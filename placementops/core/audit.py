# @forgeplan-node: core-infrastructure
"""
emit_audit_event() — reusable helper for writing AuditEvent rows.

Insert-only pattern: callers add the row and control the transaction.
No update or delete operations are exposed.
"""
# @forgeplan-spec: AC8

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.models.audit_event import AuditEvent


# @forgeplan-decision: D-core-5-audit-helper-no-flush -- emit_audit_event does not flush/commit. Why: caller owns the transaction; flushing here would break callers that batch multiple inserts in one commit
async def emit_audit_event(
    session: AsyncSession,
    organization_id: UUID,
    entity_type: str,
    entity_id: UUID,
    event_type: str,
    actor_user_id: UUID | None,
    old_value: dict | None = None,
    new_value: dict | None = None,
) -> None:
    """
    Insert an AuditEvent row.

    Insert-only pattern — no update/delete on AuditEvent.
    Caller controls when to flush/commit the surrounding transaction.

    Args:
        session:          Active AsyncSession — row is added but not committed.
        organization_id:  Tenant ID for the event.
        entity_type:      Domain entity class, e.g. "patient_case", "outreach_action", "user".
        entity_id:        UUID of the affected entity.
        event_type:       Action performed, e.g. "status_changed", "outreach_approved", "user_created".
        actor_user_id:    UUID of the acting user, or None for system-initiated actions.
        old_value:        Optional dict of field values before the change.
        new_value:        Optional dict of field values after the change.
    """
    audit_row = AuditEvent(
        organization_id=str(organization_id),
        entity_type=entity_type,
        entity_id=str(entity_id),
        event_type=event_type,
        old_value_json=old_value,
        new_value_json=new_value,
        actor_user_id=str(actor_user_id) if actor_user_id is not None else None,
    )
    session.add(audit_row)
    # Do not flush/commit — caller controls the transaction boundary
