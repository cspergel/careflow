# @forgeplan-node: core-infrastructure
"""
Tests for AuditEvent immutability — AC7.

Tests:
  - INSERT works normally
  - UPDATE raises DBAPIError (Postgres trigger blocks it)
  - DELETE raises DBAPIError (Postgres trigger blocks it)
  - ORM model exposes no update() or delete() methods

Note: The Postgres trigger test requires a real Postgres instance.
The ORM structural test runs on SQLite (unit test, no DB required).
"""
# @forgeplan-spec: AC7

import pytest
from uuid import uuid4

from placementops.core.models.audit_event import AuditEvent


def test_audit_event_model_has_no_update_method():
    """AC7: AuditEvent class exposes no class-level update() method."""
    assert not hasattr(AuditEvent, "update"), (
        "AuditEvent must not expose an update() method"
    )


def test_audit_event_model_has_no_delete_method():
    """AC7: AuditEvent class exposes no class-level delete() method."""
    assert not hasattr(AuditEvent, "delete"), (
        "AuditEvent must not expose a delete() method"
    )


@pytest.mark.asyncio
async def test_audit_event_insert_succeeds(db_session, org):
    """AuditEvent can be inserted via session.add()."""
    event = AuditEvent(
        organization_id=str(org.id),
        entity_type="patient_case",
        entity_id=str(uuid4()),
        event_type="status_changed",
        old_value_json={"status": "new"},
        new_value_json={"status": "intake_in_progress"},
        actor_user_id=None,
    )
    db_session.add(event)
    await db_session.commit()

    # Verify it was persisted
    fetched = await db_session.get(AuditEvent, event.id)
    assert fetched is not None
    assert fetched.event_type == "status_changed"


@pytest.mark.asyncio
@pytest.mark.postgres_required
async def test_audit_event_update_raises_db_error(db_session, org):
    """
    AC7: Raw SQL UPDATE on audit_events raises sqlalchemy.exc.DBAPIError.

    This test requires a real Postgres instance with the trigger installed.
    Marked as postgres_required — skipped in unit test mode.
    """
    import sqlalchemy.exc

    event = AuditEvent(
        organization_id=str(org.id),
        entity_type="test",
        entity_id=str(uuid4()),
        event_type="test_event",
        actor_user_id=None,
    )
    db_session.add(event)
    await db_session.commit()

    with pytest.raises(sqlalchemy.exc.DBAPIError):
        await db_session.execute(
            f"UPDATE audit_events SET event_type = 'hacked' WHERE id = '{event.id}'"
        )
        await db_session.commit()


@pytest.mark.asyncio
@pytest.mark.postgres_required
async def test_audit_event_delete_raises_db_error(db_session, org):
    """
    AC7: Raw SQL DELETE on audit_events raises sqlalchemy.exc.DBAPIError.

    This test requires a real Postgres instance with the trigger installed.
    """
    import sqlalchemy.exc

    event = AuditEvent(
        organization_id=str(org.id),
        entity_type="test",
        entity_id=str(uuid4()),
        event_type="test_event",
        actor_user_id=None,
    )
    db_session.add(event)
    await db_session.commit()

    with pytest.raises(sqlalchemy.exc.DBAPIError):
        await db_session.execute(
            f"DELETE FROM audit_events WHERE id = '{event.id}'"
        )
        await db_session.commit()
