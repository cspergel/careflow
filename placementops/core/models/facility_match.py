# @forgeplan-node: core-infrastructure
"""FacilityMatch ORM model — scored match record linking patient case to candidate facility."""
# @forgeplan-spec: AC1

from uuid import uuid4
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, JSON, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from placementops.core.database import Base


class FacilityMatch(Base):
    __tablename__ = "facility_matches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    patient_case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("patient_cases.id"), nullable=False, index=True
    )
    facility_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("facilities.id"), nullable=False
    )
    assessment_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("clinical_assessments.id"), nullable=True
    )

    overall_score: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    payer_fit_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    clinical_fit_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    geography_score: Mapped[float | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )  # 0.0 when patient_zip or facility coordinates null
    preference_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    level_of_care_fit_score: Mapped[float | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )  # 20% weight component; stored separately for auditability

    rank_order: Mapped[int] = mapped_column(Integer, nullable=False)
    is_recommended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    selected_for_outreach: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )  # coordinator marks; multiple simultaneous allowed

    blockers_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # hard exclusions
    explanation_text: Mapped[str | None] = mapped_column(String, nullable=True)
    generated_by: Mapped[str] = mapped_column(
        String, nullable=False, default="rules_engine"
    )  # rules_engine|voice_ai
    generated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
