# @forgeplan-node: matching-module
# @forgeplan-spec: AC1
# @forgeplan-spec: AC2
# @forgeplan-spec: AC3
# @forgeplan-spec: AC4
# @forgeplan-spec: AC5
# @forgeplan-spec: AC13
# @forgeplan-spec: AC14
# @forgeplan-spec: AC16
"""
Matching module FastAPI router.

Endpoints:
  POST  /api/v1/cases/{case_id}/matches/generate  — run scoring pipeline (AC1, AC2, AC3, AC4, AC5)
  GET   /api/v1/cases/{case_id}/matches            — latest match set (AC13)
  PATCH /api/v1/cases/{case_id}/matches/{match_id}/select  — toggle selected_for_outreach (AC14)

Role enforcement:
  - POST generate: clinical_reviewer, placement_coordinator, admin (AC16)
  - GET matches: all authenticated roles
  - PATCH select: clinical_reviewer, placement_coordinator, admin (AC16)
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Body, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.auth import AuthContext, get_auth_context
from placementops.core.database import get_db
from placementops.modules.auth.dependencies import require_role, require_write_permission
from placementops.modules.matching import service
from placementops.modules.matching.schemas import (
    MatchGenerateRequest,
    MatchListResponse,
    FacilityMatchResponse,
    SelectToggleResponse,
)

router = APIRouter(tags=["matching"])


# ---------------------------------------------------------------------------
# AC1, AC2, AC3, AC4, AC5 — Generate matches
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC1
# @forgeplan-spec: AC2
# @forgeplan-spec: AC16
@router.post(
    "/cases/{case_id}/matches/generate",
    response_model=MatchListResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[
        require_role("clinical_reviewer", "placement_coordinator", "admin"),
        require_write_permission,
    ],
)
async def generate_matches(
    case_id: UUID,
    payload: MatchGenerateRequest = Body(default=MatchGenerateRequest()),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> MatchListResponse:
    """
    Run the four-stage matching pipeline for a case.

    Requires a finalized ClinicalAssessment (AC1).
    Creates FacilityMatch rows for all active facilities — scored non-excluded
    facilities plus hard-excluded facilities (AC2, AC3, AC4, AC5).
    Advances case status to facility_options_generated (AC2).

    Re-scoring inserts new rows; old rows are preserved (AC15).
    selected_for_outreach=False on all new rows (AC15).

    Roles: clinical_reviewer, placement_coordinator, admin (AC16).
    """
    new_matches = await service.generate_matches(
        session=db,
        case_id=case_id,
        assessment_id=payload.assessment_id,
        auth_ctx=auth,
    )

    return MatchListResponse(
        matches=[FacilityMatchResponse.model_validate(m) for m in new_matches],
        total=len(new_matches),
    )


# ---------------------------------------------------------------------------
# AC13 — Get latest match set
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC13
@router.get(
    "/cases/{case_id}/matches",
    response_model=MatchListResponse,
    status_code=status.HTTP_200_OK,
)
async def get_matches(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> MatchListResponse:
    """
    Return the latest match set for a case.

    Returns all FacilityMatch rows from the most recent generation run
    ordered by rank_order ASC (excluded facilities with rank_order=-1 at bottom).

    explanation_text is returned verbatim from storage — never regenerated (AC11).
    All component scores included for auditability (AC10).
    """
    matches = await service.get_matches(
        session=db,
        case_id=case_id,
        auth_ctx=auth,
    )

    return MatchListResponse(
        matches=[FacilityMatchResponse.model_validate(m) for m in matches],
        total=len(matches),
    )


# ---------------------------------------------------------------------------
# AC14 — Toggle selected_for_outreach
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC14
# @forgeplan-spec: AC16
@router.patch(
    "/cases/{case_id}/matches/{match_id}/select",
    response_model=SelectToggleResponse,
    status_code=status.HTTP_200_OK,
    dependencies=[
        require_role("clinical_reviewer", "placement_coordinator", "admin"),
        require_write_permission,
    ],
)
async def select_match(
    case_id: UUID,
    match_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> SelectToggleResponse:
    """
    Toggle selected_for_outreach on a FacilityMatch.

    Multiple facilities may be simultaneously selected (AC14).
    Flipping an already-selected facility deselects it.
    Writes case_activity_event and AuditEvent on each toggle.

    Roles: clinical_reviewer, placement_coordinator, admin (AC16).
    """
    updated_match = await service.toggle_select(
        session=db,
        case_id=case_id,
        match_id=match_id,
        auth_ctx=auth,
    )

    action = "selected" if updated_match.selected_for_outreach else "deselected"

    return SelectToggleResponse(
        match_id=UUID(updated_match.id),
        facility_id=UUID(updated_match.facility_id),
        selected_for_outreach=updated_match.selected_for_outreach,
        message=f"Facility {action} for outreach consideration",
    )
