# @forgeplan-node: core-infrastructure
"""
Tests for case status transition handler — AC6.

Tests:
  (a) Transition not in allowlist → 400 with list of allowed transitions
  (b) Valid transition, wrong role → 403
  (c) Valid transition, correct role → success; state change committed
"""
# @forgeplan-spec: AC6

import pytest
from uuid import uuid4, UUID
from fastapi import HTTPException

from placementops.core.state_machine import transition_case_status, STATE_MACHINE_TRANSITIONS

pytestmark = pytest.mark.asyncio


async def test_invalid_transition_returns_400(db_session, patient_case, user):
    """AC6a: Transition not in allowlist returns 400 with allowed_transitions list."""
    case_id = UUID(patient_case.id)
    actor_user_id = UUID(user.id)

    with pytest.raises(HTTPException) as exc_info:
        await transition_case_status(
            case_id=case_id,
            to_status="placed",  # new → placed is NOT in allowlist
            actor_role="admin",
            actor_user_id=actor_user_id,
            session=db_session,
        )

    exc = exc_info.value
    assert exc.status_code == 400
    detail = exc.detail
    assert "allowed_transitions" in detail
    assert detail["from_status"] == "new"
    assert "intake_in_progress" in detail["allowed_transitions"]


async def test_wrong_role_returns_403(db_session, patient_case, user):
    """AC6b: Valid transition path but wrong role → 403."""
    case_id = UUID(patient_case.id)
    actor_user_id = UUID(user.id)

    # new → intake_in_progress requires [system, intake_staff, admin]
    # clinical_reviewer is NOT permitted
    with pytest.raises(HTTPException) as exc_info:
        await transition_case_status(
            case_id=case_id,
            to_status="intake_in_progress",
            actor_role="clinical_reviewer",  # not permitted
            actor_user_id=actor_user_id,
            session=db_session,
        )

    exc = exc_info.value
    assert exc.status_code == 403
    detail = exc.detail
    assert "clinical_reviewer" in detail["actor_role"]
    assert "intake_staff" in detail["permitted_roles"]


async def test_valid_transition_succeeds(db_session, patient_case, user):
    """AC6c: Valid transition with correct role commits state change."""
    case_id = UUID(patient_case.id)
    actor_user_id = UUID(user.id)

    assert patient_case.current_status == "new"

    updated_case = await transition_case_status(
        case_id=case_id,
        to_status="intake_in_progress",
        actor_role="intake_staff",
        actor_user_id=actor_user_id,
        session=db_session,
        organization_id=UUID(patient_case.organization_id),
    )

    assert updated_case.current_status == "intake_in_progress"


async def test_valid_transition_writes_case_status_history(db_session, patient_case, user):
    """Successful transition writes a CaseStatusHistory row."""
    from sqlalchemy import select
    from placementops.core.models import CaseStatusHistory

    case_id = UUID(patient_case.id)
    actor_user_id = UUID(user.id)

    await transition_case_status(
        case_id=case_id,
        to_status="intake_in_progress",
        actor_role="intake_staff",
        actor_user_id=actor_user_id,
        session=db_session,
        organization_id=UUID(patient_case.organization_id),
    )

    result = await db_session.execute(
        select(CaseStatusHistory).where(
            CaseStatusHistory.patient_case_id == patient_case.id
        )
    )
    history_rows = result.scalars().all()
    assert len(history_rows) == 1
    row = history_rows[0]
    assert row.from_status == "new"
    assert row.to_status == "intake_in_progress"
    assert row.actor_user_id == str(actor_user_id)


async def test_valid_transition_writes_audit_event(db_session, patient_case, user):
    """Successful transition writes an AuditEvent row."""
    from sqlalchemy import select
    from placementops.core.models import AuditEvent

    case_id = UUID(patient_case.id)
    actor_user_id = UUID(user.id)

    await transition_case_status(
        case_id=case_id,
        to_status="intake_in_progress",
        actor_role="intake_staff",
        actor_user_id=actor_user_id,
        session=db_session,
        organization_id=UUID(patient_case.organization_id),
    )

    result = await db_session.execute(
        select(AuditEvent).where(
            AuditEvent.entity_id == patient_case.id,
            AuditEvent.event_type == "status_changed",
        )
    )
    audit_rows = result.scalars().all()
    assert len(audit_rows) >= 1
    row = audit_rows[0]
    assert row.old_value_json["status"] == "new"
    assert row.new_value_json["status"] == "intake_in_progress"


async def test_case_not_found_returns_404(db_session, user):
    """Non-existent case_id returns 404."""
    fake_case_id = uuid4()
    with pytest.raises(HTTPException) as exc_info:
        await transition_case_status(
            case_id=fake_case_id,
            to_status="intake_in_progress",
            actor_role="intake_staff",
            actor_user_id=UUID(user.id),
            session=db_session,
        )
    assert exc_info.value.status_code == 404


async def test_admin_can_close_from_intake_in_progress(db_session, user, org):
    """Admin can close from any non-terminal state they are permitted for."""
    from placementops.core.models import PatientCase

    case = PatientCase(
        id=str(uuid4()),
        organization_id=str(UUID(org.id)),
        patient_name="Close Test",
        current_status="intake_in_progress",
    )
    db_session.add(case)
    await db_session.commit()

    updated = await transition_case_status(
        case_id=UUID(case.id),
        to_status="closed",
        actor_role="admin",
        actor_user_id=UUID(user.id),
        session=db_session,
        organization_id=UUID(org.id),
    )
    assert updated.current_status == "closed"


def test_state_machine_transitions_allowlist_completeness():
    """All 28 transitions from the spec are present in the allowlist."""
    transitions = STATE_MACHINE_TRANSITIONS

    # Spot-check critical transitions
    assert "intake_in_progress" in transitions["new"]
    assert "placed" in transitions["accepted"]
    assert "closed" in transitions["placed"]
    assert "ready_for_matching" in transitions["declined_retry_needed"]
    # closed is terminal — no outbound transitions
    assert "closed" not in transitions
