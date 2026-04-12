# @forgeplan-node: core-infrastructure
"""
Case status transition handler — the single authoritative gatekeeper for all status transitions.

No module may bypass this handler to update current_status directly.
Enforces:
  1. Transition allowlist — 400 if from_status → to_status not permitted.
  2. Role gate — 403 if actor_role not in permitted_roles for this transition.
  3. Writes CaseStatusHistory row for every transition.
  4. Publishes CaseActivityEvent to the in-process event bus.
"""
# @forgeplan-spec: AC6
# @forgeplan-spec: AC8
# @forgeplan-spec: AC9
# @forgeplan-decision: D-core-4-select-for-update -- SELECT FOR UPDATE on PatientCase before transition. Why: prevents lost updates under concurrent transitions (two coordinators racing to close the same case)

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.models.patient_case import PatientCase
from placementops.core.models.case_status_history import CaseStatusHistory
from placementops.core.models.audit_event import AuditEvent
from placementops.core.events import CaseActivityEvent, publish_case_activity_event

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Authoritative state machine transition allowlist
# Format: { from_status: { to_status: [permitted_roles] } }
# This MUST match the spec exactly — do not add or remove transitions.
# ---------------------------------------------------------------------------
STATE_MACHINE_TRANSITIONS: dict[str, dict[str, list[str]]] = {
    "new": {
        "intake_in_progress": ["system", "intake_staff", "admin"],
    },
    "intake_in_progress": {
        "intake_complete": ["intake_staff", "admin"],
        "closed": ["manager", "admin"],
    },
    "intake_complete": {
        "needs_clinical_review": ["system", "intake_staff", "admin"],
        "closed": ["manager", "admin"],
    },
    "needs_clinical_review": {
        "under_clinical_review": ["clinical_reviewer", "admin"],
        "closed": ["manager", "admin"],
    },
    "under_clinical_review": {
        "needs_clinical_review": ["clinical_reviewer", "admin"],
        "ready_for_matching": ["clinical_reviewer", "admin"],
        "closed": ["manager", "admin"],
    },
    "ready_for_matching": {
        "facility_options_generated": ["system", "placement_coordinator", "clinical_reviewer", "admin"],
        "closed": ["manager", "admin"],
    },
    "facility_options_generated": {
        "outreach_pending_approval": ["placement_coordinator", "admin"],
        "ready_for_matching": ["placement_coordinator", "admin"],
        "closed": ["manager", "admin"],
    },
    "outreach_pending_approval": {
        "outreach_in_progress": ["system"],
        "closed": ["manager", "admin"],
    },
    "outreach_in_progress": {
        "pending_facility_response": ["system"],
        "closed": ["manager", "admin"],
    },
    "pending_facility_response": {
        "accepted": ["placement_coordinator", "admin"],
        "declined_retry_needed": ["system", "placement_coordinator", "admin"],
        "closed": ["manager", "admin"],
    },
    "accepted": {
        "placed": ["placement_coordinator", "admin"],
        "declined_retry_needed": ["placement_coordinator", "admin"],
        "closed": ["manager", "admin"],
    },
    "declined_retry_needed": {
        "ready_for_matching": ["placement_coordinator", "admin"],
        "outreach_pending_approval": ["placement_coordinator", "admin"],
        "closed": ["manager", "admin"],
    },
    "placed": {
        "closed": ["manager", "admin"],
    },
    # closed is terminal — no transitions out
}


async def transition_case_status(
    case_id: UUID,
    to_status: str,
    actor_role: str,
    actor_user_id: UUID,
    session: AsyncSession,
    transition_reason: str | None = None,
    organization_id: UUID | None = None,
) -> PatientCase:
    """
    Transition a PatientCase to a new status.

    Steps:
      1. Load case with SELECT FOR UPDATE (pessimistic lock)
      2. Validate from_status → to_status is in allowlist → 400 if not
      3. Validate actor_role is in permitted_roles → 403 if not
      4. Update case.current_status
      5. Insert CaseStatusHistory row
      6. Insert AuditEvent row
      7. Commit
      8. Publish CaseActivityEvent

    Returns the updated PatientCase.
    Raises HTTPException 404 if case not found.
    Raises HTTPException 400 if transition not in allowlist.
    Raises HTTPException 403 if actor role not permitted for this transition.
    """
    # @forgeplan-spec: AC6
    # Step 1: Load case with row-level lock to prevent concurrent modification
    # Filter on organization_id when provided to prevent cross-tenant transitions (F7)
    _case_query = (
        select(PatientCase)
        .where(PatientCase.id == str(case_id))
        .with_for_update()
    )
    if organization_id is not None:
        _case_query = _case_query.where(
            PatientCase.organization_id == str(organization_id)
        )
    result = await session.execute(_case_query)
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case {case_id} not found",
        )

    from_status = case.current_status

    # Guard: closed cases are terminal — no further transitions permitted (F4)
    if from_status == "closed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Case is closed — no further modifications permitted",
        )

    # Step 2: Validate transition is in allowlist
    allowed_transitions = STATE_MACHINE_TRANSITIONS.get(from_status, {})
    if to_status not in allowed_transitions:
        allowed = list(allowed_transitions.keys())
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "invalid_transition",
                "message": f"Transition from '{from_status}' to '{to_status}' is not allowed",
                "allowed_transitions": allowed,
                "from_status": from_status,
                "to_status": to_status,
            },
        )

    # Step 3: Validate actor role is permitted for this transition
    permitted_roles = allowed_transitions[to_status]
    if actor_role not in permitted_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "role_not_permitted",
                "message": f"Role '{actor_role}' is not permitted to transition from '{from_status}' to '{to_status}'",
                "permitted_roles": permitted_roles,
                "actor_role": actor_role,
            },
        )

    # Step 4: Update case status
    case.current_status = to_status

    # Resolve org_id for history/audit rows
    effective_org_id = organization_id or case.organization_id

    # Step 5: Insert CaseStatusHistory row
    history_row = CaseStatusHistory(
        organization_id=str(effective_org_id),
        patient_case_id=str(case_id),
        from_status=from_status,
        to_status=to_status,
        actor_user_id=str(actor_user_id),
        transition_reason=transition_reason,
    )
    session.add(history_row)

    # Step 6: Insert AuditEvent row
    # @forgeplan-spec: AC8
    audit = AuditEvent(
        organization_id=str(effective_org_id),
        entity_type="patient_case",
        entity_id=str(case_id),
        event_type="status_changed",
        old_value_json={"status": from_status},
        new_value_json={"status": to_status},
        actor_user_id=str(actor_user_id),
    )
    session.add(audit)

    # Step 7: Commit all changes atomically
    await session.commit()
    await session.refresh(case)

    logger.info(
        "Case %s transitioned from '%s' to '%s' by actor %s (role=%s)",
        case_id,
        from_status,
        to_status,
        actor_user_id,
        actor_role,
    )

    # Step 8: Publish event AFTER commit (so subscribers see committed state)
    # @forgeplan-spec: AC9
    event = CaseActivityEvent(
        case_id=case_id,
        actor_user_id=actor_user_id,
        event_type="status_changed",
        old_status=from_status,
        new_status=to_status,
        occurred_at=datetime.now(timezone.utc),
        organization_id=UUID(str(effective_org_id)) if effective_org_id else None,
        metadata={"transition_reason": transition_reason},
    )
    await publish_case_activity_event(event)

    return case
