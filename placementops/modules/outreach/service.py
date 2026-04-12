# @forgeplan-node: outreach-module
# @forgeplan-spec: AC1
# @forgeplan-spec: AC2
# @forgeplan-spec: AC3
# @forgeplan-spec: AC4
# @forgeplan-spec: AC5
# @forgeplan-spec: AC6
# @forgeplan-spec: AC7
# @forgeplan-spec: AC8
# @forgeplan-spec: AC9
# @forgeplan-spec: AC10
# @forgeplan-spec: AC11
# @forgeplan-spec: AC12
"""
Outreach module service layer.

Implements the 6-state approval machine:
  draft → pending_approval → approved → sent (terminal)
                                          ↓
                                        failed (terminal delivery error)
  Any pre-sent state (draft, pending_approval, approved, failed) → canceled
  sent → NOTHING (permanent record, 409 on cancel)

phone_manual and task channels bypass approval: created directly at sent.

Security constraints:
  - Template variable allowlist checked BEFORE rendering (AC1, AC2)
  - AuditEvent new_value_json NEVER contains draft_body or draft_subject (AC6)
  - sent → cancel returns 409 with exact message (AC7)
  - phone_manual/task created at sent atomically (AC8)
  - All queries scoped to organization_id (tenant isolation)
"""
# @forgeplan-decision: D-outreach-2-system-role-advance -- Use actor_role="system" for outreach_pending_approval→outreach_in_progress and outreach_in_progress→pending_facility_response. Why: state machine only allows role "system" for these transitions; outreach service orchestrates internally, not via a human actor

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import and_, func as sql_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.auth import AuthContext
from placementops.core.events import CaseActivityEvent, publish_case_activity_event
from placementops.core.models.audit_event import AuditEvent
from placementops.core.models.facility_match import FacilityMatch
from placementops.core.models.outreach_action import OutreachAction
from placementops.core.models.outreach_template import OutreachTemplate
from placementops.core.models.patient_case import PatientCase
from placementops.core.state_machine import transition_case_status
from placementops.modules.outreach.schemas import (
    OutreachActionCreate,
    OutreachActionPatch,
)
from placementops.modules.outreach.template_renderer import (
    render_template,
    validate_template_variables,
)

logger = logging.getLogger(__name__)

# Channels that bypass the approval flow and are created directly at sent
_BYPASS_CHANNELS: frozenset[str] = frozenset({"phone_manual", "task"})

# States from which cancel is permitted
_CANCELABLE_STATES: frozenset[str] = frozenset(
    {"draft", "pending_approval", "approved", "failed"}
)

# Outreach-related case statuses — used to determine if advance is needed
_OUTREACH_CASE_STATUSES: frozenset[str] = frozenset(
    {
        "outreach_pending_approval",
        "outreach_in_progress",
        "pending_facility_response",
    }
)

# Case statuses from which we can advance to outreach_pending_approval
_PRE_OUTREACH_STATUSES: frozenset[str] = frozenset(
    {"facility_options_generated", "declined_retry_needed"}
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _get_case_scoped(
    session: AsyncSession,
    case_id: UUID,
    organization_id: UUID,
) -> PatientCase:
    """Load PatientCase scoped to org; 404 if not found."""
    result = await session.execute(
        select(PatientCase).where(
            and_(
                PatientCase.id == str(case_id),
                PatientCase.organization_id == str(organization_id),
            )
        )
    )
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case {case_id} not found",
        )
    return case


async def _get_action_scoped(
    session: AsyncSession,
    action_id: UUID,
    organization_id: UUID,
) -> OutreachAction:
    """
    Load OutreachAction scoped to org via case join; 404 if not found.
    Returns 409 if the associated case is closed (AC12 / F5).

    Tenant isolation: action must belong to a case owned by organization_id.
    """
    # @forgeplan-spec: AC12
    # F5: Load both action and its case in one query so we can check case.current_status
    result = await session.execute(
        select(OutreachAction, PatientCase)
        .join(PatientCase, PatientCase.id == OutreachAction.patient_case_id)
        .where(
            and_(
                OutreachAction.id == str(action_id),
                PatientCase.organization_id == str(organization_id),
            )
        )
    )
    row = result.one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"OutreachAction {action_id} not found",
        )
    action, case = row
    # AC12 / F5: Reject mutation on actions belonging to closed cases
    if case.current_status == "closed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot modify outreach actions on a closed case",
        )
    return action


def _write_audit_event(
    session: AsyncSession,
    organization_id: UUID,
    entity_id: str,
    event_type: str,
    old_value_json: dict | None,
    new_value_json: dict | None,
    actor_user_id: UUID,
) -> None:
    """Add an AuditEvent to the session (not yet committed)."""
    audit = AuditEvent(
        organization_id=str(organization_id),
        entity_type="outreach_action",
        entity_id=entity_id,
        event_type=event_type,
        old_value_json=old_value_json,
        new_value_json=new_value_json,
        actor_user_id=str(actor_user_id),
    )
    session.add(audit)


async def _write_case_activity_event(
    case_id: UUID,
    actor_user_id: UUID,
    organization_id: UUID,
    event_type: str,
    old_status: str | None,
    new_status: str,
    metadata: dict | None = None,
) -> None:
    """Publish a CaseActivityEvent for an outreach state change."""
    event = CaseActivityEvent(
        case_id=case_id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        old_status=old_status,
        new_status=new_status,
        occurred_at=datetime.now(timezone.utc),
        organization_id=organization_id,
        metadata=metadata or {},
    )
    await publish_case_activity_event(event)


# ---------------------------------------------------------------------------
# AC1, AC8: create_outreach_action
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC1
# @forgeplan-spec: AC8
# @forgeplan-spec: AC12
async def create_outreach_action(
    session: AsyncSession,
    case_id: UUID,
    payload: OutreachActionCreate,
    auth_ctx: AuthContext,
) -> OutreachAction:
    """
    Create a new OutreachAction for a case.

    AC1: Validates template_variables against ALLOWED_VARIABLES BEFORE rendering.
    AC8: phone_manual and task channels are created at approval_status=sent immediately;
         case advances atomically to pending_facility_response.
    AC12: Returns 409 if the case is closed.
    """
    organization_id = auth_ctx.organization_id

    # Load and validate case (org-scoped)
    case = await _get_case_scoped(session, case_id, organization_id)

    # AC12: Reject mutation on closed cases
    if case.current_status == "closed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot create outreach actions on a closed case",
        )

    # @forgeplan-spec: AC8 (interface contract: matching-module)
    # F2: Validate facility_id is selected_for_outreach before drafting (AC8 / matching interface)
    # Tenant scoping via patient_case_id (FacilityMatch has no organization_id column;
    # isolation comes from the case belonging to this org, already verified above).
    if payload.facility_id is not None:
        match_result = await session.execute(
            select(FacilityMatch).where(
                and_(
                    FacilityMatch.patient_case_id == str(case_id),
                    FacilityMatch.facility_id == str(payload.facility_id),
                    FacilityMatch.selected_for_outreach.is_(True),
                )
            )
        )
        facility_match = match_result.scalar_one_or_none()
        if facility_match is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="facility must be selected for outreach before drafting outreach actions",
            )

    # Resolve draft body — apply template if provided
    draft_body = payload.draft_body
    draft_subject = payload.draft_subject

    if payload.template_id is not None:
        # Load template — must be active and belong to this org
        template_result = await session.execute(
            select(OutreachTemplate).where(
                and_(
                    OutreachTemplate.id == str(payload.template_id),
                    OutreachTemplate.organization_id == str(organization_id),
                    OutreachTemplate.is_active.is_(True),
                )
            )
        )
        template = template_result.scalar_one_or_none()
        if template is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"OutreachTemplate {payload.template_id} not found or inactive",
            )

        # AC1: Validate allowlisted variables BEFORE rendering
        variables = payload.template_variables or {}
        if variables:
            validate_template_variables(variables)

        # Render body from template
        draft_body = render_template(template.body_template, variables)
        if template.subject_template:
            draft_subject = render_template(template.subject_template, variables)

    elif payload.template_variables:
        # template_variables provided but no template_id — validate anyway (AC1)
        validate_template_variables(payload.template_variables)

    # Determine initial approval_status based on channel (AC8)
    is_bypass_channel = payload.channel in _BYPASS_CHANNELS

    action = OutreachAction(
        id=str(uuid4()),
        patient_case_id=str(case_id),
        facility_id=str(payload.facility_id) if payload.facility_id else None,
        template_id=str(payload.template_id) if payload.template_id else None,
        action_type=payload.action_type,
        channel=payload.channel,
        draft_subject=draft_subject,
        draft_body=draft_body,
        approval_status="sent" if is_bypass_channel else "draft",
        # phone_manual/task: populate sent fields immediately
        sent_by_user_id=str(auth_ctx.user_id) if is_bypass_channel else None,
        sent_at=datetime.now(timezone.utc) if is_bypass_channel else None,
    )
    session.add(action)

    if is_bypass_channel:
        # @forgeplan-decision: D-outreach-4-bypass-atomicity -- Defer commit until first transition_case_status call. Why: removing the early commit at this point means the OutreachAction and audit row are flushed (visible within the session) but not yet committed; the first transition_case_status call will commit them together with the first case-status change, achieving the atomicity required by F3
        # AC8: Flush action (do NOT commit yet — atomicity requires action and case transitions
        # to be committed together). The first transition_case_status call inside
        # _advance_case_through_outreach_to_pending will commit all pending writes atomically.
        await session.flush()

        # Write AuditEvent for creation (no body content in new_value_json)
        _write_audit_event(
            session=session,
            organization_id=organization_id,
            entity_id=action.id,
            event_type="outreach_action_created_sent",
            old_value_json=None,
            new_value_json={
                "action_id": action.id,
                "channel": action.channel,
                "approval_status": "sent",
                "sent_at": action.sent_at.isoformat() if action.sent_at else None,
                "sent_by_user_id": action.sent_by_user_id,
            },
            actor_user_id=auth_ctx.user_id,
        )
        # Do NOT commit here — advance case first; transition_case_status commits everything.

        # Advance case through intermediate outreach states to pending_facility_response.
        # The first transition_case_status call will commit the OutreachAction + its audit
        # event + the case history row in a single transaction.
        await _advance_case_through_outreach_to_pending(
            session, case, auth_ctx.user_id, auth_ctx.role_key, organization_id
        )
        await session.refresh(action)
    else:
        # email / sms / voicemail_drop / voice_ai: created at draft
        await session.flush()

        _write_audit_event(
            session=session,
            organization_id=organization_id,
            entity_id=action.id,
            event_type="outreach_action_created_draft",
            old_value_json=None,
            new_value_json={
                "action_id": action.id,
                "channel": action.channel,
                "approval_status": "draft",
            },
            actor_user_id=auth_ctx.user_id,
        )
        await session.commit()
        await session.refresh(action)

    return action


async def _advance_case_through_outreach_to_pending(
    session: AsyncSession,
    case: PatientCase,
    actor_user_id: UUID,
    actor_role: str,
    organization_id: UUID,
) -> None:
    """
    Advance case status to pending_facility_response from any outreach state.

    AC8: phone_manual/task actions trigger this — case advances through any
    intermediate outreach states to reach pending_facility_response.

    Role mapping:
      facility_options_generated → outreach_pending_approval: requires placement_coordinator|admin
      declined_retry_needed → outreach_pending_approval: requires placement_coordinator|admin
      outreach_pending_approval → outreach_in_progress: requires system
      outreach_in_progress → pending_facility_response: requires system

    Each transition is committed by transition_case_status.
    """
    # @forgeplan-spec: AC8
    current = case.current_status

    # facility_options_generated / declined_retry_needed → outreach_pending_approval
    # These transitions require placement_coordinator|admin (the actual human actor)
    if current in _PRE_OUTREACH_STATUSES:
        case = await transition_case_status(
            case_id=UUID(case.id),
            to_status="outreach_pending_approval",
            actor_role=actor_role,  # Must be placement_coordinator or admin
            actor_user_id=actor_user_id,
            session=session,
            transition_reason="phone_manual/task outreach bypasses approval flow",
            organization_id=organization_id,
        )
        current = case.current_status

    # outreach_pending_approval → outreach_in_progress: state machine requires "system"
    if current == "outreach_pending_approval":
        case = await transition_case_status(
            case_id=UUID(case.id),
            to_status="outreach_in_progress",
            actor_role="system",
            actor_user_id=actor_user_id,
            session=session,
            transition_reason="phone_manual/task outreach bypasses approval flow",
            organization_id=organization_id,
        )
        current = case.current_status

    # outreach_in_progress → pending_facility_response: state machine requires "system"
    if current == "outreach_in_progress":
        await transition_case_status(
            case_id=UUID(case.id),
            to_status="pending_facility_response",
            actor_role="system",
            actor_user_id=actor_user_id,
            session=session,
            transition_reason="First outreach action sent; awaiting facility response",
            organization_id=organization_id,
        )


# ---------------------------------------------------------------------------
# AC3: patch_outreach_action
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC3
async def patch_outreach_action(
    session: AsyncSession,
    action_id: UUID,
    patch: OutreachActionPatch,
    auth_ctx: AuthContext,
) -> OutreachAction:
    """
    Edit draft_subject and/or draft_body on a draft OutreachAction (AC3).

    Returns 409 if the action is not in draft state.
    """
    organization_id = auth_ctx.organization_id

    action = await _get_action_scoped(session, action_id, organization_id)

    if action.approval_status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"OutreachAction {action_id} is in '{action.approval_status}' state "
                "and cannot be edited; only draft actions may be patched"
            ),
        )

    old_status = action.approval_status
    if patch.draft_subject is not None:
        action.draft_subject = patch.draft_subject
    if patch.draft_body is not None:
        action.draft_body = patch.draft_body

    _write_audit_event(
        session=session,
        organization_id=organization_id,
        entity_id=action.id,
        event_type="outreach_action_patched",
        old_value_json={"approval_status": old_status},
        new_value_json={"approval_status": action.approval_status, "patched_fields": list(
            k for k, v in {"draft_subject": patch.draft_subject, "draft_body": patch.draft_body}.items()
            if v is not None
        )},
        actor_user_id=auth_ctx.user_id,
    )

    await session.commit()
    await session.refresh(action)
    return action


# ---------------------------------------------------------------------------
# AC4: submit_for_approval
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC4
# @forgeplan-spec: AC11
async def submit_for_approval(
    session: AsyncSession,
    action_id: UUID,
    auth_ctx: AuthContext,
) -> OutreachAction:
    """
    Submit an OutreachAction for approval (AC4).

    Transitions action draft → pending_approval.
    Advances case to outreach_pending_approval if not already in an outreach state.
    Writes AuditEvent and case_activity_event (AC11).
    """
    organization_id = auth_ctx.organization_id

    action = await _get_action_scoped(session, action_id, organization_id)

    if action.approval_status != "draft":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"OutreachAction {action_id} is in '{action.approval_status}' state; "
                "only draft actions can be submitted for approval"
            ),
        )

    action.approval_status = "pending_approval"

    _write_audit_event(
        session=session,
        organization_id=organization_id,
        entity_id=action.id,
        event_type="outreach_action_submitted",
        old_value_json={"approval_status": "draft"},
        new_value_json={"approval_status": "pending_approval"},
        actor_user_id=auth_ctx.user_id,
    )

    await session.commit()
    await session.refresh(action)

    case_id = UUID(action.patient_case_id)

    # Reload case to check current status
    case = await _get_case_scoped(session, case_id, organization_id)

    # Advance case to outreach_pending_approval if at a pre-outreach status (AC4)
    if case.current_status in _PRE_OUTREACH_STATUSES:
        await transition_case_status(
            case_id=case_id,
            to_status="outreach_pending_approval",
            actor_role=auth_ctx.role_key,
            actor_user_id=auth_ctx.user_id,
            session=session,
            transition_reason="Outreach action submitted for approval",
            organization_id=organization_id,
        )

    # Also publish a case_activity_event for the outreach state change (AC11)
    await _write_case_activity_event(
        case_id=case_id,
        actor_user_id=auth_ctx.user_id,
        organization_id=organization_id,
        event_type="outreach_submitted",
        old_status="draft",
        new_status="pending_approval",
        metadata={"action_id": action.id},
    )

    return action


# ---------------------------------------------------------------------------
# AC5: approve_action
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC5
# @forgeplan-spec: AC11
async def approve_action(
    session: AsyncSession,
    action_id: UUID,
    auth_ctx: AuthContext,
) -> OutreachAction:
    """
    Approve a pending_approval OutreachAction (AC5).

    Sets approval_status=approved, approved_by_user_id, approved_at.
    If first approved action for this case → advance case to outreach_in_progress.
    Writes AuditEvent (AC11).
    """
    organization_id = auth_ctx.organization_id

    action = await _get_action_scoped(session, action_id, organization_id)

    if action.approval_status != "pending_approval":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"OutreachAction {action_id} is in '{action.approval_status}' state; "
                "only pending_approval actions can be approved"
            ),
        )

    approved_at = datetime.now(timezone.utc)
    action.approval_status = "approved"
    action.approved_by_user_id = str(auth_ctx.user_id)
    action.approved_at = approved_at

    _write_audit_event(
        session=session,
        organization_id=organization_id,
        entity_id=action.id,
        event_type="outreach_action_approved",
        old_value_json={"approval_status": "pending_approval"},
        new_value_json={
            "approval_status": "approved",
            "approved_by_user_id": str(auth_ctx.user_id),
            "approved_at": approved_at.isoformat(),
        },
        actor_user_id=auth_ctx.user_id,
    )

    await session.commit()
    await session.refresh(action)

    case_id = UUID(action.patient_case_id)

    # AC5: Check if this is the first approved action for the case
    existing_approved = await session.execute(
        select(OutreachAction).where(
            and_(
                OutreachAction.patient_case_id == str(case_id),
                OutreachAction.id != action.id,
                OutreachAction.approval_status.in_(["approved", "sent"]),
            )
        )
    )
    is_first_approved = existing_approved.scalar_one_or_none() is None

    if is_first_approved:
        # Advance case to outreach_in_progress if at outreach_pending_approval
        case = await _get_case_scoped(session, case_id, organization_id)
        if case.current_status == "outreach_pending_approval":
            try:
                await transition_case_status(
                    case_id=case_id,
                    to_status="outreach_in_progress",
                    actor_role="system",
                    actor_user_id=auth_ctx.user_id,
                    session=session,
                    transition_reason="First outreach action approved",
                    organization_id=organization_id,
                )
            except HTTPException as exc:
                # F38: Guard against race condition where two coordinators
                # simultaneously approve actions for the same case. Both may
                # read is_first_approved=True; the second concurrent call
                # reaches here after the first has already advanced the state
                # machine. Treat an invalid_transition as a no-op — the case
                # is already in the correct state and the action was validly
                # approved.
                if exc.status_code == 400 and (
                    exc.detail if isinstance(exc.detail, str) else (exc.detail or {}).get("error_code")
                ) == "invalid_transition":
                    logger.warning(
                        "approve_action: concurrent approval detected for case %s — "
                        "state machine already advanced, ignoring invalid_transition error",
                        case_id,
                    )
                else:
                    raise

    # @forgeplan-spec: AC11
    # F1: Write case_activity_event for pending_approval→approved transition (AC11)
    await _write_case_activity_event(
        case_id=case_id,
        actor_user_id=auth_ctx.user_id,
        organization_id=organization_id,
        event_type="outreach_approved",
        old_status="pending_approval",
        new_status="approved",
        metadata={"action_id": action.id},
    )

    return action


# ---------------------------------------------------------------------------
# AC6: mark_sent
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC6
# @forgeplan-spec: AC11
async def mark_sent(
    session: AsyncSession,
    action_id: UUID,
    auth_ctx: AuthContext,
) -> OutreachAction:
    """
    Mark an approved OutreachAction as sent (AC6).

    Sets approval_status=sent, sent_by_user_id, sent_at.
    AuditEvent new_value_json MUST NOT contain draft_body or draft_subject (AC6 constraint).
    Advances case to pending_facility_response if first sent action.
    Writes AuditEvent and case_activity_event (AC11).
    """
    organization_id = auth_ctx.organization_id

    action = await _get_action_scoped(session, action_id, organization_id)

    if action.approval_status != "approved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"OutreachAction {action_id} is in '{action.approval_status}' state; "
                "only approved actions can be marked as sent"
            ),
        )

    sent_at = datetime.now(timezone.utc)
    action.approval_status = "sent"
    action.sent_by_user_id = str(auth_ctx.user_id)
    action.sent_at = sent_at

    # AC6: new_value_json MUST NOT contain draft_body or draft_subject
    _write_audit_event(
        session=session,
        organization_id=organization_id,
        entity_id=action.id,
        event_type="outreach_action_sent",
        old_value_json={"approval_status": "approved"},
        new_value_json={
            "action_id": action.id,
            "approval_status": "sent",
            "sent_at": sent_at.isoformat(),
            "sent_by_user_id": str(auth_ctx.user_id),
            "delivery_status": action.delivery_status,
        },
        actor_user_id=auth_ctx.user_id,
    )

    await session.commit()
    await session.refresh(action)

    case_id = UUID(action.patient_case_id)

    # AC6: Advance case to pending_facility_response if first sent action
    existing_sent = await session.execute(
        select(OutreachAction).where(
            and_(
                OutreachAction.patient_case_id == str(case_id),
                OutreachAction.id != action.id,
                OutreachAction.approval_status == "sent",
            )
        )
    )
    is_first_sent = existing_sent.scalar_one_or_none() is None

    if is_first_sent:
        case = await _get_case_scoped(session, case_id, organization_id)
        if case.current_status == "outreach_in_progress":
            await transition_case_status(
                case_id=case_id,
                to_status="pending_facility_response",
                actor_role="system",
                actor_user_id=auth_ctx.user_id,
                session=session,
                transition_reason="First outreach action marked sent; awaiting facility response",
                organization_id=organization_id,
            )

    # Publish case_activity_event for the outreach state change (AC11)
    await _write_case_activity_event(
        case_id=case_id,
        actor_user_id=auth_ctx.user_id,
        organization_id=organization_id,
        event_type="outreach_sent",
        old_status="approved",
        new_status="sent",
        metadata={"action_id": action.id},
    )

    return action


# ---------------------------------------------------------------------------
# AC7: cancel_action
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC7
# @forgeplan-spec: AC11
async def cancel_action(
    session: AsyncSession,
    action_id: UUID,
    auth_ctx: AuthContext,
) -> OutreachAction:
    """
    Cancel an OutreachAction (AC7).

    Returns 409 with "sent records are permanent communication records" if sent.
    Cancels from any other pre-sent state.
    Writes AuditEvent and case_activity_event (AC11).
    """
    organization_id = auth_ctx.organization_id

    action = await _get_action_scoped(session, action_id, organization_id)

    # AC7: sent → 409, permanent record
    if action.approval_status == "sent":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="sent records are permanent communication records",
        )

    if action.approval_status not in _CANCELABLE_STATES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"OutreachAction {action_id} is in '{action.approval_status}' state "
                "and cannot be canceled"
            ),
        )

    old_status = action.approval_status
    action.approval_status = "canceled"

    _write_audit_event(
        session=session,
        organization_id=organization_id,
        entity_id=action.id,
        event_type="outreach_action_canceled",
        old_value_json={"approval_status": old_status},
        new_value_json={"approval_status": "canceled"},
        actor_user_id=auth_ctx.user_id,
    )

    await session.commit()
    await session.refresh(action)

    case_id = UUID(action.patient_case_id)

    # Publish case_activity_event (AC11)
    await _write_case_activity_event(
        case_id=case_id,
        actor_user_id=auth_ctx.user_id,
        organization_id=organization_id,
        event_type="outreach_canceled",
        old_status=old_status,
        new_status="canceled",
        metadata={"action_id": action.id},
    )

    return action


# ---------------------------------------------------------------------------
# AC9: get_outreach_queue
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC9
async def get_outreach_queue(
    session: AsyncSession,
    auth_ctx: AuthContext,
    approval_status_filter: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[OutreachAction], int]:
    """
    Return OutreachAction records scoped to organization_id (AC9).

    Filterable by approval_status. Returns (items, total) for pagination.
    Tenant isolation: queries via PatientCase.organization_id join.
    """
    organization_id = auth_ctx.organization_id

    base_query = (
        select(OutreachAction)
        .join(PatientCase, PatientCase.id == OutreachAction.patient_case_id)
        .where(PatientCase.organization_id == str(organization_id))
    )

    if approval_status_filter:
        base_query = base_query.where(
            OutreachAction.approval_status == approval_status_filter
        )

    # Total count
    count_result = await session.execute(
        select(sql_func.count()).select_from(base_query.subquery())
    )
    total = count_result.scalar() or 0

    # Paginated results
    offset = (page - 1) * page_size
    result = await session.execute(
        base_query.order_by(OutreachAction.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    items = list(result.scalars().all())

    return items, total


# ---------------------------------------------------------------------------
# AC10: get_templates
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC10
async def get_templates(
    session: AsyncSession,
    auth_ctx: AuthContext,
) -> list[OutreachTemplate]:
    """
    Return active OutreachTemplate records for the organization (AC10).

    Read-only — template CRUD is owned by admin-surfaces.
    """
    organization_id = auth_ctx.organization_id

    result = await session.execute(
        select(OutreachTemplate).where(
            and_(
                OutreachTemplate.organization_id == str(organization_id),
                OutreachTemplate.is_active.is_(True),
            )
        )
    )
    return list(result.scalars().all())
