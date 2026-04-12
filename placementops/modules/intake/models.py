# @forgeplan-node: intake-module
"""
Local ORM models for the intake module.

IntakeFieldIssue and CaseAssignment are not defined in core-infrastructure
models. They are defined here as they are intake-specific entities.

CONCERN: These models require DB migrations or Base.metadata.create_all()
for test setup. The orchestrator must handle migrations.
"""
# @forgeplan-decision: D-intake-1-local-models -- IntakeFieldIssue and CaseAssignment defined in intake module (not core). Why: these models do not exist in core/models and are intake-specific; defining locally avoids modifying core file_scope while keeping the data models available

from uuid import uuid4
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from placementops.core.database import Base


# @forgeplan-spec: AC15
class IntakeFieldIssue(Base):
    """
    Tracks validation failures for individual fields on a PatientCase during intake.

    resolved_flag is set to True when the field is re-submitted with a valid value.
    """

    __tablename__ = "intake_field_issues"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    patient_case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("patient_cases.id"), nullable=False, index=True
    )
    field_name: Mapped[str] = mapped_column(String, nullable=False)
    issue_description: Mapped[str] = mapped_column(String, nullable=False)
    resolved_flag: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )


# @forgeplan-spec: AC6
class CaseAssignment(Base):
    """
    Records every case assignment event (coordinator, clinical_reviewer, etc.).

    A single case may have multiple assignments over its lifetime.
    When a placement_coordinator is assigned, PatientCase.assigned_coordinator_user_id
    is also updated (denormalized for queue performance).
    """

    __tablename__ = "case_assignments"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    patient_case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("patient_cases.id"), nullable=False, index=True
    )
    assigned_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    assigned_role: Mapped[str] = mapped_column(String, nullable=False)
    assigned_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
