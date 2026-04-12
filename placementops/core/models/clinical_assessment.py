# @forgeplan-node: core-infrastructure
"""ClinicalAssessment ORM model — structured clinical review feeding matching engine."""
# @forgeplan-spec: AC1

from uuid import uuid4
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from placementops.core.database import Base


class ClinicalAssessment(Base):
    __tablename__ = "clinical_assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    patient_case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("patient_cases.id"), nullable=False, index=True
    )
    reviewer_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )

    recommended_level_of_care: Mapped[str] = mapped_column(String, nullable=False)  # snf|irf|ltach
    confidence_level: Mapped[str | None] = mapped_column(String, nullable=True)
    clinical_summary: Mapped[str | None] = mapped_column(String, nullable=True)
    rehab_tolerance: Mapped[str | None] = mapped_column(String, nullable=True)
    mobility_status: Mapped[str | None] = mapped_column(String, nullable=True)

    # Clinical capability flags — Python attribute names match the DB column names and
    # the FacilityCapabilities fields exactly, enabling direct comparison in the matching
    # engine without a translation layer (spec constraint).
    accepts_oxygen_therapy: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accepts_trach: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accepts_vent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accepts_hd: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    in_house_hemodialysis: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accepts_peritoneal_dialysis: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accepts_wound_vac: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accepts_iv_antibiotics: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accepts_tpn: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accepts_isolation_cases: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accepts_behavioral_complexity: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accepts_bariatric: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    accepts_memory_care: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Narrative fields — not used for hard-exclusion matching
    psych_behavior_flags: Mapped[str | None] = mapped_column(
        String, nullable=True
    )  # narrative notes — NOT used for hard exclusion
    special_equipment_needs: Mapped[str | None] = mapped_column(String, nullable=True)
    barriers_to_placement: Mapped[str | None] = mapped_column(String, nullable=True)
    payer_notes: Mapped[str | None] = mapped_column(String, nullable=True)
    family_preference_notes: Mapped[str | None] = mapped_column(String, nullable=True)

    review_status: Mapped[str] = mapped_column(String, nullable=False, default="draft")  # draft|finalized

    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )
