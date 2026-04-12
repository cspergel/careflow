# @forgeplan-node: core-infrastructure
"""FacilityCapabilities ORM model — clinical capability matrix (one row per facility)."""
# @forgeplan-spec: AC1

from uuid import uuid4
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from placementops.core.database import Base


class FacilityCapabilities(Base):
    __tablename__ = "facility_capabilities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    facility_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("facilities.id"), unique=True, nullable=False
    )

    # Level of care
    accepts_snf: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accepts_irf: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accepts_ltach: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Clinical capabilities — must exactly match ClinicalAssessment field names for matching engine
    accepts_trach: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accepts_vent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accepts_hd: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # hemodialysis
    in_house_hemodialysis: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accepts_peritoneal_dialysis: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accepts_wound_vac: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accepts_iv_antibiotics: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accepts_tpn: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accepts_bariatric: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accepts_behavioral_complexity: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accepts_memory_care: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accepts_isolation_cases: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accepts_oxygen_therapy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Admission timing
    weekend_admissions: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    after_hours_admissions: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    last_verified_at: Mapped[datetime | None] = mapped_column(nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )
