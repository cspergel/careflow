# @forgeplan-node: core-infrastructure
"""PlacementOutcome ORM model — outcome record for a patient case."""
# @forgeplan-spec: AC1

from uuid import uuid4
from datetime import datetime

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from placementops.core.database import Base


class PlacementOutcome(Base):
    __tablename__ = "placement_outcomes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    patient_case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("patient_cases.id"), nullable=False, index=True
    )
    facility_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("facilities.id"), nullable=True
    )

    outcome_type: Mapped[str] = mapped_column(
        String, nullable=False
    )  # pending_review|accepted|declined|placed|family_declined|withdrawn
    decline_reason_code: Mapped[str | None] = mapped_column(
        String, nullable=True
    )  # → decline_reason_reference.code
    decline_reason_text: Mapped[str | None] = mapped_column(String, nullable=True)
    recorded_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
