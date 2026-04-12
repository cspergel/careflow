# @forgeplan-node: core-infrastructure
"""
CaseStatusHistory ORM model — full audit trail of case status transitions.

Required for SLA computations in analytics-module.
Written by transition_case_status() on every status change.
"""
# @forgeplan-spec: AC9
# @forgeplan-spec: AC1

from uuid import uuid4
from datetime import datetime

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from placementops.core.database import Base


class CaseStatusHistory(Base):
    __tablename__ = "case_status_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )
    patient_case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("patient_cases.id"), nullable=False, index=True
    )
    from_status: Mapped[str | None] = mapped_column(String, nullable=True)  # null for initial create
    to_status: Mapped[str] = mapped_column(String, nullable=False)
    actor_user_id: Mapped[str] = mapped_column(String(36), nullable=False)
    transition_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    entered_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
