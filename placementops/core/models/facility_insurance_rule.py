# @forgeplan-node: core-infrastructure
"""FacilityInsuranceRule ORM model — payer acceptance rules per facility."""
# @forgeplan-spec: AC1

from uuid import uuid4
from datetime import datetime

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from placementops.core.database import Base


class FacilityInsuranceRule(Base):
    __tablename__ = "facility_insurance_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    facility_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("facilities.id"), nullable=False, index=True
    )
    payer_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("payer_reference.id"), nullable=False
    )
    payer_name: Mapped[str] = mapped_column(String, nullable=False)  # denormalized for display
    accepted_status: Mapped[str] = mapped_column(
        String, nullable=False
    )  # accepted|conditional|not_accepted
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )
