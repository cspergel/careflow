# @forgeplan-node: admin-surfaces
# @forgeplan-spec: AC1, AC2, AC3, AC4, AC5, AC6, AC7, AC8, AC9, AC10
"""
Pydantic request/response schemas for the admin-surfaces module.

All response schemas use model_validate() against SQLAlchemy ORM rows.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------------------------
# User schemas
# ---------------------------------------------------------------------------


class UserResponse(BaseModel):
    """Full User record response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    email: str
    full_name: str
    role_key: str
    status: str
    timezone: str | None = None
    default_hospital_id: str | None = None
    created_at: datetime
    updated_at: datetime


class UserListResponse(BaseModel):
    """Paginated list of User records."""

    items: list[UserResponse]
    total: int
    page: int
    page_size: int


class AdminCreateUserRequest(BaseModel):
    """Request body for creating a new User."""

    email: str
    full_name: str
    role_key: str  # admin|intake_staff|clinical_reviewer|placement_coordinator|manager|read_only
    default_hospital_id: str | None = None
    timezone: str | None = None


class AdminUpdateUserRequest(BaseModel):
    """Request body for updating a User — all fields optional."""

    role_key: str | None = None
    status: str | None = None  # active|inactive
    full_name: str | None = None
    default_hospital_id: str | None = None
    timezone: str | None = None


# ---------------------------------------------------------------------------
# OutreachTemplate schemas
# ---------------------------------------------------------------------------


class TemplateResponse(BaseModel):
    """Full OutreachTemplate record response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    template_name: str
    template_type: str  # email|phone_manual|task|voice_ai_script
    subject_template: str | None = None
    body_template: str
    allowed_variables: list  # JSONB stored list (may contain str items)
    is_active: bool
    created_by_user_id: str
    created_at: datetime
    updated_at: datetime


class TemplateListResponse(BaseModel):
    """List of OutreachTemplate records."""

    items: list[TemplateResponse]
    total: int


class AdminCreateTemplateRequest(BaseModel):
    """Request body for creating an OutreachTemplate."""

    template_name: str
    template_type: str  # email|phone_manual|task|voice_ai_script
    subject_template: str | None = None
    body_template: str
    allowed_variables: list[str] = []
    is_active: bool = True


class AdminUpdateTemplateRequest(BaseModel):
    """Request body for updating an OutreachTemplate — all fields optional."""

    template_name: str | None = None
    template_type: str | None = None
    subject_template: str | None = None
    body_template: str | None = None
    allowed_variables: list[str] | None = None
    is_active: bool | None = None


# ---------------------------------------------------------------------------
# ImportJob schemas
# ---------------------------------------------------------------------------


class ImportJobResponse(BaseModel):
    """Full ImportJob record response including error_detail_json."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    created_by_user_id: str
    file_name: str
    file_size_bytes: int
    status: str
    column_mapping_json: dict | None = None
    total_rows: int | None = None
    created_count: int
    updated_count: int
    failed_count: int
    error_detail_json: dict | None = None
    created_at: datetime
    updated_at: datetime


class ImportListResponse(BaseModel):
    """Paginated list of ImportJob records."""

    items: list[ImportJobResponse]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Organization settings schemas
# ---------------------------------------------------------------------------


class OrgSettingsResponse(BaseModel):
    """Organization settings response."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    org_name: str
    settings_json: dict | None = None
    updated_at: datetime | None = None


class AdminUpdateOrgRequest(BaseModel):
    """Request body for updating organization settings."""

    org_name: str | None = None
    settings_json: dict | None = None


# ---------------------------------------------------------------------------
# Reference data schemas
# ---------------------------------------------------------------------------


class HospitalReferenceResponse(BaseModel):
    """HospitalReference record response — reflects actual ORM fields."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    hospital_name: str
    address: str | None = None


class DeclineReasonReferenceResponse(BaseModel):
    """DeclineReasonReference record response — reflects actual ORM fields."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    label: str
    display_order: int = 0


class PayerReferenceResponse(BaseModel):
    """PayerReference record response — reflects actual ORM fields."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    payer_name: str
    payer_type: str | None = None
