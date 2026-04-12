# @forgeplan-node: outcomes-module
# @forgeplan-spec: AC1, AC2, AC3, AC4, AC5, AC6, AC7, AC8, AC9, AC10, AC11, AC12, AC13, AC14, AC15, AC16
"""
Outcomes module FastAPI router.

Endpoints:
  POST /api/v1/cases/{case_id}/outcomes             — record outcome (201)
  GET  /api/v1/cases/{case_id}/outcomes             — outcome history (200)
  GET  /api/v1/cases/{case_id}/timeline             — case timeline (200)
  POST /api/v1/cases/{case_id}/advance-status       — late-stage transitions: retry routing + closure (200)

Role enforcement:
  - POST/GET outcomes: placement_coordinator or admin (AC1)
  - GET timeline: placement_coordinator or admin
  - POST advance-status: placement_coordinator or admin (retry routing AC9);
    closure additionally requires manager or admin role check in service (AC11)
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.auth import AuthContext, get_auth_context
from placementops.core.database import get_db
from placementops.modules.auth.dependencies import require_role, require_write_permission
from placementops.modules.outcomes import service
from placementops.modules.intake.schemas import PatientCaseSummary
from placementops.modules.outcomes.schemas import (
    CaseActivityEventResponse,
    CaseTimelineResponse,
    OutcomeHistoryResponse,
    PlacementOutcomeCreate,
    PlacementOutcomeResponse,
    StatusTransitionRequest,
)

router = APIRouter(tags=["outcomes"])

# Roles permitted to record and view outcomes
_OUTCOMES_ROLES = ("placement_coordinator", "admin")

# Roles permitted for status transitions (coordinator + admin for retry routing;
# manager/admin for closure is enforced additionally in the service layer)
_TRANSITION_ROLES = ("placement_coordinator", "admin", "manager")


# ---------------------------------------------------------------------------
# AC1-AC10, AC14-AC16 — Record outcome
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC1
# @forgeplan-spec: AC2
# @forgeplan-spec: AC3
# @forgeplan-spec: AC4
# @forgeplan-spec: AC5
# @forgeplan-spec: AC6
# @forgeplan-spec: AC7
# @forgeplan-spec: AC8
# @forgeplan-spec: AC10
# @forgeplan-spec: AC14
# @forgeplan-spec: AC15
# @forgeplan-spec: AC16
@router.post(
    "/cases/{case_id}/outcomes",
    response_model=PlacementOutcomeResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[
        require_role(*_OUTCOMES_ROLES),
        require_write_permission,
    ],
)
async def record_outcome(
    case_id: UUID,
    payload: PlacementOutcomeCreate,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> PlacementOutcomeResponse:
    """
    Record a placement outcome for a case.

    - accepted: validates sent outreach for facility_id; advances case to accepted;
      auto-cancels draft/pending_approval/approved outreach.
    - declined: requires facility_id + sent outreach + valid decline_reason_code;
      advances case to declined_retry_needed.
    - placed: validates sent outreach; advances case to placed; auto-cancels outreach.
    - family_declined/withdrawn: nullable facility_id; writes outcome record without
      advancing case status; manager must confirm closure separately.

    All outcome types write a PlacementOutcome row, AuditEvent, and status record.
    Roles: placement_coordinator, admin.
    """
    outcome = await service.record_outcome(
        session=db,
        case_id=case_id,
        payload=payload,
        auth_ctx=auth,
    )
    return PlacementOutcomeResponse.model_validate(outcome)


# ---------------------------------------------------------------------------
# AC13 — Outcome history
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC13
@router.get(
    "/cases/{case_id}/outcomes",
    response_model=OutcomeHistoryResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[require_role(*_OUTCOMES_ROLES)],
)
async def get_outcome_history(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> OutcomeHistoryResponse:
    """
    Return all PlacementOutcome records for the case in creation order.

    Scoped to the authenticated user's organization.
    Roles: placement_coordinator, admin.
    """
    outcomes = await service.get_outcomes(
        session=db,
        case_id=case_id,
        auth_ctx=auth,
    )
    return OutcomeHistoryResponse(
        items=[PlacementOutcomeResponse.model_validate(o) for o in outcomes],
        total=len(outcomes),
    )


# ---------------------------------------------------------------------------
# AC12 — Case timeline
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC12
@router.get(
    "/cases/{case_id}/timeline",
    response_model=CaseTimelineResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[require_role(*_OUTCOMES_ROLES)],
)
async def get_case_timeline(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> CaseTimelineResponse:
    """
    Return the chronological feed of case status transitions.

    Events are sourced from CaseStatusHistory (written by all modules that
    call transition_case_status). Ordered by entered_at ascending.

    Roles: placement_coordinator, admin.
    """
    history_rows = await service.get_timeline(
        session=db,
        case_id=case_id,
        auth_ctx=auth,
    )
    events = [
        CaseActivityEventResponse(
            case_id=UUID(row.patient_case_id),
            actor_user_id=UUID(row.actor_user_id) if row.actor_user_id else None,
            event_type="status_changed",
            old_status=row.from_status,
            new_status=row.to_status,
            occurred_at=row.entered_at,
        )
        for row in history_rows
    ]
    return CaseTimelineResponse(events=events, total=len(events))


# ---------------------------------------------------------------------------
# AC9, AC11 — Status transition (retry routing + closure)
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC9
# @forgeplan-spec: AC11
@router.post(
    "/cases/{case_id}/status-transition",
    response_model=PatientCaseSummary,
    status_code=status.HTTP_200_OK,
    dependencies=[
        require_role(*_TRANSITION_ROLES),
        require_write_permission,
    ],
)
async def post_status_transition(
    case_id: UUID,
    payload: StatusTransitionRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> PatientCaseSummary:
    """
    Perform a case status transition.

    Retry routing (AC9):
      POST with to_status=ready_for_matching or outreach_pending_approval from
      declined_retry_needed; placement_coordinator or admin permitted.

    Case closure (AC11):
      POST with to_status=closed; manager or admin only; transition_reason required.

    All transitions are validated by the shared state machine handler.
    """
    updated_case = await service.status_transition(
        session=db,
        case_id=case_id,
        payload=payload,
        auth_ctx=auth,
    )
    return PatientCaseSummary.model_validate(updated_case)
