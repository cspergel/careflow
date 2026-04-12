# @forgeplan-node: clinical-module
"""
Pydantic schemas for the clinical module.

Field names in AssessmentCreateRequest / AssessmentUpdateRequest use the ORM
(accepts_*) names as the canonical Python attribute names, which exactly match
FacilityCapabilities field names enabling direct comparison in the matching engine.

AC8 spec lists short names (trach, vent, wound_vac_needs, …).  To satisfy both
the spec API surface and the ORM/matching-engine naming constraint, each clinical
capability flag in the request schemas declares an AliasChoices so the API
accepts either the spec short name *or* the canonical accepts_* name.
The response schema serialises using the canonical accepts_* names (matching ORM).
"""
# @forgeplan-spec: AC3
# @forgeplan-spec: AC4
# @forgeplan-spec: AC5
# @forgeplan-spec: AC6
# @forgeplan-spec: AC7
# @forgeplan-spec: AC8

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class AssignReviewerRequest(BaseModel):
    """POST /cases/{case_id}/assign — assign a clinical reviewer."""

    # @forgeplan-spec: AC2
    user_id: UUID
    role: str = Field(default="clinical_reviewer")


class AssessmentCreateRequest(BaseModel):
    """POST /cases/{case_id}/assessments — create a draft assessment.

    recommended_level_of_care is optional at draft creation;
    required when review_status=finalized (AC6, AC7).
    All boolean flags default to False when absent (spec constraint).

    AC8 spec names (trach, vent, wound_vac_needs, oxygen_required,
    memory_care_needed, behavioral_complexity_flag, bariatric_needs,
    iv_antibiotics, tpn, isolation_precautions) are accepted as aliases
    alongside the canonical accepts_* ORM names.  populate_by_name=True
    means the accepts_* names are also accepted directly.
    """

    # @forgeplan-spec: AC3
    # @forgeplan-spec: AC8
    model_config = ConfigDict(populate_by_name=True)

    recommended_level_of_care: str = Field(default="")

    # Clinical capability flags — canonical names match FacilityCapabilities/ORM exactly.
    # Each field also accepts the AC8 spec short name via AliasChoices.
    accepts_trach: bool = Field(
        default=False,
        validation_alias=AliasChoices("accepts_trach", "trach"),
    )
    accepts_vent: bool = Field(
        default=False,
        validation_alias=AliasChoices("accepts_vent", "vent"),
    )
    accepts_hd: bool = False
    in_house_hemodialysis: bool = False
    accepts_peritoneal_dialysis: bool = False
    accepts_wound_vac: bool = Field(
        default=False,
        validation_alias=AliasChoices("accepts_wound_vac", "wound_vac_needs"),
    )
    accepts_iv_antibiotics: bool = Field(
        default=False,
        validation_alias=AliasChoices("accepts_iv_antibiotics", "iv_antibiotics"),
    )
    accepts_tpn: bool = Field(
        default=False,
        validation_alias=AliasChoices("accepts_tpn", "tpn"),
    )
    accepts_isolation_cases: bool = Field(
        default=False,
        validation_alias=AliasChoices("accepts_isolation_cases", "isolation_precautions"),
    )
    accepts_behavioral_complexity: bool = Field(
        default=False,
        validation_alias=AliasChoices("accepts_behavioral_complexity", "behavioral_complexity_flag"),
    )
    accepts_bariatric: bool = Field(
        default=False,
        validation_alias=AliasChoices("accepts_bariatric", "bariatric_needs"),
    )
    accepts_memory_care: bool = Field(
        default=False,
        validation_alias=AliasChoices("accepts_memory_care", "memory_care_needed"),
    )
    accepts_oxygen_therapy: bool = Field(
        default=False,
        validation_alias=AliasChoices("accepts_oxygen_therapy", "oxygen_required"),
    )

    # Narrative / non-matching fields
    rehab_tolerance: str | None = None
    mobility_status: str | None = None
    psych_behavior_flags: str | None = None
    special_equipment_needs: str | None = None
    barriers_to_placement: str | None = None
    payer_notes: str | None = None
    family_preference_notes: str | None = None
    confidence_level: str | None = None
    clinical_summary: str | None = None


class AssessmentUpdateRequest(BaseModel):
    """PATCH /assessments/{assessment_id} — update fields and create a new version row.

    When review_status=finalized, recommended_level_of_care must be non-empty (AC6/AC7).
    All fields are optional — only supplied fields are changed.

    AC8 spec short names are accepted as aliases alongside the canonical accepts_* names
    (see AssessmentCreateRequest for the full alias mapping).
    """

    # @forgeplan-spec: AC4
    # @forgeplan-spec: AC6
    # @forgeplan-spec: AC7
    # @forgeplan-spec: AC8
    model_config = ConfigDict(populate_by_name=True)

    review_status: str | None = None  # "draft" | "finalized"
    recommended_level_of_care: str | None = None

    # Clinical capability flags — accepts both canonical and AC8 spec short names
    accepts_trach: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("accepts_trach", "trach"),
    )
    accepts_vent: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("accepts_vent", "vent"),
    )
    accepts_hd: bool | None = None
    in_house_hemodialysis: bool | None = None
    accepts_peritoneal_dialysis: bool | None = None
    accepts_wound_vac: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("accepts_wound_vac", "wound_vac_needs"),
    )
    accepts_iv_antibiotics: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("accepts_iv_antibiotics", "iv_antibiotics"),
    )
    accepts_tpn: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("accepts_tpn", "tpn"),
    )
    accepts_isolation_cases: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("accepts_isolation_cases", "isolation_precautions"),
    )
    accepts_behavioral_complexity: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("accepts_behavioral_complexity", "behavioral_complexity_flag"),
    )
    accepts_bariatric: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("accepts_bariatric", "bariatric_needs"),
    )
    accepts_memory_care: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("accepts_memory_care", "memory_care_needed"),
    )
    accepts_oxygen_therapy: bool | None = Field(
        default=None,
        validation_alias=AliasChoices("accepts_oxygen_therapy", "oxygen_required"),
    )

    # Narrative fields
    rehab_tolerance: str | None = None
    mobility_status: str | None = None
    psych_behavior_flags: str | None = None
    special_equipment_needs: str | None = None
    barriers_to_placement: str | None = None
    payer_notes: str | None = None
    family_preference_notes: str | None = None
    confidence_level: str | None = None
    clinical_summary: str | None = None

    @model_validator(mode="after")
    def check_finalization_requires_loc(self) -> "AssessmentUpdateRequest":
        """Enforce recommended_level_of_care when finalizing (AC7)."""
        if self.review_status == "finalized":
            if not self.recommended_level_of_care:
                raise ValueError(
                    "recommended_level_of_care is required when review_status=finalized"
                )
        return self


class BackwardTransitionRequest(BaseModel):
    """POST /cases/{case_id}/status-transition (backward: under_clinical_review→needs_clinical_review).

    transition_reason is REQUIRED for backward transitions (AC9).
    """

    # @forgeplan-spec: AC9
    to_status: str
    transition_reason: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def check_backward_reason_required(self) -> "BackwardTransitionRequest":
        if self.to_status == "needs_clinical_review" and not self.transition_reason:
            raise ValueError(
                "transition_reason is required when transitioning back to needs_clinical_review"
            )
        return self


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class AssignReviewerResponse(BaseModel):
    """Response for POST /cases/{case_id}/assign."""

    case_id: UUID
    assigned_user_id: UUID
    new_case_status: str
    message: str

    model_config = {"from_attributes": True}


class AssessmentResponse(BaseModel):
    """Single ClinicalAssessment row — returned by create, update, and GET endpoints."""

    # @forgeplan-spec: AC3
    # @forgeplan-spec: AC4
    # @forgeplan-spec: AC5
    id: UUID
    patient_case_id: UUID
    reviewer_user_id: UUID
    review_status: str

    recommended_level_of_care: str
    confidence_level: str | None
    clinical_summary: str | None
    rehab_tolerance: str | None
    mobility_status: str | None

    # Clinical capability flags
    accepts_trach: bool
    accepts_vent: bool
    accepts_hd: bool
    in_house_hemodialysis: bool
    accepts_peritoneal_dialysis: bool
    accepts_wound_vac: bool
    accepts_iv_antibiotics: bool
    accepts_tpn: bool
    accepts_isolation_cases: bool
    accepts_behavioral_complexity: bool
    accepts_bariatric: bool
    accepts_memory_care: bool
    accepts_oxygen_therapy: bool

    # Narrative fields
    psych_behavior_flags: str | None
    special_equipment_needs: str | None
    barriers_to_placement: str | None
    payer_notes: str | None
    family_preference_notes: str | None

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AssessmentVersionEntry(AssessmentResponse):
    """AssessmentResponse extended with a 1-based version_sequence counter.

    version_sequence is the ordinal position of this assessment row in the
    chronological (created_at asc) history for the patient case.  It is
    computed at query time in the service layer — not stored in the DB.

    AC spec: AssessmentVersionEntry.version_sequence: integer
    """

    # @forgeplan-spec: AC8
    version_sequence: int

    model_config = {"from_attributes": True}


class AssessmentListResponse(BaseModel):
    """GET /cases/{case_id}/assessments — ordered list of assessment versions."""

    # @forgeplan-spec: AC5
    assessments: list[AssessmentVersionEntry]
    total: int


class ClinicalTransitionResponse(BaseModel):
    """Response after a status transition."""

    case_id: UUID
    new_status: str
    message: str
