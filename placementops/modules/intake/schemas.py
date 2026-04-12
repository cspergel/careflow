# @forgeplan-node: intake-module
"""
Pydantic request/response schemas for the intake module.

All schemas use model_config = ConfigDict(from_attributes=True) to allow
construction from SQLAlchemy ORM instances.
"""
# @forgeplan-spec: AC1
# @forgeplan-spec: AC2
# @forgeplan-spec: AC3
# @forgeplan-spec: AC4
# @forgeplan-spec: AC5
# @forgeplan-spec: AC8
# @forgeplan-spec: AC9
# @forgeplan-spec: AC14

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Case create/patch schemas
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC1
class CaseCreateRequest(BaseModel):
    """Request body for POST /api/v1/cases."""

    patient_name: str = Field(..., min_length=1)
    hospital_id: UUID
    dob: date | None = None
    mrn: str | None = None
    hospital_unit: str | None = None
    room_number: str | None = None
    admission_date: date | None = None
    primary_diagnosis_text: str | None = None
    insurance_primary: str | None = None
    insurance_secondary: str | None = None
    patient_zip: str | None = None
    preferred_geography_text: str | None = None
    discharge_target_date: date | None = None
    priority_level: str | None = Field(
        default=None, pattern="^(routine|urgent|emergent)$"
    )


# @forgeplan-spec: AC4
class CasePatchRequest(BaseModel):
    """
    Request body for PATCH /api/v1/cases/{case_id}.

    Role-based field allowlists are enforced server-side in the service layer:
      - intake_staff: may update intake fields (all except assigned_coordinator_user_id)
      - placement_coordinator: may update priority_level and assigned_coordinator_user_id
    """

    hospital_unit: str | None = None
    room_number: str | None = None
    admission_date: date | None = None
    primary_diagnosis_text: str | None = None
    insurance_primary: str | None = None
    insurance_secondary: str | None = None
    patient_zip: str | None = None
    preferred_geography_text: str | None = None
    discharge_target_date: date | None = None
    priority_level: str | None = Field(
        default=None, pattern="^(routine|urgent|emergent)$"
    )
    assigned_coordinator_user_id: UUID | None = None


# ---------------------------------------------------------------------------
# Intake field issue schema
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC15
class IntakeFieldIssueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_case_id: UUID
    field_name: str
    issue_description: str
    resolved_flag: bool
    created_at: datetime


# ---------------------------------------------------------------------------
# Case response schemas
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC2
class PatientCaseSummary(BaseModel):
    """Lightweight case representation for list/queue endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    hospital_id: UUID | None
    patient_name: str
    dob: date | None
    mrn: str | None
    current_status: str
    priority_level: str | None
    intake_complete: bool
    active_case_flag: bool
    assigned_coordinator_user_id: UUID | None
    created_by_user_id: UUID | None
    updated_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime


# @forgeplan-spec: AC3
class PatientCaseDetail(BaseModel):
    """Full case detail including intake_field_issues."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    hospital_id: UUID | None
    patient_name: str
    dob: date | None
    mrn: str | None
    hospital_unit: str | None
    room_number: str | None
    admission_date: date | None
    primary_diagnosis_text: str | None
    insurance_primary: str | None
    insurance_secondary: str | None
    patient_zip: str | None
    preferred_geography_text: str | None
    discharge_target_date: date | None
    current_status: str
    priority_level: str | None
    intake_complete: bool
    active_case_flag: bool
    assigned_coordinator_user_id: UUID | None
    created_by_user_id: UUID | None
    updated_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime
    intake_field_issues: list[IntakeFieldIssueResponse] = Field(default_factory=list)


# @forgeplan-spec: AC2
class PaginatedCasesResponse(BaseModel):
    """Paginated list of case summaries."""

    cases: list[PatientCaseSummary]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Duplicate warning schema
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC14
class DuplicateWarning(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    existing_case_id: UUID
    patient_name: str
    dob: date | None
    hospital_id: UUID
    current_status: str


# @forgeplan-spec: AC1
class CreateCaseResponse(BaseModel):
    """Response for POST /api/v1/cases — includes case and optional duplicate warning."""

    model_config = ConfigDict(from_attributes=True)

    case: PatientCaseSummary
    duplicate_warning: DuplicateWarning | None = None


# ---------------------------------------------------------------------------
# Mark intake complete schema
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC5
class MarkIntakeCompleteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    case_id: UUID
    final_status: str
    message: str


# ---------------------------------------------------------------------------
# Assignment schemas
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC6
class AssignCaseRequest(BaseModel):
    """Request body for POST /api/v1/cases/{case_id}/assign."""

    user_id: UUID
    role: str


class AssignCaseResponse(BaseModel):
    case_id: UUID
    assigned_user_id: UUID
    assigned_role: str
    message: str


# ---------------------------------------------------------------------------
# Status transition schema
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC7
class StatusTransitionRequest(BaseModel):
    """Request body for POST /api/v1/cases/{case_id}/status-transition."""

    to_status: str
    transition_reason: str | None = None


# ---------------------------------------------------------------------------
# Import schemas
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC8
class ImportJobResponse(BaseModel):
    """Response for import job endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    created_by_user_id: UUID
    file_name: str
    file_size_bytes: int
    status: str
    column_mapping_json: dict[str, Any] | None
    total_rows: int | None
    created_count: int
    updated_count: int
    failed_count: int
    error_detail_json: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


# @forgeplan-spec: AC9
class ColumnMappingEntry(BaseModel):
    source_column: str
    destination_field: str


class ColumnMappingRequest(BaseModel):
    """Request body for POST /api/v1/imports/{id}/map-columns."""

    mappings: list[ColumnMappingEntry]


# @forgeplan-spec: AC10
class RowValidationResult(BaseModel):
    row_number: int
    is_valid: bool
    errors: list[str] = Field(default_factory=list)


class ValidateImportResponse(BaseModel):
    import_job_id: UUID
    status: str
    total_rows: int
    row_results: list[RowValidationResult]


# ---------------------------------------------------------------------------
# Queue schema
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC13
class IntakeQueueResponse(BaseModel):
    """Intake queue response for GET /api/v1/queues/intake."""

    cases: list[PatientCaseSummary]
    total: int
    page: int
    page_size: int
