# @forgeplan-node: facilities-module
"""
Pydantic request/response schemas for the facilities module.

All schemas follow FastAPI conventions:
- Request schemas use BaseModel with explicit Optional fields for nullable inputs.
- Response schemas use model_config = ConfigDict(from_attributes=True) for ORM coercion.
"""
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

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, field_validator


# ── Facility schemas ──────────────────────────────────────────────────────────

class FacilityCreateRequest(BaseModel):
    """POST /facilities — admin only."""
    # @forgeplan-spec: AC2
    facility_name: str
    facility_type: str  # snf | irf | ltach
    address_line_1: Optional[str] = None
    city: Optional[str] = None
    county: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    notes: Optional[str] = None

    @field_validator("facility_type")
    @classmethod
    def validate_facility_type(cls, v: str) -> str:
        allowed = {"snf", "irf", "ltach"}
        if v not in allowed:
            raise ValueError(f"facility_type must be one of {allowed}")
        return v


class FacilityPatchRequest(BaseModel):
    """PATCH /facilities/{id} — admin only; at least one field required."""
    # @forgeplan-spec: AC4
    facility_name: Optional[str] = None
    facility_type: Optional[str] = None
    address_line_1: Optional[str] = None
    city: Optional[str] = None
    county: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    active_status: Optional[bool] = None
    notes: Optional[str] = None

    @field_validator("facility_type")
    @classmethod
    def validate_facility_type(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            allowed = {"snf", "irf", "ltach"}
            if v not in allowed:
                raise ValueError(f"facility_type must be one of {allowed}")
        return v


class FacilityResponse(BaseModel):
    """Single facility record response."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    facility_name: str
    facility_type: str
    address_line_1: Optional[str] = None
    city: Optional[str] = None
    county: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    active_status: bool
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# ── FacilityCapabilities schemas ──────────────────────────────────────────────

class FacilityCapabilitiesUpsertRequest(BaseModel):
    """
    PUT /facilities/{id}/capabilities — admin or placement_coordinator.

    All 18 boolean flags are required. Names must exactly mirror ClinicalAssessment.
    """
    # @forgeplan-spec: AC5
    # @forgeplan-spec: AC9
    accepts_snf: bool
    accepts_irf: bool
    accepts_ltach: bool
    accepts_trach: bool
    accepts_vent: bool
    accepts_hd: bool
    in_house_hemodialysis: bool
    accepts_peritoneal_dialysis: bool
    accepts_wound_vac: bool
    accepts_iv_antibiotics: bool
    accepts_tpn: bool
    accepts_bariatric: bool
    accepts_behavioral_complexity: bool
    accepts_memory_care: bool
    accepts_isolation_cases: bool
    accepts_oxygen_therapy: bool
    weekend_admissions: bool
    after_hours_admissions: bool


class FacilityCapabilitiesResponse(BaseModel):
    """FacilityCapabilities response — all 18 flags + metadata."""
    model_config = ConfigDict(from_attributes=True)

    # @forgeplan-spec: AC9
    id: str
    facility_id: str
    accepts_snf: bool
    accepts_irf: bool
    accepts_ltach: bool
    accepts_trach: bool
    accepts_vent: bool
    accepts_hd: bool
    in_house_hemodialysis: bool
    accepts_peritoneal_dialysis: bool
    accepts_wound_vac: bool
    accepts_iv_antibiotics: bool
    accepts_tpn: bool
    accepts_bariatric: bool
    accepts_behavioral_complexity: bool
    accepts_memory_care: bool
    accepts_isolation_cases: bool
    accepts_oxygen_therapy: bool
    weekend_admissions: bool
    after_hours_admissions: bool
    last_verified_at: Optional[datetime] = None
    updated_at: datetime


# ── FacilityContact schemas ───────────────────────────────────────────────────

class FacilityContactCreateRequest(BaseModel):
    """POST /facilities/{id}/contacts — admin or placement_coordinator."""
    # @forgeplan-spec: AC10
    contact_name: str
    title: Optional[str] = None
    phone: Optional[str] = None
    # Phase 2 voice fields — stored now for forward compatibility
    phone_extension: Optional[str] = None
    best_call_window: Optional[str] = None
    phone_contact_name: Optional[str] = None
    email: Optional[str] = None
    is_primary: bool = False


class FacilityContactResponse(BaseModel):
    """FacilityContact response including Phase 2 voice fields."""
    model_config = ConfigDict(from_attributes=True)

    # @forgeplan-spec: AC10
    id: str
    facility_id: str
    contact_name: str
    title: Optional[str] = None
    phone: Optional[str] = None
    phone_extension: Optional[str] = None   # Phase 2
    best_call_window: Optional[str] = None  # Phase 2
    phone_contact_name: Optional[str] = None  # Phase 2
    email: Optional[str] = None
    is_primary: bool
    created_at: datetime
    updated_at: datetime


# ── FacilityInsuranceRule schemas ─────────────────────────────────────────────

class InsuranceRuleCreateRequest(BaseModel):
    """POST /facilities/{id}/insurance-rules — admin only."""
    # @forgeplan-spec: AC7
    payer_id: str
    payer_name: str
    accepted_status: str  # accepted | conditional | not_accepted
    notes: Optional[str] = None

    @field_validator("accepted_status")
    @classmethod
    def validate_accepted_status(cls, v: str) -> str:
        allowed = {"accepted", "conditional", "not_accepted"}
        if v not in allowed:
            raise ValueError(f"accepted_status must be one of {allowed}")
        return v


class InsuranceRulePatchRequest(BaseModel):
    """PATCH /insurance-rules/{id} — admin or placement_coordinator."""
    # @forgeplan-spec: AC8
    accepted_status: Optional[str] = None
    notes: Optional[str] = None

    @field_validator("accepted_status")
    @classmethod
    def validate_accepted_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            allowed = {"accepted", "conditional", "not_accepted"}
            if v not in allowed:
                raise ValueError(f"accepted_status must be one of {allowed}")
        return v


class InsuranceRuleResponse(BaseModel):
    """FacilityInsuranceRule response."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    facility_id: str
    payer_id: str
    payer_name: str
    accepted_status: str
    notes: Optional[str] = None
    last_verified_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# ── FacilityPreference schemas ────────────────────────────────────────────────

class FacilityPreferenceResponse(BaseModel):
    """FacilityPreference response."""
    model_config = ConfigDict(from_attributes=True)

    # @forgeplan-spec: AC11
    id: str
    facility_id: str
    scope: str  # global | market | hospital
    scope_reference_id: Optional[str] = None
    preference_rank: int
    created_at: datetime
    updated_at: datetime


# ── Directory / composite schemas ─────────────────────────────────────────────

class FacilityDetailResponse(BaseModel):
    """
    GET /facilities/{id} — full profile with nested objects.

    Includes capabilities, contacts, insurance_rules, and preferences.
    """
    model_config = ConfigDict(from_attributes=True)

    # @forgeplan-spec: AC3
    id: str
    organization_id: str
    facility_name: str
    facility_type: str
    address_line_1: Optional[str] = None
    city: Optional[str] = None
    county: Optional[str] = None
    state: Optional[str] = None
    zip: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    active_status: bool
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    capabilities: Optional[FacilityCapabilitiesResponse] = None
    contacts: List[FacilityContactResponse] = []
    insurance_rules: List[InsuranceRuleResponse] = []
    preferences: List[FacilityPreferenceResponse] = []


class FacilityDirectoryResponse(BaseModel):
    """
    GET /facilities — paginated directory response.
    """
    # @forgeplan-spec: AC1
    facilities: List[FacilityResponse]
    total: int
    page: int
    page_size: int
