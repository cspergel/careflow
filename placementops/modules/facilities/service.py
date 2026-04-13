# @forgeplan-node: facilities-module
"""
Database operations for the facilities module.

All write operations:
  1. Apply the business logic (upsert, update, etc.)
  2. Emit an AuditEvent via emit_audit_event()
  3. Commit and refresh the ORM object (service owns the commit)

Organization isolation is enforced at the application layer by filtering
all queries on organization_id=auth_ctx.organization_id. This is defense-
in-depth alongside Supabase RLS policies on the underlying tables.
"""
# @forgeplan-spec: AC1
# @forgeplan-spec: AC2
# @forgeplan-spec: AC3
# @forgeplan-spec: AC4
# @forgeplan-spec: AC5
# @forgeplan-spec: AC6
# @forgeplan-spec: AC7
# @forgeplan-spec: AC8
# @forgeplan-spec: AC12
# @forgeplan-spec: AC13
# @forgeplan-decision: D-facilities-2-org-filter -- All list/get queries filter by organization_id. Why: defense-in-depth alongside RLS; prevents data leakage when RLS is disabled in dev/test environments

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.audit import emit_audit_event
from placementops.core.auth import AuthContext
from placementops.core.models import (
    Facility,
    FacilityCapabilities,
    FacilityContact,
    FacilityInsuranceRule,
)
from placementops.modules.facilities.models import FacilityPreference
from placementops.modules.facilities.schemas import (
    FacilityCapabilitiesUpsertRequest,
    FacilityContactCreateRequest,
    FacilityCreateRequest,
    FacilityPatchRequest,
    InsuranceRuleCreateRequest,
    InsuranceRulePatchRequest,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    """Return current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


async def _get_facility_or_404(
    db: AsyncSession,
    facility_id: str,
    organization_id: str,
) -> Facility:
    """
    Fetch a Facility row filtered by organization_id; raise 404 if not found.

    AC13: org filter prevents cross-org reads even when RLS is disabled.
    """
    # @forgeplan-spec: AC13
    result = await db.execute(
        select(Facility).where(
            Facility.id == facility_id,
            Facility.organization_id == organization_id,
        )
    )
    facility = result.scalar_one_or_none()
    if facility is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Facility not found",
        )
    return facility


# ── Facility CRUD ─────────────────────────────────────────────────────────────

async def list_facilities(
    db: AsyncSession,
    auth_ctx: AuthContext,
    facility_type: Optional[str] = None,
    state: Optional[str] = None,
    county: Optional[str] = None,
    payer_id: Optional[str] = None,
    # Capability flag filters — each is an optional boolean
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
) -> tuple[list[Facility], int]:
    """
    Return paginated facility list filtered by organization_id and optional filters.

    AC1: supports facility_type, state, county, capability flags, and payer_id.
    AC13: organization_id filter enforced.
    """
    # @forgeplan-spec: AC1
    # @forgeplan-spec: AC13
    query = select(Facility).where(
        Facility.organization_id == str(auth_ctx.organization_id)
    )

    if facility_type:
        query = query.where(Facility.facility_type == facility_type)
    if state:
        query = query.where(Facility.state == state)
    if county:
        query = query.where(Facility.county == county)

    # Capability flag filters require a JOIN to facility_capabilities
    cap_filters = {
        "accepts_snf": accepts_snf,
        "accepts_irf": accepts_irf,
        "accepts_ltach": accepts_ltach,
        "accepts_trach": accepts_trach,
        "accepts_vent": accepts_vent,
        "accepts_hd": accepts_hd,
        "in_house_hemodialysis": in_house_hemodialysis,
        "accepts_peritoneal_dialysis": accepts_peritoneal_dialysis,
        "accepts_wound_vac": accepts_wound_vac,
        "accepts_iv_antibiotics": accepts_iv_antibiotics,
        "accepts_tpn": accepts_tpn,
        "accepts_bariatric": accepts_bariatric,
        "accepts_behavioral_complexity": accepts_behavioral_complexity,
        "accepts_memory_care": accepts_memory_care,
        "accepts_isolation_cases": accepts_isolation_cases,
        "accepts_oxygen_therapy": accepts_oxygen_therapy,
        "weekend_admissions": weekend_admissions,
        "after_hours_admissions": after_hours_admissions,
    }
    active_cap_filters = {k: v for k, v in cap_filters.items() if v is not None}

    if active_cap_filters or payer_id:
        if active_cap_filters:
            query = query.join(
                FacilityCapabilities,
                FacilityCapabilities.facility_id == Facility.id,
            )
            for flag_name, flag_value in active_cap_filters.items():
                query = query.where(
                    getattr(FacilityCapabilities, flag_name) == flag_value
                )

        if payer_id:
            query = query.join(
                FacilityInsuranceRule,
                FacilityInsuranceRule.facility_id == Facility.id,
            ).where(FacilityInsuranceRule.payer_id == payer_id)

    # Count total matching rows before applying pagination.
    # Build count subquery from the filtered base query before adding LIMIT/OFFSET.
    count_query = select(func.count()).select_from(query.subquery())
    count_result = await db.execute(count_query)
    total = count_result.scalar_one() or 0

    # Apply pagination
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)

    result = await db.execute(query)
    facilities = result.scalars().all()

    return list(facilities), total


async def create_facility(
    db: AsyncSession,
    auth_ctx: AuthContext,
    payload: FacilityCreateRequest,
) -> Facility:
    """
    Create a Facility record; emit AuditEvent.

    AC2: caller must be admin (enforced in router via require_role dependency).
    """
    # @forgeplan-spec: AC2
    facility = Facility(
        organization_id=str(auth_ctx.organization_id),
        facility_name=payload.facility_name,
        facility_type=payload.facility_type,
        address_line_1=payload.address_line_1,
        city=payload.city,
        county=payload.county,
        state=payload.state,
        zip=payload.zip,
        latitude=payload.latitude,
        longitude=payload.longitude,
        notes=payload.notes,
    )
    db.add(facility)
    await db.flush()  # populate id before audit event

    await emit_audit_event(
        session=db,
        organization_id=auth_ctx.organization_id,
        entity_type="facility",
        entity_id=UUID(facility.id),
        event_type="facility.created",
        actor_user_id=auth_ctx.user_id,
        new_value={
            "facility_name": facility.facility_name,
            "facility_type": facility.facility_type,
        },
    )
    await db.commit()
    await db.refresh(facility)
    return facility


async def get_facility(
    db: AsyncSession,
    auth_ctx: AuthContext,
    facility_id: str,
) -> Facility:
    """
    Fetch a single facility by ID. Returns 404 if not found or wrong org.

    AC3: accessible to all authenticated roles.
    AC13: org filter enforced.
    """
    # @forgeplan-spec: AC3
    # @forgeplan-spec: AC13
    return await _get_facility_or_404(db, facility_id, str(auth_ctx.organization_id))


async def get_facility_capabilities(
    db: AsyncSession,
    facility_id: str,
) -> Optional[FacilityCapabilities]:
    """Return FacilityCapabilities for a facility, or None if not set."""
    result = await db.execute(
        select(FacilityCapabilities).where(
            FacilityCapabilities.facility_id == facility_id
        )
    )
    return result.scalar_one_or_none()


async def get_facility_contacts(
    db: AsyncSession,
    facility_id: str,
) -> list[FacilityContact]:
    """Return all FacilityContact rows for a facility."""
    result = await db.execute(
        select(FacilityContact).where(FacilityContact.facility_id == facility_id)
    )
    return list(result.scalars().all())


async def get_facility_insurance_rules(
    db: AsyncSession,
    facility_id: str,
) -> list[FacilityInsuranceRule]:
    """Return all FacilityInsuranceRule rows for a facility."""
    # @forgeplan-spec: AC6
    result = await db.execute(
        select(FacilityInsuranceRule).where(
            FacilityInsuranceRule.facility_id == facility_id
        )
    )
    return list(result.scalars().all())


async def get_facility_preferences(
    db: AsyncSession,
    facility_id: str,
) -> list[FacilityPreference]:
    """Return all FacilityPreference rows for a facility."""
    # @forgeplan-spec: AC11
    result = await db.execute(
        select(FacilityPreference).where(
            FacilityPreference.facility_id == facility_id
        )
    )
    return list(result.scalars().all())


async def patch_facility(
    db: AsyncSession,
    auth_ctx: AuthContext,
    facility_id: str,
    payload: FacilityPatchRequest,
) -> Facility:
    """
    Update facility profile fields; emit AuditEvent.

    AC4: caller must be admin (enforced in router).
    """
    # @forgeplan-spec: AC4
    facility = await _get_facility_or_404(db, facility_id, str(auth_ctx.organization_id))

    old_values: dict = {}
    new_values: dict = {}

    update_fields = payload.model_dump(exclude_none=True)
    for field, value in update_fields.items():
        old_val = getattr(facility, field, None)
        if old_val != value:
            old_values[field] = old_val
            new_values[field] = value
            setattr(facility, field, value)

    await emit_audit_event(
        session=db,
        organization_id=auth_ctx.organization_id,
        entity_type="facility",
        entity_id=UUID(facility.id),
        event_type="facility.updated",
        actor_user_id=auth_ctx.user_id,
        old_value=old_values or None,
        new_value=new_values or None,
    )
    await db.commit()
    await db.refresh(facility)
    return facility


# ── Capabilities upsert ───────────────────────────────────────────────────────

async def upsert_capabilities(
    db: AsyncSession,
    auth_ctx: AuthContext,
    facility_id: str,
    payload: FacilityCapabilitiesUpsertRequest,
) -> FacilityCapabilities:
    """
    Upsert FacilityCapabilities for a facility; sets last_verified_at.

    AC5: admin or placement_coordinator (enforced in router).
    AC9: all 18 boolean flags stored.
    AC12: last_verified_at set to current UTC.
    """
    # @forgeplan-spec: AC5
    # @forgeplan-spec: AC9
    # @forgeplan-spec: AC12

    # Verify facility belongs to caller's org
    await _get_facility_or_404(db, facility_id, str(auth_ctx.organization_id))

    now = _utcnow()

    result = await db.execute(
        select(FacilityCapabilities).where(
            FacilityCapabilities.facility_id == facility_id
        )
    )
    capabilities = result.scalar_one_or_none()

    flag_data = payload.model_dump()

    if capabilities is None:
        # @forgeplan-decision: D-facilities-3-upsert-pattern -- SELECT then INSERT/UPDATE for upsert. Why: SQLite in tests does not support PostgreSQL ON CONFLICT syntax; merge() does SELECT+INSERT which works across both backends
        capabilities = FacilityCapabilities(
            facility_id=facility_id,
            last_verified_at=now,
            **flag_data,
        )
        db.add(capabilities)
        await db.flush()
    else:
        for flag_name, flag_value in flag_data.items():
            setattr(capabilities, flag_name, flag_value)
        capabilities.last_verified_at = now

    await emit_audit_event(
        session=db,
        organization_id=auth_ctx.organization_id,
        entity_type="facility_capabilities",
        entity_id=UUID(capabilities.id),
        event_type="facility.capabilities.updated",
        actor_user_id=auth_ctx.user_id,
        new_value={**flag_data, "last_verified_at": now.isoformat()},
    )
    await db.commit()
    await db.refresh(capabilities)
    return capabilities


# ── Contact management ────────────────────────────────────────────────────────

async def create_contact(
    db: AsyncSession,
    auth_ctx: AuthContext,
    facility_id: str,
    payload: FacilityContactCreateRequest,
) -> FacilityContact:
    """
    Create a FacilityContact record; emit AuditEvent.

    AC10: Phase 2 voice fields persisted.
    """
    # @forgeplan-spec: AC10
    await _get_facility_or_404(db, facility_id, str(auth_ctx.organization_id))

    contact = FacilityContact(
        facility_id=facility_id,
        contact_name=payload.contact_name,
        title=payload.title,
        phone=payload.phone,
        phone_extension=payload.phone_extension,
        best_call_window=payload.best_call_window,
        phone_contact_name=payload.phone_contact_name,
        email=payload.email,
        is_primary=payload.is_primary,
    )
    db.add(contact)
    await db.flush()

    await emit_audit_event(
        session=db,
        organization_id=auth_ctx.organization_id,
        entity_type="facility_contact",
        entity_id=UUID(contact.id),
        event_type="facility.contact.created",
        actor_user_id=auth_ctx.user_id,
        new_value={"contact_name": contact.contact_name, "facility_id": facility_id},
    )
    await db.commit()
    await db.refresh(contact)
    return contact


# ── Insurance rule management ─────────────────────────────────────────────────

async def create_insurance_rule(
    db: AsyncSession,
    auth_ctx: AuthContext,
    facility_id: str,
    payload: InsuranceRuleCreateRequest,
) -> FacilityInsuranceRule:
    """
    Create FacilityInsuranceRule; set last_verified_at; emit AuditEvent.

    AC7: admin only (enforced in router).
    AC12: last_verified_at set.
    """
    # @forgeplan-spec: AC7
    # @forgeplan-spec: AC12
    await _get_facility_or_404(db, facility_id, str(auth_ctx.organization_id))

    now = _utcnow()
    rule = FacilityInsuranceRule(
        facility_id=facility_id,
        payer_id=payload.payer_id,
        payer_name=payload.payer_name,
        accepted_status=payload.accepted_status,
        notes=payload.notes,
        last_verified_at=now,
    )
    db.add(rule)
    await db.flush()

    await emit_audit_event(
        session=db,
        organization_id=auth_ctx.organization_id,
        entity_type="facility_insurance_rule",
        entity_id=UUID(rule.id),
        event_type="facility.insurance_rule.created",
        actor_user_id=auth_ctx.user_id,
        new_value={
            "payer_id": rule.payer_id,
            "accepted_status": rule.accepted_status,
            "last_verified_at": now.isoformat(),
        },
    )
    await db.commit()
    await db.refresh(rule)
    return rule


async def patch_insurance_rule(
    db: AsyncSession,
    auth_ctx: AuthContext,
    rule_id: str,
    payload: InsuranceRulePatchRequest,
) -> FacilityInsuranceRule:
    """
    Update FacilityInsuranceRule; refresh last_verified_at; emit AuditEvent.

    AC8: admin or placement_coordinator (enforced in router).
    AC12: last_verified_at refreshed.
    """
    # @forgeplan-spec: AC8
    # @forgeplan-spec: AC12
    result = await db.execute(
        select(FacilityInsuranceRule).where(FacilityInsuranceRule.id == rule_id)
    )
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Insurance rule not found",
        )

    # Verify the rule's facility belongs to caller's org
    await _get_facility_or_404(db, rule.facility_id, str(auth_ctx.organization_id))

    now = _utcnow()
    old_values: dict = {}
    new_values: dict = {}

    if payload.accepted_status is not None and payload.accepted_status != rule.accepted_status:
        old_values["accepted_status"] = rule.accepted_status
        new_values["accepted_status"] = payload.accepted_status
        rule.accepted_status = payload.accepted_status

    if payload.notes is not None and payload.notes != rule.notes:
        old_values["notes"] = rule.notes
        new_values["notes"] = payload.notes
        rule.notes = payload.notes

    # AC12: always refresh last_verified_at on PATCH
    rule.last_verified_at = now
    new_values["last_verified_at"] = now.isoformat()

    await emit_audit_event(
        session=db,
        organization_id=auth_ctx.organization_id,
        entity_type="facility_insurance_rule",
        entity_id=UUID(rule.id),
        event_type="facility.insurance_rule.updated",
        actor_user_id=auth_ctx.user_id,
        old_value=old_values or None,
        new_value=new_values,
    )
    await db.commit()
    await db.refresh(rule)
    return rule
