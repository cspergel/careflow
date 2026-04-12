# @forgeplan-node: analytics-module
"""
Analytics module FastAPI router.

Endpoints:
  GET /api/v1/queues/operations          — operational queue (AC1, AC2, AC3, AC8)
  GET /api/v1/queues/manager-summary     — queue aging distribution (AC4, AC8)
  GET /api/v1/analytics/dashboard        — case volume + placement rate (AC5)
  GET /api/v1/analytics/outreach-performance — accept/decline rates (AC6)

Role enforcement (AC1):
  - /queues/operations: placement_coordinator, clinical_reviewer, manager, admin
  - All other endpoints: manager, admin only
  - intake_staff, read_only: 403 on ALL endpoints

Constraint: role gate executes BEFORE any database query (via require_role dependency
injected before service calls are made).
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

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.auth import AuthContext, get_auth_context
from placementops.core.database import get_db
from placementops.modules.auth.dependencies import require_role
from placementops.modules.analytics import service
from placementops.modules.analytics.schemas import (
    DashboardReport,
    ManagerSummary,
    OutreachPerformanceReport,
    PaginatedOperationsQueue,
)

router = APIRouter(tags=["analytics"])

# Role sets — defined once to avoid magic strings scattered through endpoints
_OPERATIONS_ROLES = ("placement_coordinator", "clinical_reviewer", "manager", "admin")
_MANAGER_ROLES = ("manager", "admin")


# ---------------------------------------------------------------------------
# AC1, AC2, AC3, AC8 — GET /api/v1/queues/operations
# ---------------------------------------------------------------------------

@router.get(
    "/queues/operations",
    response_model=PaginatedOperationsQueue,
    summary="Operational case queue with SLA aging flags",
)
async def get_operations_queue(
    status: str | None = Query(default=None, description="Filter by current_status"),
    hospital_id: UUID | None = Query(default=None),
    assigned_coordinator_user_id: UUID | None = Query(default=None),
    priority: str | None = Query(default=None, description="routine | urgent | emergent"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    # Role gate: placement_coordinator, clinical_reviewer, manager, admin
    # @forgeplan-spec: AC1 — role check executes BEFORE any DB query via Depends
    auth: AuthContext = require_role(*_OPERATIONS_ROLES),
    session: AsyncSession = Depends(get_db),
) -> PaginatedOperationsQueue:
    """
    Returns paginated OperationsQueueItem list scoped to caller's organization.

    Accessible to: placement_coordinator, clinical_reviewer, manager, admin.
    Returns 403 for intake_staff and read_only.
    """
    return await service.get_operations_queue(
        session=session,
        organization_id=auth.organization_id,
        status_filter=status,
        hospital_id=hospital_id,
        assigned_coordinator_user_id=assigned_coordinator_user_id,
        priority=priority,
        page=page,
        page_size=page_size,
    )


# ---------------------------------------------------------------------------
# AC4, AC8 — GET /api/v1/queues/manager-summary
# ---------------------------------------------------------------------------

@router.get(
    "/queues/manager-summary",
    response_model=ManagerSummary,
    summary="Queue aging distribution and SLA breach cases",
)
async def get_manager_summary(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    # Role gate: manager, admin only
    # @forgeplan-spec: AC1 — 403 for all other roles without touching DB
    auth: AuthContext = require_role(*_MANAGER_ROLES),
    session: AsyncSession = Depends(get_db),
) -> ManagerSummary:
    """
    Returns queue aging distribution, SLA breach counts, and breach case list.

    Accessible to: manager, admin only.
    """
    return await service.get_manager_summary(
        session=session,
        organization_id=auth.organization_id,
        page=page,
        page_size=page_size,
    )


# ---------------------------------------------------------------------------
# AC5 — GET /api/v1/analytics/dashboard
# ---------------------------------------------------------------------------

@router.get(
    "/analytics/dashboard",
    response_model=DashboardReport,
    summary="Case volume, placement rate, and stage cycle times",
)
async def get_dashboard(
    date_from: date | None = Query(default=None, description="ISO 8601 date; defaults to 30 days ago"),
    date_to: date | None = Query(default=None, description="ISO 8601 date; defaults to today"),
    # Role gate: manager, admin only
    # @forgeplan-spec: AC1 — 403 for all other roles without touching DB
    auth: AuthContext = require_role(*_MANAGER_ROLES),
    session: AsyncSession = Depends(get_db),
) -> DashboardReport:
    """
    Returns case volume by status, placement rate, and avg cycle time per stage.

    Defaults to last 30 days. Returns 400 if date_from > date_to.
    Accessible to: manager, admin only.
    """
    return await service.get_dashboard_report(
        session=session,
        organization_id=auth.organization_id,
        date_from=date_from,
        date_to=date_to,
    )


# ---------------------------------------------------------------------------
# AC6 — GET /api/v1/analytics/outreach-performance
# ---------------------------------------------------------------------------

@router.get(
    "/analytics/outreach-performance",
    response_model=OutreachPerformanceReport,
    summary="Accept/decline rates by facility and decline reason",
)
async def get_outreach_performance(
    date_from: date | None = Query(default=None, description="ISO 8601 date; defaults to 30 days ago"),
    date_to: date | None = Query(default=None, description="ISO 8601 date; defaults to today"),
    # Role gate: manager, admin only
    # @forgeplan-spec: AC1 — 403 for all other roles without touching DB
    auth: AuthContext = require_role(*_MANAGER_ROLES),
    session: AsyncSession = Depends(get_db),
) -> OutreachPerformanceReport:
    """
    Returns accept/decline rates grouped by facility and by decline_reason_code.

    Defaults to last 30 days. Returns 400 if date_from > date_to.
    Accessible to: manager, admin only.
    """
    return await service.get_outreach_performance(
        session=session,
        organization_id=auth.organization_id,
        date_from=date_from,
        date_to=date_to,
    )
