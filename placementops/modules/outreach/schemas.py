# @forgeplan-node: outreach-module
# @forgeplan-spec: AC1
# @forgeplan-spec: AC3
# @forgeplan-spec: AC9
# @forgeplan-spec: AC10
"""
Pydantic v2 schemas for outreach-module request/response models.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class OutreachActionCreate(BaseModel):
    """
    Payload for POST /api/v1/cases/{case_id}/outreach-actions (AC1, AC8).

    template_variables keys are validated against ALLOWED_VARIABLES before rendering.
    """

    model_config = ConfigDict(extra="forbid")

    facility_id: UUID | None = None
    template_id: UUID | None = None
    action_type: str = Field(
        ...,
        description="facility_outreach|internal_alert|cm_update|follow_up_reminder",
    )
    channel: str = Field(
        ...,
        description="email|phone_manual|task|sms|voicemail_drop|voice_ai",
    )
    draft_subject: str | None = None
    draft_body: str = Field(..., description="Required body content or template source")
    template_variables: dict[str, Any] | None = None


class OutreachActionPatch(BaseModel):
    """
    Payload for PATCH /api/v1/outreach-actions/{action_id} (AC3).

    Only draft_subject and draft_body may be patched.
    """

    model_config = ConfigDict(extra="forbid")

    draft_subject: str | None = None
    draft_body: str | None = None


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class OutreachActionResponse(BaseModel):
    """
    Response schema for OutreachAction records.

    Note: draft_body and draft_subject are included in draft/pending responses
    (needed by coordinators to review before sending). They are NEVER included
    in AuditEvent log entries per AC6 constraint.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    patient_case_id: UUID
    facility_id: UUID | None = None
    template_id: UUID | None = None
    action_type: str
    channel: str
    draft_subject: str | None = None
    draft_body: str
    approval_status: str
    approved_by_user_id: UUID | None = None
    approved_at: datetime | None = None
    sent_by_user_id: UUID | None = None
    sent_at: datetime | None = None
    delivery_status: str | None = None
    call_transcript_url: str | None = None
    call_duration_seconds: int | None = None
    call_outcome_summary: str | None = None
    created_at: datetime
    updated_at: datetime


class OutreachQueueResponse(BaseModel):
    """Response schema for GET /api/v1/queues/outreach (AC9)."""

    items: list[OutreachActionResponse]
    total: int
    page: int
    page_size: int


class OutreachTemplateResponse(BaseModel):
    """Response schema for a single OutreachTemplate record (AC10)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    template_name: str
    template_type: str
    subject_template: str | None = None
    body_template: str
    allowed_variables: Any  # JSONB — list or dict
    is_active: bool


class TemplateListResponse(BaseModel):
    """Response schema for GET /api/v1/templates/outreach (AC10)."""

    templates: list[OutreachTemplateResponse]
