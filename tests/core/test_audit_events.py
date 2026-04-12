# @forgeplan-node: core-infrastructure
"""
Tests that AuditEvent rows are written for key domain actions — AC8.

Tests:
  (a) Case status transition writes audit row with entity_type=patient_case, event_type=status_changed
  (b) AuditEvent row structure: old_value_json, new_value_json, actor_user_id correct
"""
# @forgeplan-spec: AC8

import pytest
from uuid import uuid4, UUID
from sqlalchemy import select

from placementops.core.models import AuditEvent
from placementops.core.state_machine import transition_case_status
from placementops.core.audit import emit_audit_event

pytestmark = pytest.mark.asyncio


async def test_status_transition_writes_audit_event(db_session, patient_case, user):
    """AC8a: Status transition writes AuditEvent with correct fields."""
    case_id = UUID(patient_case.id)
    actor_user_id = UUID(user.id)
    org_id = UUID(patient_case.organization_id)

    await transition_case_status(
        case_id=case_id,
        to_status="intake_in_progress",
        actor_role="intake_staff",
        actor_user_id=actor_user_id,
        session=db_session,
        organization_id=org_id,
    )

    result = await db_session.execute(
        select(AuditEvent).where(
            AuditEvent.entity_id == patient_case.id,
            AuditEvent.entity_type == "patient_case",
            AuditEvent.event_type == "status_changed",
        )
    )
    rows = result.scalars().all()
    assert len(rows) >= 1, "Expected at least one audit_events row for status_changed"


async def test_audit_event_has_correct_old_and_new_values(db_session, patient_case, user):
    """AC8: Audit row has correct old_value_json and new_value_json."""
    case_id = UUID(patient_case.id)
    actor_user_id = UUID(user.id)
    org_id = UUID(patient_case.organization_id)

    await transition_case_status(
        case_id=case_id,
        to_status="intake_in_progress",
        actor_role="intake_staff",
        actor_user_id=actor_user_id,
        session=db_session,
        organization_id=org_id,
    )

    result = await db_session.execute(
        select(AuditEvent).where(
            AuditEvent.entity_id == patient_case.id,
        )
    )
    row = result.scalar_one()

    assert row.old_value_json == {"status": "new"}
    assert row.new_value_json == {"status": "intake_in_progress"}
    assert row.actor_user_id == str(actor_user_id)
    assert row.organization_id == patient_case.organization_id


async def test_audit_event_written_directly(db_session, org):
    """Manually inserted AuditEvent is persisted correctly."""
    event = AuditEvent(
        organization_id=str(org.id),
        entity_type="outreach_action",
        entity_id=str(uuid4()),
        event_type="outreach_approved",
        old_value_json={"approval_status": "pending_approval"},
        new_value_json={"approval_status": "approved"},
        actor_user_id=None,
    )
    db_session.add(event)
    await db_session.commit()

    fetched = await db_session.get(AuditEvent, event.id)
    assert fetched.event_type == "outreach_approved"
    assert fetched.new_value_json["approval_status"] == "approved"


async def test_multiple_transitions_write_multiple_audit_events(db_session, user, org):
    """Multiple transitions produce multiple AuditEvent rows for the same case."""
    from placementops.core.models import PatientCase

    case = PatientCase(
        id=str(uuid4()),
        organization_id=str(org.id),
        patient_name="Multi-Transition Test",
        current_status="new",
    )
    db_session.add(case)
    await db_session.commit()

    org_id = UUID(org.id)
    actor_user_id = UUID(user.id)
    case_id = UUID(case.id)

    await transition_case_status(
        case_id=case_id,
        to_status="intake_in_progress",
        actor_role="intake_staff",
        actor_user_id=actor_user_id,
        session=db_session,
        organization_id=org_id,
    )

    await transition_case_status(
        case_id=case_id,
        to_status="intake_complete",
        actor_role="intake_staff",
        actor_user_id=actor_user_id,
        session=db_session,
        organization_id=org_id,
    )

    result = await db_session.execute(
        select(AuditEvent).where(
            AuditEvent.entity_id == case.id,
            AuditEvent.event_type == "status_changed",
        )
    )
    rows = result.scalars().all()
    assert len(rows) == 2


# ---------------------------------------------------------------------------
# emit_audit_event() helper tests — AC8(b) and AC8(c)
# These test the helper directly, independent of the outreach/admin modules
# which don't exist yet. The outreach and user modules will call this helper;
# here we verify the helper itself writes the correct row structure.
# ---------------------------------------------------------------------------


async def test_transition_case_status_produces_correct_audit_fields(db_session, patient_case, user, org):
    """AC8: transition_case_status writes AuditEvent with entity_type=patient_case, event_type=status_changed."""
    case_id = UUID(patient_case.id)
    actor_user_id = UUID(user.id)
    org_id = UUID(patient_case.organization_id)

    await transition_case_status(
        case_id=case_id,
        to_status="intake_in_progress",
        actor_role="intake_staff",
        actor_user_id=actor_user_id,
        session=db_session,
        organization_id=org_id,
    )

    result = await db_session.execute(
        select(AuditEvent).where(
            AuditEvent.entity_id == patient_case.id,
            AuditEvent.entity_type == "patient_case",
            AuditEvent.event_type == "status_changed",
        )
    )
    row = result.scalars().first()
    assert row is not None, "AuditEvent row for status_changed must exist"
    assert row.old_value_json == {"status": "new"}
    assert row.new_value_json == {"status": "intake_in_progress"}
    assert row.actor_user_id == str(actor_user_id)
    assert row.organization_id == str(org_id)


async def test_emit_audit_event_outreach_context(db_session, org):
    """AC8(b): emit_audit_event writes outreach_action/outreach_approved row correctly."""
    org_id = UUID(org.id)
    outreach_id = uuid4()

    await emit_audit_event(
        session=db_session,
        organization_id=org_id,
        entity_type="outreach_action",
        entity_id=outreach_id,
        event_type="outreach_approved",
        actor_user_id=None,  # system action
        old_value={"approval_status": "pending_approval"},
        new_value={"approval_status": "approved"},
    )
    await db_session.commit()

    result = await db_session.execute(
        select(AuditEvent).where(
            AuditEvent.entity_id == str(outreach_id),
            AuditEvent.entity_type == "outreach_action",
            AuditEvent.event_type == "outreach_approved",
        )
    )
    row = result.scalar_one()
    assert row.old_value_json == {"approval_status": "pending_approval"}
    assert row.new_value_json == {"approval_status": "approved"}
    assert row.actor_user_id is None
    assert row.organization_id == str(org_id)


async def test_emit_audit_event_user_context(db_session, org, user):
    """AC8(c): emit_audit_event writes user/user_created row correctly."""
    org_id = UUID(org.id)
    new_user_id = uuid4()
    actor_user_id = UUID(user.id)

    await emit_audit_event(
        session=db_session,
        organization_id=org_id,
        entity_type="user",
        entity_id=new_user_id,
        event_type="user_created",
        actor_user_id=actor_user_id,
        old_value=None,
        new_value={"email": "newuser@example.com", "role_key": "intake_staff"},
    )
    await db_session.commit()

    result = await db_session.execute(
        select(AuditEvent).where(
            AuditEvent.entity_id == str(new_user_id),
            AuditEvent.entity_type == "user",
            AuditEvent.event_type == "user_created",
        )
    )
    row = result.scalar_one()
    assert row.old_value_json is None
    assert row.new_value_json == {"email": "newuser@example.com", "role_key": "intake_staff"}
    assert row.actor_user_id == str(actor_user_id)
    assert row.organization_id == str(org_id)
