# @forgeplan-node: facilities-module
"""
FastAPI router for the facilities module.

All endpoints registered under /api/v1/facilities (prefix applied at app level).

Endpoint summary:
  GET    /facilities                              — AC1: all authenticated roles
  POST   /facilities                             — AC2: admin only
  GET    /facilities/{facility_id}               — AC3: all authenticated roles
  PATCH  /facilities/{facility_id}               — AC4: admin only
  PUT    /facilities/{facility_id}/capabilities  — AC5: admin or placement_coordinator
  GET    /facilities/{facility_id}/insurance-rules — AC6: all authenticated roles
  POST   /facilities/{facility_id}/insurance-rules — AC7: admin only
  PATCH  /insurance-rules/{rule_id}              — AC8: admin or placement_coordinator
  POST   /facilities/{facility_id}/contacts      — AC10: admin or placement_coordinator
"""
# @forgeplan-spec: AC1
# @forgeplan-spec: AC2
# @forgeplan-spec: AC3
# @forgeplan-spec: AC4
# @forgeplan-spec: AC5
# @forgeplan-spec: AC6
# @forgeplan-spec: AC7
# @forgeplan-spec: AC8
# @forgeplan-spec: AC10

from typing import Optional

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.auth import AuthContext, get_auth_context
from placementops.core.database import get_db
from placementops.modules.auth.dependencies import require_role, require_write_permission
from placementops.modules.facilities.schemas import (
    FacilityCapabilitiesResponse,
    FacilityCapabilitiesUpsertRequest,
    FacilityContactCreateRequest,
    FacilityContactResponse,
    FacilityCreateRequest,
    FacilityDetailResponse,
    FacilityDirectoryResponse,
    FacilityPatchRequest,
    FacilityPreferenceResponse,
    FacilityResponse,
    InsuranceRuleCreateRequest,
    InsuranceRulePatchRequest,
    InsuranceRuleResponse,
)
import placementops.modules.facilities.service as service

router = APIRouter(tags=["facilities"])

# Shorthand role sets
_ALL_ROLES = ["admin", "intake_staff", "clinical_reviewer", "placement_coordinator", "manager", "read_only"]
_ADMIN_ONLY = ["admin"]
_ADMIN_OR_COORDINATOR = ["admin", "placement_coordinator"]


# ── GET /facilities ──────────────────────────────────────────────────────────

@router.get(
    "/facilities",
    response_model=FacilityDirectoryResponse,
    status_code=status.HTTP_200_OK,
    summary="List facility directory (paginated, filtered)",
    dependencies=[require_role(*_ALL_ROLES)],
)
async def list_facilities(
    facility_type: Optional[str] = None,
    state: Optional[str] = None,
    county: Optional[str] = None,
    payer_id: Optional[str] = None,
    # Capability flag filters
    accepts_snf: Optional[bool] = None,
    accepts_irf: Optional[bool] = None,
    accepts_ltach: Optional[bool] = None,
    accepts_trach: Optional[bool] = None,
    accepts_vent: Optional[bool] = None,
    accepts_hd: Optional[bool] = None,
    in_house_hemodialysis: Optional[bool] = None,
    accepts_peritoneal_dialysis: Optional[bool] = None,
    accepts_wound_vac: Optional[bool] = None,
    accepts_iv_antibiotics: Optional[bool] = None,
    accepts_tpn: Optional[bool] = None,
    accepts_bariatric: Optional[bool] = None,
    accepts_behavioral_complexity: Optional[bool] = None,
    accepts_memory_care: Optional[bool] = None,
    accepts_isolation_cases: Optional[bool] = None,
    accepts_oxygen_therapy: Optional[bool] = None,
    weekend_admissions: Optional[bool] = None,
    after_hours_admissions: Optional[bool] = None,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    auth_ctx: AuthContext = Depends(get_auth_context),
) -> FacilityDirectoryResponse:
    """
    GET /api/v1/facilities

    Returns paginated facility directory. Accessible to all authenticated roles.
    Supports filters: facility_type, state, county, capability boolean flags, payer_id.
    AC1: pagination + filters.
    AC13: org isolation via organization_id filter.
    """
    # @forgeplan-spec: AC1
    # @forgeplan-spec: AC13
    facilities, total = await service.list_facilities(
        db=db,
        auth_ctx=auth_ctx,
        facility_type=facility_type,
        state=state,
        county=county,
        payer_id=payer_id,
        accepts_snf=accepts_snf,
        accepts_irf=accepts_irf,
        accepts_ltach=accepts_ltach,
        accepts_trach=accepts_trach,
        accepts_vent=accepts_vent,
        accepts_hd=accepts_hd,
        in_house_hemodialysis=in_house_hemodialysis,
        accepts_peritoneal_dialysis=accepts_peritoneal_dialysis,
        accepts_wound_vac=accepts_wound_vac,
        accepts_iv_antibiotics=accepts_iv_antibiotics,
        accepts_tpn=accepts_tpn,
        accepts_bariatric=accepts_bariatric,
        accepts_behavioral_complexity=accepts_behavioral_complexity,
        accepts_memory_care=accepts_memory_care,
        accepts_isolation_cases=accepts_isolation_cases,
        accepts_oxygen_therapy=accepts_oxygen_therapy,
        weekend_admissions=weekend_admissions,
        after_hours_admissions=after_hours_admissions,
        page=page,
        page_size=page_size,
    )
    return FacilityDirectoryResponse(
        facilities=[FacilityResponse.model_validate(f) for f in facilities],
        total=total,
        page=page,
        page_size=page_size,
    )


# ── POST /facilities ──────────────────────────────────────────────────────────

@router.post(
    "/facilities",
    response_model=FacilityResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new facility (admin only)",
    dependencies=[require_write_permission, require_role(*_ADMIN_ONLY)],
)
async def create_facility(
    payload: FacilityCreateRequest,
    db: AsyncSession = Depends(get_db),
    auth_ctx: AuthContext = Depends(get_auth_context),
) -> FacilityResponse:
    """
    POST /api/v1/facilities

    Creates a Facility record. Admin only (403 for all other roles).
    AC2: role enforcement via require_role("admin") dependency.
    """
    # @forgeplan-spec: AC2
    facility = await service.create_facility(db=db, auth_ctx=auth_ctx, payload=payload)
    return FacilityResponse.model_validate(facility)


# ── GET /facilities/{facility_id} ─────────────────────────────────────────────

@router.get(
    "/facilities/{facility_id}",
    response_model=FacilityDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get full facility profile",
    dependencies=[require_role(*_ALL_ROLES)],
)
async def get_facility(
    facility_id: str,
    db: AsyncSession = Depends(get_db),
    auth_ctx: AuthContext = Depends(get_auth_context),
) -> FacilityDetailResponse:
    """
    GET /api/v1/facilities/{facility_id}

    Returns full profile including capabilities, contacts, insurance_rules, preferences.
    Accessible to all authenticated roles.
    AC3: nested objects in response.
    AC13: 404 returned for cross-org facility_id.
    """
    # @forgeplan-spec: AC3
    # @forgeplan-spec: AC13
    facility = await service.get_facility(db=db, auth_ctx=auth_ctx, facility_id=facility_id)

    capabilities_orm = await service.get_facility_capabilities(db, facility_id)
    contacts_orm = await service.get_facility_contacts(db, facility_id)
    insurance_rules_orm = await service.get_facility_insurance_rules(db, facility_id)
    preferences_orm = await service.get_facility_preferences(db, facility_id)

    return FacilityDetailResponse(
        id=facility.id,
        organization_id=facility.organization_id,
        facility_name=facility.facility_name,
        facility_type=facility.facility_type,
        address_line_1=facility.address_line_1,
        city=facility.city,
        county=facility.county,
        state=facility.state,
        zip=facility.zip,
        latitude=float(facility.latitude) if facility.latitude is not None else None,
        longitude=float(facility.longitude) if facility.longitude is not None else None,
        active_status=facility.active_status,
        notes=facility.notes,
        created_at=facility.created_at,
        updated_at=facility.updated_at,
        capabilities=(
            FacilityCapabilitiesResponse.model_validate(capabilities_orm)
            if capabilities_orm
            else None
        ),
        contacts=[FacilityContactResponse.model_validate(c) for c in contacts_orm],
        insurance_rules=[InsuranceRuleResponse.model_validate(r) for r in insurance_rules_orm],
        preferences=[FacilityPreferenceResponse.model_validate(p) for p in preferences_orm],
    )


# ── PATCH /facilities/{facility_id} ──────────────────────────────────────────

@router.patch(
    "/facilities/{facility_id}",
    response_model=FacilityResponse,
    status_code=status.HTTP_200_OK,
    summary="Update facility profile fields (admin only)",
    dependencies=[require_write_permission, require_role(*_ADMIN_ONLY)],
)
async def patch_facility(
    facility_id: str,
    payload: FacilityPatchRequest,
    db: AsyncSession = Depends(get_db),
    auth_ctx: AuthContext = Depends(get_auth_context),
) -> FacilityResponse:
    """
    PATCH /api/v1/facilities/{facility_id}

    Updates facility profile fields. Admin only (403 for all other roles).
    AC4: role enforcement via require_role("admin") dependency.
    """
    # @forgeplan-spec: AC4
    facility = await service.patch_facility(
        db=db, auth_ctx=auth_ctx, facility_id=facility_id, payload=payload
    )
    return FacilityResponse.model_validate(facility)


# ── PUT /facilities/{facility_id}/capabilities ────────────────────────────────

@router.put(
    "/facilities/{facility_id}/capabilities",
    response_model=FacilityCapabilitiesResponse,
    status_code=status.HTTP_200_OK,
    summary="Upsert facility capability matrix (admin or coordinator)",
    dependencies=[require_write_permission, require_role(*_ADMIN_OR_COORDINATOR)],
)
async def upsert_capabilities(
    facility_id: str,
    payload: FacilityCapabilitiesUpsertRequest,
    db: AsyncSession = Depends(get_db),
    auth_ctx: AuthContext = Depends(get_auth_context),
) -> FacilityCapabilitiesResponse:
    """
    PUT /api/v1/facilities/{facility_id}/capabilities

    Creates or replaces FacilityCapabilities. All 18 boolean flags must be present.
    Sets last_verified_at to current UTC timestamp.
    AC5: admin or placement_coordinator; 403 for intake_staff, clinical_reviewer, read_only.
    AC9: all 18 flags stored.
    AC12: last_verified_at updated.
    """
    # @forgeplan-spec: AC5
    # @forgeplan-spec: AC9
    # @forgeplan-spec: AC12
    capabilities = await service.upsert_capabilities(
        db=db, auth_ctx=auth_ctx, facility_id=facility_id, payload=payload
    )
    return FacilityCapabilitiesResponse.model_validate(capabilities)


# ── GET /facilities/{facility_id}/insurance-rules ─────────────────────────────

@router.get(
    "/facilities/{facility_id}/insurance-rules",
    response_model=list[InsuranceRuleResponse],
    status_code=status.HTTP_200_OK,
    summary="List insurance rules for a facility",
    dependencies=[require_role(*_ALL_ROLES)],
)
async def list_insurance_rules(
    facility_id: str,
    db: AsyncSession = Depends(get_db),
    auth_ctx: AuthContext = Depends(get_auth_context),
) -> list[InsuranceRuleResponse]:
    """
    GET /api/v1/facilities/{facility_id}/insurance-rules

    Lists all payer acceptance rules for a facility. Accessible to all authenticated roles.
    AC6: all roles permitted.
    AC13: facility 404 if wrong org.
    """
    # @forgeplan-spec: AC6
    # @forgeplan-spec: AC13
    # Verify facility belongs to caller's org before listing rules
    await service.get_facility(db=db, auth_ctx=auth_ctx, facility_id=facility_id)
    rules = await service.get_facility_insurance_rules(db, facility_id)
    return [InsuranceRuleResponse.model_validate(r) for r in rules]


# ── POST /facilities/{facility_id}/insurance-rules ────────────────────────────

@router.post(
    "/facilities/{facility_id}/insurance-rules",
    response_model=InsuranceRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create insurance rule for a facility (admin only)",
    dependencies=[require_write_permission, require_role(*_ADMIN_ONLY)],
)
async def create_insurance_rule(
    facility_id: str,
    payload: InsuranceRuleCreateRequest,
    db: AsyncSession = Depends(get_db),
    auth_ctx: AuthContext = Depends(get_auth_context),
) -> InsuranceRuleResponse:
    """
    POST /api/v1/facilities/{facility_id}/insurance-rules

    Creates a FacilityInsuranceRule. Sets last_verified_at to current UTC.
    Admin only (403 for all other roles).
    AC7: admin role enforcement.
    AC12: last_verified_at set.
    """
    # @forgeplan-spec: AC7
    # @forgeplan-spec: AC12
    rule = await service.create_insurance_rule(
        db=db, auth_ctx=auth_ctx, facility_id=facility_id, payload=payload
    )
    return InsuranceRuleResponse.model_validate(rule)


# ── PATCH /insurance-rules/{rule_id} ─────────────────────────────────────────

@router.patch(
    "/insurance-rules/{rule_id}",
    response_model=InsuranceRuleResponse,
    status_code=status.HTTP_200_OK,
    summary="Update insurance rule (admin or coordinator)",
    dependencies=[require_write_permission, require_role(*_ADMIN_OR_COORDINATOR)],
)
async def patch_insurance_rule(
    rule_id: str,
    payload: InsuranceRulePatchRequest,
    db: AsyncSession = Depends(get_db),
    auth_ctx: AuthContext = Depends(get_auth_context),
) -> InsuranceRuleResponse:
    """
    PATCH /api/v1/insurance-rules/{rule_id}

    Updates accepted_status and/or notes; always refreshes last_verified_at.
    Admin or placement_coordinator (403 for all other roles).
    AC8: role enforcement.
    AC12: last_verified_at updated.
    """
    # @forgeplan-spec: AC8
    # @forgeplan-spec: AC12
    rule = await service.patch_insurance_rule(
        db=db, auth_ctx=auth_ctx, rule_id=rule_id, payload=payload
    )
    return InsuranceRuleResponse.model_validate(rule)


# ── POST /facilities/{facility_id}/contacts ───────────────────────────────────

@router.post(
    "/facilities/{facility_id}/contacts",
    response_model=FacilityContactResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a contact for a facility (admin or coordinator)",
    dependencies=[require_write_permission, require_role(*_ADMIN_OR_COORDINATOR)],
)
async def create_contact(
    facility_id: str,
    payload: FacilityContactCreateRequest,
    db: AsyncSession = Depends(get_db),
    auth_ctx: AuthContext = Depends(get_auth_context),
) -> FacilityContactResponse:
    """
    POST /api/v1/facilities/{facility_id}/contacts

    Creates a FacilityContact record including Phase 2 voice fields.
    AC10: phone_extension, best_call_window, phone_contact_name persisted.
    """
    # @forgeplan-spec: AC10
    contact = await service.create_contact(
        db=db, auth_ctx=auth_ctx, facility_id=facility_id, payload=payload
    )
    return FacilityContactResponse.model_validate(contact)
