# @forgeplan-node: admin-surfaces
# @forgeplan-spec: AC1, AC2, AC3, AC4, AC5, AC6, AC7, AC8, AC9, AC10, AC11
"""
Admin-surfaces service layer.

All functions are async, accept an AsyncSession, and perform org-scoped queries.
Mutations emit AuditEvent rows atomically within the same transaction.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.audit import emit_audit_event
from placementops.core.auth import AuthContext
from placementops.core.models import (
    AuditEvent,
    DeclineReasonReference,
    HospitalReference,
    ImportJob,
    OutreachTemplate,
    PayerReference,
    User,
)
from placementops.core.models.reference_tables import Organization
from placementops.modules.admin.schemas import (
    AdminCreateTemplateRequest,
    AdminCreateUserRequest,
    AdminUpdateOrgRequest,
    AdminUpdateTemplateRequest,
    AdminUpdateUserRequest,
)

# @forgeplan-decision: D-admin-1-allowed-variables-allowlist -- Hard-coded allowlist in service constant. Why: template allowed_variables must be validated server-side to prevent unsafe variable injection into outreach templates; a central constant is the single source of truth
ALLOWED_TEMPLATE_VARIABLES: frozenset[str] = frozenset(
    [
        "patient_name",
        "facility_name",
        "payer_name",
        "assessment_summary",
        "coordinator_name",
    ]
)

VALID_ROLE_KEYS: frozenset[str] = frozenset(
    [
        "admin",
        "intake_staff",
        "clinical_reviewer",
        "placement_coordinator",
        "manager",
        "read_only",
    ]
)

VALID_USER_STATUSES: frozenset[str] = frozenset(["active", "inactive"])

VALID_TEMPLATE_TYPES: frozenset[str] = frozenset(
    ["email", "phone_manual", "task", "voice_ai_script"]
)


def _validate_allowed_variables(variables: list[str]) -> None:
    """Raise HTTP 400 if any variable is outside the safe allowlist."""
    invalid = [v for v in variables if v not in ALLOWED_TEMPLATE_VARIABLES]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid template variables: {invalid}. Allowed: {sorted(ALLOWED_TEMPLATE_VARIABLES)}",
        )


# ---------------------------------------------------------------------------
# User management  (AC1, AC2, AC3)
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC1
async def list_users(
    session: AsyncSession,
    auth_ctx: AuthContext,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[User], int]:
    """
    Return paginated users scoped to caller's organization_id.

    Returns (users, total_count).
    """
    org_id = str(auth_ctx.organization_id)

    count_stmt = select(func.count(User.id)).where(User.organization_id == org_id)
    total_result = await session.execute(count_stmt)
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    stmt = (
        select(User)
        .where(User.organization_id == org_id)
        .order_by(User.created_at.asc())
        .offset(offset)
        .limit(page_size)
    )
    result = await session.execute(stmt)
    users = list(result.scalars().all())
    return users, total


# @forgeplan-spec: AC2
# @forgeplan-spec: AC11
async def create_user(
    session: AsyncSession,
    payload: AdminCreateUserRequest,
    auth_ctx: AuthContext,
) -> User:
    """
    Create a new User record with status=active.

    Validates:
      - email uniqueness in users table
      - role_key in VALID_ROLE_KEYS

    Writes AuditEvent(event_type=user_created) atomically.
    """
    org_id = str(auth_ctx.organization_id)

    # Validate role_key
    if payload.role_key not in VALID_ROLE_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role_key '{payload.role_key}'. Must be one of: {sorted(VALID_ROLE_KEYS)}",
        )

    # Check email uniqueness
    existing = await session.execute(
        select(User).where(User.email == payload.email)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A user with email '{payload.email}' already exists",
        )

    new_user = User(
        id=str(uuid4()),
        organization_id=org_id,
        email=payload.email,
        full_name=payload.full_name,
        role_key=payload.role_key,
        status="active",
        timezone=payload.timezone,
        default_hospital_id=payload.default_hospital_id,
    )
    session.add(new_user)
    # Flush to get the generated id before audit
    await session.flush()

    await emit_audit_event(
        session=session,
        organization_id=auth_ctx.organization_id,
        entity_type="user",
        entity_id=UUID(new_user.id),
        event_type="user_created",
        actor_user_id=auth_ctx.user_id,
        old_value=None,
        new_value={
            "email": new_user.email,
            "full_name": new_user.full_name,
            "role_key": new_user.role_key,
            "status": new_user.status,
        },
    )
    await session.commit()
    await session.refresh(new_user)
    return new_user


# @forgeplan-spec: AC3
# @forgeplan-spec: AC11
async def update_user(
    session: AsyncSession,
    user_id: str,
    payload: AdminUpdateUserRequest,
    auth_ctx: AuthContext,
) -> User:
    """
    Update role_key and/or status (and optionally full_name, timezone, default_hospital_id).

    Guards:
      - User must exist and belong to caller's org (404 otherwise)
      - Cannot deactivate the last active admin in the org (400)
      - role_key must be valid if provided
      - status must be 'active' or 'inactive' if provided

    Writes AuditEvent(event_type=user_updated) atomically.
    Captures old values BEFORE applying changes.
    """
    org_id = str(auth_ctx.organization_id)

    result = await session.execute(
        select(User).where(User.id == user_id, User.organization_id == org_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User '{user_id}' not found",
        )

    # Validate inputs
    if payload.role_key is not None and payload.role_key not in VALID_ROLE_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role_key '{payload.role_key}'",
        )
    if payload.status is not None and payload.status not in VALID_USER_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status '{payload.status}'. Must be 'active' or 'inactive'",
        )

    # @forgeplan-spec: AC3 — last-admin guard
    # Check BEFORE applying changes: if we're deactivating this user or changing role away from admin
    will_become_inactive = payload.status == "inactive" and user.status == "active"
    will_lose_admin = payload.role_key is not None and payload.role_key != "admin" and user.role_key == "admin"

    if will_become_inactive or will_lose_admin:
        # Count active admins in this org
        count_result = await session.execute(
            select(func.count(User.id)).where(
                User.organization_id == org_id,
                User.role_key == "admin",
                User.status == "active",
            )
        )
        active_admin_count = count_result.scalar_one()

        if user.role_key == "admin" and active_admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot deactivate the last active admin in this organization.",
            )

    # Capture old values before mutation (AC11)
    old_values = {
        "role_key": user.role_key,
        "status": user.status,
        "full_name": user.full_name,
        "timezone": user.timezone,
        "default_hospital_id": user.default_hospital_id,
    }

    # Apply changes
    if payload.role_key is not None:
        user.role_key = payload.role_key
    if payload.status is not None:
        user.status = payload.status
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.timezone is not None:
        user.timezone = payload.timezone
    if payload.default_hospital_id is not None:
        user.default_hospital_id = payload.default_hospital_id

    new_values = {
        "role_key": user.role_key,
        "status": user.status,
        "full_name": user.full_name,
        "timezone": user.timezone,
        "default_hospital_id": user.default_hospital_id,
    }

    await emit_audit_event(
        session=session,
        organization_id=auth_ctx.organization_id,
        entity_type="user",
        entity_id=UUID(user.id),
        event_type="user_updated",
        actor_user_id=auth_ctx.user_id,
        old_value=old_values,
        new_value=new_values,
    )
    await session.commit()
    await session.refresh(user)
    return user


# ---------------------------------------------------------------------------
# OutreachTemplate management  (AC4, AC5, AC6)
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC4
async def list_templates(
    session: AsyncSession,
    auth_ctx: AuthContext,
) -> tuple[list[OutreachTemplate], int]:
    """
    Return all OutreachTemplate records for caller's org.

    Accessible to any authenticated role (not admin-only).
    Returns (templates, total).
    """
    org_id = str(auth_ctx.organization_id)
    stmt = (
        select(OutreachTemplate)
        .where(OutreachTemplate.organization_id == org_id)
        .order_by(OutreachTemplate.created_at.asc())
    )
    result = await session.execute(stmt)
    templates = list(result.scalars().all())
    return templates, len(templates)


# @forgeplan-spec: AC5
# @forgeplan-spec: AC11
async def create_template(
    session: AsyncSession,
    payload: AdminCreateTemplateRequest,
    auth_ctx: AuthContext,
) -> OutreachTemplate:
    """
    Create a new OutreachTemplate.

    Validates:
      - template_name and body_template non-empty
      - template_type in VALID_TEMPLATE_TYPES
      - allowed_variables subset of ALLOWED_TEMPLATE_VARIABLES

    Writes AuditEvent(event_type=template_created) atomically.
    """
    org_id = str(auth_ctx.organization_id)

    if not payload.template_name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="template_name must not be empty",
        )
    if not payload.body_template.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="body_template must not be empty",
        )
    if payload.template_type not in VALID_TEMPLATE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid template_type '{payload.template_type}'. Must be one of: {sorted(VALID_TEMPLATE_TYPES)}",
        )
    _validate_allowed_variables(payload.allowed_variables)

    template = OutreachTemplate(
        id=str(uuid4()),
        organization_id=org_id,
        template_name=payload.template_name,
        template_type=payload.template_type,
        subject_template=payload.subject_template,
        body_template=payload.body_template,
        allowed_variables=payload.allowed_variables,
        is_active=payload.is_active,
        created_by_user_id=str(auth_ctx.user_id),
    )
    session.add(template)
    await session.flush()

    await emit_audit_event(
        session=session,
        organization_id=auth_ctx.organization_id,
        entity_type="outreach_template",
        entity_id=UUID(template.id),
        event_type="template_created",
        actor_user_id=auth_ctx.user_id,
        old_value=None,
        new_value={
            "template_name": template.template_name,
            "template_type": template.template_type,
            "is_active": template.is_active,
            "allowed_variables": payload.allowed_variables,
        },
    )
    await session.commit()
    await session.refresh(template)
    return template


# @forgeplan-spec: AC6
# @forgeplan-spec: AC11
async def update_template(
    session: AsyncSession,
    template_id: str,
    payload: AdminUpdateTemplateRequest,
    auth_ctx: AuthContext,
) -> OutreachTemplate:
    """
    Update an OutreachTemplate.

    Guards:
      - Template must belong to caller's org (404 — not 403 — for cross-org access)
      - template_name and body_template must be non-empty if provided
      - allowed_variables must not introduce variables outside allowlist

    Captures old values BEFORE mutation (AC11).
    Writes AuditEvent(event_type=template_updated).
    """
    org_id = str(auth_ctx.organization_id)

    result = await session.execute(
        select(OutreachTemplate).where(
            OutreachTemplate.id == template_id,
            OutreachTemplate.organization_id == org_id,
        )
    )
    template = result.scalar_one_or_none()
    if template is None:
        # 404 — not 403 — to avoid information disclosure about cross-org template_ids
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"OutreachTemplate '{template_id}' not found",
        )

    # Validate inputs
    if payload.template_name is not None and not payload.template_name.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="template_name must not be empty",
        )
    if payload.body_template is not None and not payload.body_template.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="body_template must not be empty",
        )
    if payload.template_type is not None and payload.template_type not in VALID_TEMPLATE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid template_type '{payload.template_type}'",
        )
    if payload.allowed_variables is not None:
        _validate_allowed_variables(payload.allowed_variables)

    # Capture old values before mutation
    old_values = {
        "template_name": template.template_name,
        "template_type": template.template_type,
        "body_template": template.body_template,
        "subject_template": template.subject_template,
        "allowed_variables": template.allowed_variables,
        "is_active": template.is_active,
    }

    # Apply changes
    if payload.template_name is not None:
        template.template_name = payload.template_name
    if payload.template_type is not None:
        template.template_type = payload.template_type
    if payload.subject_template is not None:
        template.subject_template = payload.subject_template
    if payload.body_template is not None:
        template.body_template = payload.body_template
    if payload.allowed_variables is not None:
        template.allowed_variables = payload.allowed_variables
    if payload.is_active is not None:
        template.is_active = payload.is_active

    new_values = {
        "template_name": template.template_name,
        "template_type": template.template_type,
        "body_template": template.body_template,
        "subject_template": template.subject_template,
        "allowed_variables": template.allowed_variables,
        "is_active": template.is_active,
    }

    await emit_audit_event(
        session=session,
        organization_id=auth_ctx.organization_id,
        entity_type="outreach_template",
        entity_id=UUID(template.id),
        event_type="template_updated",
        actor_user_id=auth_ctx.user_id,
        old_value=old_values,
        new_value=new_values,
    )
    await session.commit()
    await session.refresh(template)
    return template


# ---------------------------------------------------------------------------
# Import job monitoring  (AC7, AC8)
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC7
async def list_imports(
    session: AsyncSession,
    auth_ctx: AuthContext,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[ImportJob], int]:
    """
    Return paginated ImportJob records for caller's org (read-only monitoring view).

    Returns (jobs, total_count).
    """
    org_id = str(auth_ctx.organization_id)

    count_result = await session.execute(
        select(func.count(ImportJob.id)).where(ImportJob.organization_id == org_id)
    )
    total = count_result.scalar_one()

    offset = (page - 1) * page_size
    result = await session.execute(
        select(ImportJob)
        .where(ImportJob.organization_id == org_id)
        .order_by(ImportJob.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    jobs = list(result.scalars().all())
    return jobs, total


# @forgeplan-spec: AC8
async def get_import(
    session: AsyncSession,
    import_id: str,
    auth_ctx: AuthContext,
) -> ImportJob:
    """
    Return full ImportJob record including error_detail_json.

    Returns 404 for cross-org import_id (not 403 — information disclosure).
    """
    org_id = str(auth_ctx.organization_id)

    result = await session.execute(
        select(ImportJob).where(
            ImportJob.id == import_id,
            ImportJob.organization_id == org_id,
        )
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ImportJob '{import_id}' not found",
        )
    return job


# ---------------------------------------------------------------------------
# Organization settings  (AC9)
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC9
async def get_org_settings(
    session: AsyncSession,
    auth_ctx: AuthContext,
) -> Organization:
    """
    Return the Organization record for the caller's org (serves as org settings).

    Phase 1: Organization table has id, name, created_at.
    settings_json is not stored in the DB — returned as None.
    """
    org_id = str(auth_ctx.organization_id)
    result = await session.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )
    return org


# @forgeplan-spec: AC9
# @forgeplan-spec: AC11
async def update_org_settings(
    session: AsyncSession,
    payload: AdminUpdateOrgRequest,
    auth_ctx: AuthContext,
) -> Organization:
    """
    Update organization settings.

    Phase 1: Only org_name (Organization.name) is persisted.
    settings_json is accepted but not stored (no DB column in Phase 1).

    Writes AuditEvent(event_type=org_settings_updated) atomically.
    """
    org_id = str(auth_ctx.organization_id)
    result = await session.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found",
        )

    old_values: dict = {"org_name": org.name}
    new_values: dict = {}

    if payload.org_name is not None:
        old_values["org_name"] = org.name
        org.name = payload.org_name
        new_values["org_name"] = org.name

    # settings_json is NOT persisted in Phase 1 (no DB column) — excluded from
    # audit trail so the event only reflects fields that are actually stored.

    await emit_audit_event(
        session=session,
        organization_id=auth_ctx.organization_id,
        entity_type="organization",
        entity_id=UUID(org_id),
        event_type="org_settings_updated",
        actor_user_id=auth_ctx.user_id,
        old_value=old_values,
        new_value=new_values,
    )
    await session.commit()
    await session.refresh(org)
    return org


# ---------------------------------------------------------------------------
# Reference data  (AC10)
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC10
async def list_hospitals(
    session: AsyncSession,
    auth_ctx: AuthContext,
) -> list[HospitalReference]:
    """Return HospitalReference records scoped to caller's org."""
    org_id = str(auth_ctx.organization_id)
    result = await session.execute(
        select(HospitalReference)
        .where(HospitalReference.organization_id == org_id)
        .order_by(HospitalReference.hospital_name.asc())
    )
    return list(result.scalars().all())


# @forgeplan-spec: AC10
async def list_decline_reasons(
    session: AsyncSession,
    auth_ctx: AuthContext,
) -> list[DeclineReasonReference]:
    """Return all DeclineReasonReference records ordered by display_order."""
    result = await session.execute(
        select(DeclineReasonReference).order_by(
            DeclineReasonReference.display_order.asc(),
            DeclineReasonReference.label.asc(),
        )
    )
    return list(result.scalars().all())


# @forgeplan-spec: AC10
async def list_payers(
    session: AsyncSession,
    auth_ctx: AuthContext,
) -> list[PayerReference]:
    """
    Return all PayerReference records.

    Note (A4): PayerReference has no organization_id column in Phase 1 ORM.
    Returns all payers (not org-scoped).
    """
    result = await session.execute(
        select(PayerReference).order_by(PayerReference.payer_name.asc())
    )
    return list(result.scalars().all())
