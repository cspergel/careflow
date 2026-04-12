# @forgeplan-node: core-infrastructure
"""
AuditEvent ORM model — immutable append-only audit log for HIPAA compliance.

INSERT-ONLY: This model intentionally exposes NO update() or delete() class methods.
Immutability is enforced at two layers:
  1. This ORM class — no mutation methods exposed.
  2. Postgres BEFORE UPDATE OR DELETE trigger (created in migration 0002).
"""
# @forgeplan-spec: AC7
# @forgeplan-spec: AC8

from uuid import uuid4
from datetime import datetime

from sqlalchemy import ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from placementops.core.database import Base


class AuditEvent(Base):
    """
    Immutable audit log record.

    Usage:
        session.add(AuditEvent(...))  # Only valid write operation
        await session.commit()

    Never call session.delete(audit_event) or execute UPDATE on audit_events table.
    The Postgres trigger will raise an exception if attempted.
    """

    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(
        String, nullable=False
    )  # patient_case|outreach_action|user|...
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(
        String, nullable=False
    )  # status_changed|assessment_finalized|outreach_approved|...
    old_value_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    actor_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )  # null = system action
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())

    # --- INSERT-ONLY GUARD ---
    # The following class-level attributes are intentionally absent:
    #   update(), delete() — do NOT add them.
    # The Postgres trigger provides the hard enforcement at the DB layer.
