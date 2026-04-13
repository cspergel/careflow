# @forgeplan-node: outreach-module
# @forgeplan-spec: AC1
# @forgeplan-spec: AC3
# @forgeplan-spec: AC4
# @forgeplan-spec: AC5
# @forgeplan-spec: AC6
# @forgeplan-spec: AC7
# @forgeplan-spec: AC8
# @forgeplan-spec: AC9
# @forgeplan-spec: AC10
"""
Outreach module FastAPI router.

Endpoints:
  POST  /api/v1/cases/{case_id}/outreach-actions             — create (AC1, AC8)
  GET   /api/v1/cases/{case_id}/outreach-actions             — per-case action history (F10)
  PATCH /api/v1/outreach-actions/{action_id}                 — edit draft (AC3)
  POST  /api/v1/outreach-actions/{action_id}/submit-for-approval — submit (AC4)
  POST  /api/v1/outreach-actions/{action_id}/approve         — approve (AC5)
  POST  /api/v1/outreach-actions/{action_id}/mark-sent       — mark sent (AC6)
  POST  /api/v1/outreach-actions/{action_id}/cancel          — cancel (AC7)
  GET   /api/v1/queues/outreach                              — queue (AC9)
  GET   /api/v1/templates/outreach                           — template listing (AC10)
  POST|PATCH|DELETE /api/v1/templates/outreach               — 405 (AC10)

Role enforcement: placement_coordinator or admin only for all mutating endpoints.
GET /queues/outreach: placement_coordinator, manager, admin (F9).
GET /cases/{case_id}/outreach-actions: placement_coordinator, manager, admin (F10).
"""
# @forgeplan-decision: D-outreach-3-405-explicit-handlers -- Explicit POST/PATCH/DELETE handlers on /templates/outreach return 405. Why: FastAPI does not automatically return 405 for unregistered methods; explicit handlers with raise HTTPException(405) are required to satisfy AC10's method-not-allowed constraint

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.exceptions import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.auth import AuthContext, get_auth_context
from placementops.core.database import get_db
from placementops.modules.auth.dependencies import require_role, require_write_permission
from placementops.modules.outreach import service
from placementops.modules.outreach.schemas import (
    CaseOutreachActionListResponse,
    OutreachActionCreate,
    OutreachActionPatch,
    OutreachActionResponse,
    OutreachQueueResponse,
    TemplateListResponse,
    OutreachTemplateResponse,
)

router = APIRouter(tags=["outreach"])

# Roles permitted for all mutating outreach operations
_OUTREACH_WRITE_ROLES = ("placement_coordinator", "admin")

# Roles permitted for read-only outreach operations (F9, F10)
_OUTREACH_READ_ROLES = ("placement_coordinator", "manager", "admin")


# ---------------------------------------------------------------------------
# AC1, AC8 — Create outreach action
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC1
# @forgeplan-spec: AC8
@router.post(
    "/cases/{case_id}/outreach-actions",
    response_model=OutreachActionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        require_role(*_OUTREACH_WRITE_ROLES),
        require_write_permission,
    ],
)
async def create_outreach_action(
    case_id: UUID,
    payload: OutreachActionCreate,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> OutreachActionResponse:
    """
    Create an OutreachAction for a case.

    email/sms/voicemail_drop/voice_ai: created at approval_status=draft.
    phone_manual/task: created at approval_status=sent; case advances to
    pending_facility_response atomically (AC8).

    Template variable allowlist checked before rendering (AC1, AC2).
    Roles: placement_coordinator, admin.
    """
    action = await service.create_outreach_action(
        session=db,
        case_id=case_id,
        payload=payload,
        auth_ctx=auth,
    )
    return OutreachActionResponse.model_validate(action)


# ---------------------------------------------------------------------------
# F10 — Per-case outreach action history
# ---------------------------------------------------------------------------


@router.get(
    "/cases/{case_id}/outreach-actions",
    response_model=CaseOutreachActionListResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[require_role(*_OUTREACH_READ_ROLES)],
)
async def get_case_outreach_actions(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> CaseOutreachActionListResponse:
    """
    Return outreach action history for a specific case (F10).

    Scoped to the authenticated user's organization.
    Returns 404 if the case is not found or does not belong to the org.
    Roles: placement_coordinator, manager, admin.
    """
    items, total = await service.get_case_outreach_actions(
        session=db,
        case_id=case_id,
        auth_ctx=auth,
    )
    return CaseOutreachActionListResponse(
        items=[OutreachActionResponse.model_validate(a) for a in items],
        total=total,
        case_id=case_id,
    )


# ---------------------------------------------------------------------------
# AC3 — Edit draft
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC3
@router.patch(
    "/outreach-actions/{action_id}",
    response_model=OutreachActionResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[
        require_role(*_OUTREACH_WRITE_ROLES),
        require_write_permission,
    ],
)
async def patch_outreach_action(
    action_id: UUID,
    patch: OutreachActionPatch,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> OutreachActionResponse:
    """
    Edit draft_subject and/or draft_body on a draft OutreachAction.

    Returns 409 if not in draft state.
    Roles: placement_coordinator, admin.
    """
    action = await service.patch_outreach_action(
        session=db,
        action_id=action_id,
        patch=patch,
        auth_ctx=auth,
    )
    return OutreachActionResponse.model_validate(action)


# ---------------------------------------------------------------------------
# AC4 — Submit for approval
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC4
@router.post(
    "/outreach-actions/{action_id}/submit-for-approval",
    response_model=OutreachActionResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[
        require_role(*_OUTREACH_WRITE_ROLES),
        require_write_permission,
    ],
)
async def submit_for_approval(
    action_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> OutreachActionResponse:
    """
    Submit a draft OutreachAction for approval.

    Advances action to pending_approval and case to outreach_pending_approval.
    Returns 409 if action is not in draft state.
    Roles: placement_coordinator, admin.
    """
    action = await service.submit_for_approval(
        session=db,
        action_id=action_id,
        auth_ctx=auth,
    )
    return OutreachActionResponse.model_validate(action)


# ---------------------------------------------------------------------------
# AC5 — Approve
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC5
@router.post(
    "/outreach-actions/{action_id}/approve",
    response_model=OutreachActionResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[
        require_role(*_OUTREACH_WRITE_ROLES),
        require_write_permission,
    ],
)
async def approve_action(
    action_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> OutreachActionResponse:
    """
    Approve a pending_approval OutreachAction.

    Sets approved_by_user_id and approved_at. Advances case to outreach_in_progress
    if this is the first approved action for the case.
    Returns 409 if action is not in pending_approval state.
    Roles: placement_coordinator, admin.
    """
    action = await service.approve_action(
        session=db,
        action_id=action_id,
        auth_ctx=auth,
    )
    return OutreachActionResponse.model_validate(action)


# ---------------------------------------------------------------------------
# AC6 — Mark sent
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC6
@router.post(
    "/outreach-actions/{action_id}/mark-sent",
    response_model=OutreachActionResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[
        require_role(*_OUTREACH_WRITE_ROLES),
        require_write_permission,
    ],
)
async def mark_sent(
    action_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> OutreachActionResponse:
    """
    Mark an approved OutreachAction as sent (stub delivery).

    Sets approval_status=sent, sent_by_user_id, sent_at.
    AuditEvent never logs draft_body or draft_subject (AC6 constraint).
    Advances case to pending_facility_response if first sent action.
    Returns 409 if action is not in approved state.
    Roles: placement_coordinator, admin.
    """
    action = await service.mark_sent(
        session=db,
        action_id=action_id,
        auth_ctx=auth,
    )
    return OutreachActionResponse.model_validate(action)


# ---------------------------------------------------------------------------
# AC7 — Cancel
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC7
@router.post(
    "/outreach-actions/{action_id}/cancel",
    response_model=OutreachActionResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[
        require_role(*_OUTREACH_WRITE_ROLES),
        require_write_permission,
    ],
)
async def cancel_action(
    action_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> OutreachActionResponse:
    """
    Cancel a pre-sent OutreachAction.

    Returns 409 with 'sent records are permanent communication records' if sent.
    Roles: placement_coordinator, admin.
    """
    action = await service.cancel_action(
        session=db,
        action_id=action_id,
        auth_ctx=auth,
    )
    return OutreachActionResponse.model_validate(action)


# ---------------------------------------------------------------------------
# AC9 — Outreach queue
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC9
@router.get(
    "/queues/outreach",
    response_model=OutreachQueueResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[require_role(*_OUTREACH_READ_ROLES)],
)
async def get_outreach_queue(
    approval_status: str | None = Query(default=None, description="Filter by approval_status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> OutreachQueueResponse:
    """
    Return cross-case outreach actions filterable by approval_status (AC9).

    Scoped to the authenticated user's organization.
    Unauthenticated requests return 401 (enforced by get_auth_context).
    """
    items, total = await service.get_outreach_queue(
        session=db,
        auth_ctx=auth,
        approval_status_filter=approval_status,
        page=page,
        page_size=page_size,
    )
    return OutreachQueueResponse(
        items=[OutreachActionResponse.model_validate(a) for a in items],
        total=total,
        page=page,
        page_size=page_size,
    )


# ---------------------------------------------------------------------------
# AC10 — Template listing (read-only)
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC10
@router.get(
    "/templates/outreach",
    response_model=TemplateListResponse,
    status_code=status.HTTP_200_OK,
)
async def get_templates(
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> TemplateListResponse:
    """
    List active outreach templates for the organization (AC10).

    Read-only endpoint. Template CRUD is owned by admin-surfaces.
    """
    templates = await service.get_templates(session=db, auth_ctx=auth)
    return TemplateListResponse(
        templates=[OutreachTemplateResponse.model_validate(t) for t in templates]
    )


# F13: Explicit route registration order — GET must be registered BEFORE the 405
# method-not-allowed handlers on the same path. FastAPI resolves routes in
# registration order; if a 405 handler were registered first, GET requests would
# incorrectly match that handler and return 405 instead of 200. Do NOT reorder.
# AC10: Return 405 for POST/PATCH/DELETE on /templates/outreach
# These are explicitly defined to prevent fallthrough to 404.

@router.post(
    "/templates/outreach",
    status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
    include_in_schema=False,
)
async def templates_post_not_allowed() -> None:
    """POST is not allowed — template management is handled by admin-surfaces."""
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Template management is handled by admin-surfaces",
    )


@router.patch(
    "/templates/outreach",
    status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
    include_in_schema=False,
)
async def templates_patch_not_allowed() -> None:
    """PATCH is not allowed — template management is handled by admin-surfaces."""
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Template management is handled by admin-surfaces",
    )


@router.delete(
    "/templates/outreach",
    status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
    include_in_schema=False,
)
async def templates_delete_not_allowed() -> None:
    """DELETE is not allowed — template management is handled by admin-surfaces."""
    raise HTTPException(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        detail="Template management is handled by admin-surfaces",
    )
