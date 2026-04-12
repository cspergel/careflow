# @forgeplan-node: core-infrastructure
"""PatientCase ORM model — central case record for the 14-state placement workflow."""
# @forgeplan-spec: AC1

from uuid import uuid4
from datetime import date, datetime

from sqlalchemy import Boolean, Date, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from placementops.core.database import Base

# 14 valid case statuses — authoritative list
CASE_STATUSES = [
    "new",
    "intake_in_progress",
    "intake_complete",
    "needs_clinical_review",
    "under_clinical_review",
    "ready_for_matching",
    "facility_options_generated",
    "outreach_pending_approval",
    "outreach_in_progress",
    "pending_facility_response",
    "accepted",
    "declined_retry_needed",
    "placed",
    "closed",
]


class PatientCase(Base):
    __tablename__ = "patient_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )
    hospital_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("hospital_reference.id"), nullable=True
    )

    # Patient demographics
    patient_name: Mapped[str] = mapped_column(String, nullable=False)
    dob: Mapped[date | None] = mapped_column(Date, nullable=True)
    mrn: Mapped[str | None] = mapped_column(String, nullable=True)

    # Hospital placement context
    hospital_unit: Mapped[str | None] = mapped_column(String, nullable=True)
    room_number: Mapped[str | None] = mapped_column(String, nullable=True)
    admission_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Clinical context
    primary_diagnosis_text: Mapped[str | None] = mapped_column(String, nullable=True)
    insurance_primary: Mapped[str | None] = mapped_column(String, nullable=True)
    insurance_secondary: Mapped[str | None] = mapped_column(String, nullable=True)
    patient_zip: Mapped[str | None] = mapped_column(String, nullable=True)
    preferred_geography_text: Mapped[str | None] = mapped_column(String, nullable=True)
    discharge_target_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Workflow state
    current_status: Mapped[str] = mapped_column(String, nullable=False, default="new")
    priority_level: Mapped[str | None] = mapped_column(String, nullable=True)  # routine|urgent|emergent
    intake_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active_case_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Assignments
    assigned_coordinator_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    updated_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_patient_cases_org_status", "organization_id", "current_status"),
        Index("ix_patient_cases_active", "organization_id", "active_case_flag"),
    )
