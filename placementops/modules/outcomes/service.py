# @forgeplan-node: outcomes-module
# @forgeplan-spec: AC1, AC2, AC3, AC4, AC5, AC6, AC7, AC8, AC9, AC10, AC11, AC12, AC13, AC14, AC15, AC16
"""
Outcomes module service layer.

Key functions:
  - record_outcome()          — orchestrate all outcome types
  - _validate_sent_outreach() — 400 if no sent outreach for facility
  - _validate_decline_reason_code() — 400 if code not in reference table
  - _auto_cancel_open_outreach() — cancel draft/pending_approval/approved actions
  - get_outcomes()            — list PlacementOutcome records for a case
  - get_timeline()            — list CaseStatusHistory rows as timeline events
  - status_transition()       — retry routing and case closure

Atomicity design (D-outcomes-1-pre-flush-atomicity):
  All pending writes (outcome row, outcome AuditEvent, auto-cancel updates)
  are added to the session and flushed via session.flush() BEFORE calling
  transition_case_status(). The transition function then issues a commit()
  that atomically persists the entire batch in one transaction.

family_declined / withdrawn design (D-outcomes-3-family-withdrawn-no-transition):
  These outcome types do NOT call transition_case_status. The case status
  remains unchanged; a manager/admin separately closes the case via the
  status-transition endpoint.

Timeline design (D-outcomes-2-timeline-from-csh):
  GET /timeline reads CaseStatusHistory rows, which are the persisted
  record of every status transition; the in-process event bus is ephemeral.
"""
# @forgeplan-decision: D-outcomes-1-pre-flush-atomicity -- Flush all pending writes before calling transition_case_status which commits. Why: transition_case_status owns the commit; flushing ensures outcome row + auto-cancel updates land in the same atomic commit as the status advance
# @forgeplan-decision: D-outcomes-2-timeline-from-csh -- Read timeline from CaseStatusHistory table. Why: in-process event bus (CaseActivityEvent) is ephemeral; CaseStatusHistory is the only durable timeline store written by transition_case_status
# @forgeplan-decision: D-outcomes-3-family-withdrawn-no-transition -- family_declined/withdrawn do not call transition_case_status. Why: spec requires manager confirmation via separate status-transition; auto-advancing to closed removes required managerial oversight
# @forgeplan-decision: D-outcomes-4-outcome-audit-separate -- Write AuditEvent with entity_type=placement_outcome for every outcome type. Why: AC14 mandates audit for all 5 types; transition_case_status only writes for types that advance status; family_declined/withdrawn have no status change audit unless we write it here

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.audit import emit_audit_event
from placementops.core.auth import AuthContext
from placementops.core.models.audit_event import AuditEvent
from placementops.core.models.case_status_history import CaseStatusHistory
from placementops.core.models.outreach_action import OutreachAction
from placementops.core.models.patient_case import PatientCase
from placementops.core.models.placement_outcome import PlacementOutcome
from placementops.core.models.reference_tables import DeclineReasonReference
from placementops.core.state_machine import transition_case_status
from placementops.modules.outcomes.schemas import (
    PlacementOutcomeCreate,
    StatusTransitionRequest,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Outcome types that require facility_id and a sent outreach for that facility
_FACILITY_REQUIRED_TYPES: frozenset[str] = frozenset({"accepted", "declined", "placed"})

# Outcome types that auto-cancel open outreach on success
_AUTO_CANCEL_TYPES: frozenset[str] = frozenset({"accepted", "placed"})

# Outreach states eligible for auto-cancel (sent and failed are exempt)
_CANCELABLE_OUTREACH_STATES: list[str] = ["draft", "pending_approval", "approved"]

# Map outcome_type → case target status (None means no status change)
_OUTCOME_STATUS_MAP: dict[str, str | None] = {
    "accepted": "accepted",
    "declined": "declined_retry_needed",
    "placed": "placed",
    "family_declined": None,  # no auto-advance — manager must confirm
    "withdrawn": None,         # no auto-advance — manager must confirm
}

# Outcome types that require manager or admin for closure confirmation
_CLOSURE_ROLES: frozenset[str] = frozenset({"manager", "admin"})

# Outcome types that can record when case is at any non-closed status
_RECORD_OUTCOME_ALLOWED_TYPES: frozenset[str] = frozenset(
    {"accepted", "declined", "placed", "family_declined", "withdrawn"}
)


# ---------------------------------------------------------------------------
# Private validation helpers
# ---------------------------------------------------------------------------


async def _get_case(
    session: AsyncSession,
    case_id: UUID,
    auth_ctx: AuthContext,
) -> PatientCase:
    """
    Load a PatientCase scoped to the caller's organization.

    Raises 404 if not found.
    Raises 409 if case is closed (AC15).
    """
    # @forgeplan-spec: AC15
    result = await session.execute(
        select(PatientCase).where(
            and_(
                PatientCase.id == str(case_id),
                PatientCase.organization_id == str(auth_ctx.organization_id),
            )
        )
    )
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case {case_id} not found",
        )
    if case.current_status == "closed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot record outcome on a closed case",
        )
    return case


async def _validate_sent_outreach(
    session: AsyncSession,
    case_id: UUID,
    facility_id: UUID,
) -> None:
    """
    Validate that at least one OutreachAction with approval_status=sent
    exists for the given facility on this case.

    Raises HTTP 400 with descriptive error if no sent outreach exists (AC2, AC4).
    """
    # @forgeplan-spec: AC2
    # @forgeplan-spec: AC4
    result = await session.execute(
        select(OutreachAction).where(
            and_(
                OutreachAction.patient_case_id == str(case_id),
                OutreachAction.facility_id == str(facility_id),
                OutreachAction.approval_status == "sent",
            )
        )
    )
    sent_action = result.scalar_one_or_none()
    if sent_action is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "no_sent_outreach",
                "message": (
                    f"No sent outreach action found for facility {facility_id} on this case. "
                    "An outreach must be marked as sent before recording an accepted or declined outcome."
                ),
                "facility_id": str(facility_id),
                "case_id": str(case_id),
            },
        )


async def _validate_decline_reason_code(
    session: AsyncSession,
    code: str,
) -> None:
    """
    Validate that the decline_reason_code exists in the decline_reason_reference table.

    Raises HTTP 400 if the code is not in the seeded reference data (AC4, AC16).
    """
    # @forgeplan-spec: AC4
    # @forgeplan-spec: AC16
    result = await session.execute(
        select(DeclineReasonReference).where(DeclineReasonReference.code == code)
    )
    ref = result.scalar_one_or_none()
    if ref is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_decline_reason_code",
                "message": (
                    f"Decline reason code '{code}' is not in the decline_reason_reference table. "
                    "Valid codes include: bed_no_longer_available, insurance_issue_post_acceptance, "
                    "clinical_criteria_not_met, no_response."
                ),
                "provided_code": code,
            },
        )


async def _auto_cancel_open_outreach(
    session: AsyncSession,
    case_id: UUID,
) -> list[str]:
    """
    Atomically cancel all OutreachAction records in draft/pending_approval/approved
    states for the given case.

    sent and failed actions are NEVER canceled (AC8 constraint).

    Returns the list of canceled action IDs.

    IMPORTANT: This function adds updates to the session but does NOT flush or commit.
    The caller is responsible for flushing before the commit issued by
    transition_case_status (D-outcomes-1-pre-flush-atomicity).
    """
    # @forgeplan-spec: AC8
    result = await session.execute(
        select(OutreachAction).where(
            and_(
                OutreachAction.patient_case_id == str(case_id),
                OutreachAction.approval_status.in_(_CANCELABLE_OUTREACH_STATES),
            )
        )
    )
    actions_to_cancel = result.scalars().all()

    canceled_ids: list[str] = []
    for action in actions_to_cancel:
        action.approval_status = "canceled"
        canceled_ids.append(action.id)

    if canceled_ids:
        logger.info(
            "Auto-canceling %d outreach actions for case %s: %s",
            len(canceled_ids),
            case_id,
            canceled_ids,
        )

    return canceled_ids


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------


async def record_outcome(
    session: AsyncSession,
    case_id: UUID,
    payload: PlacementOutcomeCreate,
    auth_ctx: AuthContext,
) -> PlacementOutcome:
    """
    Record a placement outcome for a case.

    Orchestrates:
      1. Load case, enforce closed-case guard (AC15)
      2. Validate facility + sent outreach for accepted/declined/placed (AC2, AC4)
      3. Validate decline_reason_code for declined (AC4, AC16)
      4. Create PlacementOutcome row
      5. Write AuditEvent (entity_type=placement_outcome) for ALL outcome types (AC14)
      6. For accepted/placed: auto-cancel open outreach (AC8)
      7. Flush all pending writes
      8. For accepted/declined/placed: call transition_case_status (which commits)
      9. For family_declined/withdrawn: commit manually (no status advance)
      10. Publish case_activity_event
    """
    # @forgeplan-spec: AC1
    # @forgeplan-spec: AC2
    # @forgeplan-spec: AC3
    # @forgeplan-spec: AC4
    # @forgeplan-spec: AC5
    # @forgeplan-spec: AC6
    # @forgeplan-spec: AC7
    # @forgeplan-spec: AC8
    # @forgeplan-spec: AC10
    # @forgeplan-spec: AC14
    # @forgeplan-spec: AC15

    # Step 1: Load case with closed-case guard
    case = await _get_case(session, case_id, auth_ctx)
    from_status = case.current_status

    # Step 2: Validate facility + sent outreach (required for accepted/declined/placed)
    if payload.outcome_type in _FACILITY_REQUIRED_TYPES:
        if payload.facility_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"outcome_type '{payload.outcome_type}' requires a facility_id",
            )
        # Now validate sent outreach for this facility
        await _validate_sent_outreach(session, case_id, payload.facility_id)

    # Step 3: Validate decline_reason_code (required for declined)
    if payload.outcome_type == "declined":
        # facility_id required for declined — already enforced by schema validator
        await _validate_decline_reason_code(session, payload.decline_reason_code)  # type: ignore[arg-type]

    # Step 4: Create PlacementOutcome row
    outcome = PlacementOutcome(
        id=str(uuid4()),
        patient_case_id=str(case_id),
        facility_id=str(payload.facility_id) if payload.facility_id else None,
        outcome_type=payload.outcome_type,
        decline_reason_code=payload.decline_reason_code,
        decline_reason_text=payload.decline_reason_text,
        recorded_by_user_id=str(auth_ctx.user_id),
    )
    session.add(outcome)

    # Step 5: Write AuditEvent for the outcome record (ALL outcome types — AC14)
    # @forgeplan-spec: AC14
    await emit_audit_event(
        session=session,
        organization_id=auth_ctx.organization_id,
        entity_type="placement_outcome",
        entity_id=UUID(outcome.id),
        event_type="outcome_recorded",
        actor_user_id=auth_ctx.user_id,
        old_value={"case_status": from_status},
        new_value={
            "outcome_type": payload.outcome_type,
            "facility_id": str(payload.facility_id) if payload.facility_id else None,
            "decline_reason_code": payload.decline_reason_code,
        },
    )

    # Step 6: For accepted/placed, auto-cancel open outreach (AC8)
    canceled_ids: list[str] = []
    if payload.outcome_type in _AUTO_CANCEL_TYPES:
        canceled_ids = await _auto_cancel_open_outreach(session, case_id)

    # Step 7: Flush all pending writes before the transition's commit
    # (D-outcomes-1-pre-flush-atomicity)
    await session.flush()

    # Steps 8-9: Status transition or plain commit
    to_status = _OUTCOME_STATUS_MAP.get(payload.outcome_type)

    if to_status is not None:
        # Delegates commit to transition_case_status (AC3, AC5, AC6, AC10)
        await transition_case_status(
            case_id=case_id,
            to_status=to_status,
            actor_role=auth_ctx.role_key,
            actor_user_id=auth_ctx.user_id,
            session=session,
            transition_reason=f"Outcome recorded: {payload.outcome_type}",
            organization_id=auth_ctx.organization_id,
        )
    else:
        # family_declined / withdrawn — commit the outcome + audit without status change
        # (D-outcomes-3-family-withdrawn-no-transition)
        await session.commit()

    logger.info(
        "Outcome '%s' recorded for case %s by user %s (role=%s); canceled_outreach=%s",
        payload.outcome_type,
        case_id,
        auth_ctx.user_id,
        auth_ctx.role_key,
        canceled_ids,
    )

    return outcome


async def get_outcomes(
    session: AsyncSession,
    case_id: UUID,
    auth_ctx: AuthContext,
) -> list[PlacementOutcome]:
    """
    Return all PlacementOutcome records for a case, ordered by created_at.

    Tenant isolation: the case is loaded first to confirm org ownership.
    """
    # @forgeplan-spec: AC13
    # Verify case belongs to caller's org (tenant isolation)
    case_result = await session.execute(
        select(PatientCase).where(
            and_(
                PatientCase.id == str(case_id),
                PatientCase.organization_id == str(auth_ctx.organization_id),
            )
        )
    )
    case = case_result.scalar_one_or_none()
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case {case_id} not found",
        )

    result = await session.execute(
        select(PlacementOutcome)
        .where(PlacementOutcome.patient_case_id == str(case_id))
        .order_by(PlacementOutcome.created_at)
    )
    return list(result.scalars().all())


async def get_timeline(
    session: AsyncSession,
    case_id: UUID,
    auth_ctx: AuthContext,
) -> list[CaseStatusHistory]:
    """
    Return the chronological timeline of case status transitions.

    Reads from CaseStatusHistory (the persisted record written by every
    transition_case_status call). Ordered by entered_at ascending (AC12).

    Tenant isolation: the case is loaded first to confirm org ownership.
    """
    # @forgeplan-spec: AC12
    # Verify case belongs to caller's org (tenant isolation)
    case_result = await session.execute(
        select(PatientCase).where(
            and_(
                PatientCase.id == str(case_id),
                PatientCase.organization_id == str(auth_ctx.organization_id),
            )
        )
    )
    case = case_result.scalar_one_or_none()
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case {case_id} not found",
        )

    result = await session.execute(
        select(CaseStatusHistory)
        .where(
            and_(
                CaseStatusHistory.patient_case_id == str(case_id),
                CaseStatusHistory.organization_id == str(auth_ctx.organization_id),
            )
        )
        .order_by(CaseStatusHistory.entered_at)
    )
    return list(result.scalars().all())


async def status_transition(
    session: AsyncSession,
    case_id: UUID,
    payload: StatusTransitionRequest,
    auth_ctx: AuthContext,
) -> PatientCase:
    """
    Execute a case status transition via the shared state machine handler.

    Used for:
      - Retry routing: declined_retry_needed → ready_for_matching or
        outreach_pending_approval (AC9)
      - Case closure: any non-closed status → closed (AC11)

    AC11 constraints:
      - Closure requires non-empty transition_reason
      - Closure restricted to manager or admin role

    Delegates all transition validation and execution to transition_case_status.
    This module MUST NOT write PatientCase.current_status directly.
    """
    # @forgeplan-spec: AC9
    # @forgeplan-spec: AC11

    # AC11: Closure requires closure_reason text and manager/admin role
    if payload.to_status == "closed":
        if not payload.transition_reason or not payload.transition_reason.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "error": "closure_reason_required",
                    "message": "transition_reason is required (non-empty) when transitioning to 'closed'",
                },
            )
        if auth_ctx.role_key not in _CLOSURE_ROLES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "insufficient_role_for_closure",
                    "message": f"Role '{auth_ctx.role_key}' is not permitted to close cases. "
                    "Only manager or admin may close cases.",
                    "permitted_roles": list(_CLOSURE_ROLES),
                },
            )

    # Verify case belongs to caller's org (tenant isolation) before calling state machine
    case_result = await session.execute(
        select(PatientCase).where(
            and_(
                PatientCase.id == str(case_id),
                PatientCase.organization_id == str(auth_ctx.organization_id),
            )
        )
    )
    case = case_result.scalar_one_or_none()
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case {case_id} not found",
        )

    # Delegate to the canonical state machine handler
    updated_case = await transition_case_status(
        case_id=case_id,
        to_status=payload.to_status,
        actor_role=auth_ctx.role_key,
        actor_user_id=auth_ctx.user_id,
        session=session,
        transition_reason=payload.transition_reason,
        organization_id=auth_ctx.organization_id,
    )

    return updated_case
