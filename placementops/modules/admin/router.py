# @forgeplan-node: admin-surfaces
# @forgeplan-spec: AC1, AC2, AC3, AC4, AC5, AC6, AC7, AC8, AC9, AC10, AC11
"""
Admin-surfaces FastAPI router.

Role enforcement:
  - Admin-only routes: dependencies=[require_role("admin")] at the decorator level.
    This is a ROUTER-LEVEL dependency (not inside handler bodies) to prevent
    inadvertent exposure if a new handler is added without the gate.
  - AC4 /templates/outreach GET: any authenticated role (get_auth_context only).
  - AC10 /reference/* GET: any authenticated role (get_auth_context only).

Route groups (prefix /api/v1 added by main.py include_router):
  - /api/v1/admin/users         — AC1, AC2, AC3
  - /api/v1/templates/outreach  — AC4, AC5, AC6
  - /api/v1/imports             — AC7, AC8
  - /api/v1/admin/organization  — AC9
  - /api/v1/reference/*         — AC10
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.auth import AuthContext, get_auth_context
from placementops.core.database import get_db
from placementops.modules.admin import service
from placementops.modules.admin.schemas import (
    AdminCreateTemplateRequest,
    AdminCreateUserRequest,
    AdminUpdateOrgRequest,
    AdminUpdateTemplateRequest,
    AdminUpdateUserRequest,
    DeclineReasonReferenceResponse,
    HospitalReferenceResponse,
    ImportJobResponse,
    ImportListResponse,
    OrgSettingsResponse,
    PayerReferenceResponse,
    TemplateListResponse,
    TemplateResponse,
    UserListResponse,
    UserResponse,
)
from placementops.modules.auth.dependencies import require_role

router = APIRouter(tags=["admin"])


# ---------------------------------------------------------------------------
# User management  (AC1, AC2, AC3)
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC1
@router.get(
    "/admin/users",
    response_model=UserListResponse,
    dependencies=[require_role("admin")],
)
async def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> UserListResponse:
    """
    Return paginated list of users scoped to caller's organization.

    Admin only — returns 403 for all other roles.
    """
    users, total = await service.list_users(
        session=db,
        auth_ctx=auth,
        page=page,
        page_size=page_size,
    )
    return UserListResponse(
        items=[UserResponse.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )


# @forgeplan-spec: AC2
@router.post(
    "/admin/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_role("admin")],
)
async def create_user(
    payload: AdminCreateUserRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> UserResponse:
    """
    Create a new user in the caller's organization.

    Sets status=active. Writes AuditEvent(event_type=user_created).
    Admin only — returns 403 for non-admin.
    """
    user = await service.create_user(
        session=db,
        payload=payload,
        auth_ctx=auth,
    )
    return UserResponse.model_validate(user)


# @forgeplan-spec: AC3
@router.patch(
    "/admin/users/{user_id}",
    response_model=UserResponse,
    dependencies=[require_role("admin")],
)
async def update_user(
    user_id: str,
    payload: AdminUpdateUserRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> UserResponse:
    """
    Update a user's role_key and/or status.

    Last-admin guard: returns 400 if deactivating the only active admin.
    Writes AuditEvent(event_type=user_updated).
    Admin only — returns 403 for non-admin.
    """
    user = await service.update_user(
        session=db,
        user_id=user_id,
        payload=payload,
        auth_ctx=auth,
    )
    return UserResponse.model_validate(user)


# ---------------------------------------------------------------------------
# OutreachTemplate management  (AC4, AC5, AC6)
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC4
@router.get(
    "/templates/outreach",
    response_model=TemplateListResponse,
)
async def list_templates(
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> TemplateListResponse:
    """
    Return all OutreachTemplate records for caller's org.

    Accessible to ALL authenticated roles (coordinators need templates when drafting outreach).
    No role restriction — any authenticated user may call this endpoint.
    """
    templates, total = await service.list_templates(
        session=db,
        auth_ctx=auth,
    )
    return TemplateListResponse(
        items=[TemplateResponse.model_validate(t) for t in templates],
        total=total,
    )


# @forgeplan-spec: AC5
@router.post(
    "/templates/outreach",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[require_role("admin")],
)
async def create_template(
    payload: AdminCreateTemplateRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> TemplateResponse:
    """
    Create a new OutreachTemplate.

    Validates allowed_variables against safe allowlist.
    Writes AuditEvent(event_type=template_created).
    Admin only — returns 403 for non-admin.
    """
    template = await service.create_template(
        session=db,
        payload=payload,
        auth_ctx=auth,
    )
    return TemplateResponse.model_validate(template)


# @forgeplan-spec: AC6
@router.patch(
    "/templates/outreach/{template_id}",
    response_model=TemplateResponse,
    dependencies=[require_role("admin")],
)
async def update_template(
    template_id: str,
    payload: AdminUpdateTemplateRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> TemplateResponse:
    """
    Update an OutreachTemplate.

    Returns 404 for cross-org template_id (not 403 — avoids info disclosure).
    Validates allowed_variables against safe allowlist.
    Writes AuditEvent(event_type=template_updated).
    Admin only — returns 403 for non-admin.
    """
    template = await service.update_template(
        session=db,
        template_id=template_id,
        payload=payload,
        auth_ctx=auth,
    )
    return TemplateResponse.model_validate(template)


# ---------------------------------------------------------------------------
# Import job monitoring  (AC7, AC8)
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC7
@router.get(
    "/imports",
    response_model=ImportListResponse,
    dependencies=[require_role("admin")],
)
async def list_imports(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> ImportListResponse:
    """
    Return paginated ImportJob list with status and row counts.

    Read-only monitoring view — no create/update endpoints exist in this module.
    Admin only — returns 403 for non-admin.
    """
    jobs, total = await service.list_imports(
        session=db,
        auth_ctx=auth,
        page=page,
        page_size=page_size,
    )
    return ImportListResponse(
        items=[ImportJobResponse.model_validate(j) for j in jobs],
        total=total,
        page=page,
        page_size=page_size,
    )


# @forgeplan-spec: AC8
@router.get(
    "/imports/{import_id}",
    response_model=ImportJobResponse,
    dependencies=[require_role("admin")],
)
async def get_import(
    import_id: str,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> ImportJobResponse:
    """
    Return full ImportJob including error_detail_json.

    Returns 404 for cross-org import_id.
    Admin only — returns 403 for non-admin.
    """
    job = await service.get_import(
        session=db,
        import_id=import_id,
        auth_ctx=auth,
    )
    return ImportJobResponse.model_validate(job)


# ---------------------------------------------------------------------------
# Organization settings  (AC9)
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC9
@router.get(
    "/admin/organization",
    response_model=OrgSettingsResponse,
    dependencies=[require_role("admin")],
)
async def get_org_settings(
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> OrgSettingsResponse:
    """
    Return org settings for the caller's organization.

    Admin only — returns 403 for non-admin.
    """
    org = await service.get_org_settings(session=db, auth_ctx=auth)
    return OrgSettingsResponse(
        id=org.id,
        org_name=org.name,
        settings_json=None,  # Phase 1: no settings_json column in DB
        updated_at=None,  # Phase 1: Organization model has no updated_at column
    )


# @forgeplan-spec: AC9
@router.patch(
    "/admin/organization",
    response_model=OrgSettingsResponse,
    dependencies=[require_role("admin")],
)
async def update_org_settings(
    payload: AdminUpdateOrgRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> OrgSettingsResponse:
    """
    Update org settings.

    Writes AuditEvent(event_type=org_settings_updated).
    Admin only — returns 403 for non-admin.
    """
    org = await service.update_org_settings(
        session=db,
        payload=payload,
        auth_ctx=auth,
    )
    # Return the persisted DB row — org_name reflects the committed value.
    # settings_json and updated_at are None (no DB columns in Phase 1).
    return OrgSettingsResponse(
        id=org.id,
        org_name=org.name,
        settings_json=None,  # Phase 1: no settings_json column in DB
        updated_at=None,  # Phase 1: Organization model has no updated_at column
    )


# ---------------------------------------------------------------------------
# Reference data  (AC10)
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC10
@router.get(
    "/reference/hospitals",
    response_model=list[HospitalReferenceResponse],
)
async def list_hospitals(
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> list[HospitalReferenceResponse]:
    """
    Return HospitalReference records for caller's org.

    Accessible to ALL authenticated roles.
    """
    hospitals = await service.list_hospitals(session=db, auth_ctx=auth)
    return [HospitalReferenceResponse.model_validate(h) for h in hospitals]


# @forgeplan-spec: AC10
@router.get(
    "/reference/decline-reasons",
    response_model=list[DeclineReasonReferenceResponse],
)
async def list_decline_reasons(
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> list[DeclineReasonReferenceResponse]:
    """
    Return all DeclineReasonReference records.

    Accessible to ALL authenticated roles.
    """
    reasons = await service.list_decline_reasons(session=db, auth_ctx=auth)
    return [DeclineReasonReferenceResponse.model_validate(r) for r in reasons]


# @forgeplan-spec: AC10
@router.get(
    "/reference/payers",
    response_model=list[PayerReferenceResponse],
)
async def list_payers(
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> list[PayerReferenceResponse]:
    """
    Return all PayerReference records.

    Accessible to ALL authenticated roles.
    Note: PayerReference has no organization_id in Phase 1 — returns all payers.
    """
    payers = await service.list_payers(session=db, auth_ctx=auth)
    return [PayerReferenceResponse.model_validate(p) for p in payers]
