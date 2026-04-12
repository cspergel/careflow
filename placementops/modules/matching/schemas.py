# @forgeplan-node: matching-module
# @forgeplan-spec: AC1
# @forgeplan-spec: AC2
# @forgeplan-spec: AC3
# @forgeplan-spec: AC4
# @forgeplan-spec: AC5
# @forgeplan-spec: AC6
# @forgeplan-spec: AC7
# @forgeplan-spec: AC8
# @forgeplan-spec: AC9
# @forgeplan-spec: AC10
# @forgeplan-spec: AC11
# @forgeplan-spec: AC12
# @forgeplan-spec: AC13
# @forgeplan-spec: AC14
# @forgeplan-spec: AC15
# @forgeplan-spec: AC16
# @forgeplan-spec: AC17
"""
Pydantic v2 schemas for the matching module.

Request/response shapes for:
  - POST /api/v1/cases/{case_id}/matches/generate
  - GET  /api/v1/cases/{case_id}/matches
  - PATCH /api/v1/cases/{case_id}/matches/{match_id}/select
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class MatchGenerateRequest(BaseModel):
    """
    Optional request body for POST .../matches/generate.

    assessment_id is optional; when omitted the engine resolves
    the latest finalized assessment automatically.
    """

    assessment_id: UUID | None = Field(
        default=None,
        description=(
            "When provided, must reference a ClinicalAssessment with "
            "review_status=finalized for the given case_id. "
            "When omitted, engine resolves the latest finalized assessment."
        ),
    )


class BlockerDetailSchema(BaseModel):
    """One hard-exclusion reason for a facility."""

    field: str
    reason: str

    model_config = {"from_attributes": True}


class FacilityMatchResponse(BaseModel):
    """
    Full FacilityMatch record returned from GET and POST generate endpoints.

    All component scores are included for auditability (AC10).
    explanation_text is stored verbatim — never regenerated on read (AC11).
    """

    # @forgeplan-spec: AC10
    # @forgeplan-spec: AC11
    id: UUID
    patient_case_id: UUID
    facility_id: UUID
    assessment_id: UUID | None

    overall_score: float
    payer_fit_score: float | None
    clinical_fit_score: float | None
    geography_score: float | None
    preference_score: float | None
    level_of_care_fit_score: float | None

    rank_order: int
    is_recommended: bool
    selected_for_outreach: bool

    blockers_json: list[dict[str, Any]] | None = Field(default=None)
    explanation_text: str | None

    generated_by: str
    generated_at: datetime

    model_config = {"from_attributes": True}


class MatchListResponse(BaseModel):
    """Response containing an ordered list of FacilityMatch records."""

    matches: list[FacilityMatchResponse]
    total: int

    model_config = {"from_attributes": True}


class SelectToggleResponse(BaseModel):
    """Response after PATCH .../matches/{match_id}/select."""

    # @forgeplan-spec: AC14
    match_id: UUID
    facility_id: UUID
    selected_for_outreach: bool
    message: str

    model_config = {"from_attributes": True}
