# @forgeplan-node: clinical-module
"""
Clinical module FastAPI router.

Endpoints:
  GET  /api/v1/queues/clinical          — reviewer queue (AC1)
  POST /api/v1/cases/{id}/assign        — assign reviewer + advance status (AC2)
  POST /api/v1/cases/{id}/assessments   — create assessment draft (AC3)
  GET  /api/v1/cases/{id}/assessments   — list assessment versions (AC5)
  PATCH /api/v1/assessments/{id}        — update assessment, creates new version (AC4)
  POST /api/v1/cases/{id}/clinical-transition — backward transition with reason (AC9)
  GET  /api/v1/cases/{id}/assessments/latest-finalized — for matching engine (AC11)

Role enforcement:
  - POST /cases/{id}/assessments, PATCH /assessments/{id}: clinical_reviewer + admin only (AC10)
  - POST /cases/{id}/assign: clinical_reviewer + admin (must assign a clinical_reviewer) (AC2)
  - POST /cases/{id}/clinical-transition: clinical_reviewer + admin (AC9)
  - GET endpoints: any authenticated user
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
# @forgeplan-spec: AC12

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.auth import AuthContext, get_auth_context
from placementops.core.database import get_db
from placementops.modules.auth.dependencies import require_role, require_write_permission
from placementops.modules.clinical import service
from placementops.modules.clinical.schemas import (
    AssessmentCreateRequest,
    AssessmentListResponse,
    AssessmentResponse,
    AssessmentUpdateRequest,
    AssessmentVersionEntry,
    AssignReviewerRequest,
    AssignReviewerResponse,
    BackwardTransitionRequest,
    ClinicalTransitionResponse,
)
from placementops.modules.intake.schemas import PaginatedCasesResponse, PatientCaseSummary

router = APIRouter(tags=["clinical"])


# ---------------------------------------------------------------------------
# AC1 — Clinical reviewer queue
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC1
@router.get(
    "/queues/clinical",
    response_model=PaginatedCasesResponse,
    dependencies=[require_role("clinical_reviewer", "admin")],
)
async def get_clinical_queue(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> PaginatedCasesResponse:
    """
    Return cases at needs_clinical_review scoped to authenticated org.

    AC1: only org-scoped cases returned.
    """
    cases, total = await service.list_clinical_queue(
        session=db,
        organization_id=auth.organization_id,
        page=page,
        page_size=page_size,
    )
    return PaginatedCasesResponse(
        cases=[PatientCaseSummary.model_validate(c) for c in cases],
        total=total,
        page=page,
        page_size=page_size,
    )


# ---------------------------------------------------------------------------
# AC2 — Assign clinical reviewer
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC2
@router.post(
    "/cases/{case_id}/assign",
    response_model=AssignReviewerResponse,
    dependencies=[
        require_role("clinical_reviewer", "admin"),
        require_write_permission,
    ],
)
async def assign_reviewer(
    case_id: UUID,
    payload: AssignReviewerRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> AssignReviewerResponse:
    """
    Assign a clinical reviewer to a case and advance it to under_clinical_review.

    AC2: case_status_history row written; case_activity_events published.
    """
    updated_case = await service.assign_clinical_reviewer(
        session=db,
        case_id=case_id,
        organization_id=auth.organization_id,
        reviewer_user_id=payload.user_id,
        actor_role=auth.role_key,
        actor_user_id=auth.user_id,
    )
    return AssignReviewerResponse(
        case_id=UUID(updated_case.id),
        assigned_user_id=payload.user_id,
        new_case_status=updated_case.current_status,
        message="Reviewer assigned; case advanced to under_clinical_review",
    )


# ---------------------------------------------------------------------------
# AC3 — Create assessment draft
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC3
# @forgeplan-spec: AC10
@router.post(
    "/cases/{case_id}/assessments",
    status_code=status.HTTP_201_CREATED,
    response_model=AssessmentResponse,
    dependencies=[
        require_role("clinical_reviewer", "admin"),
        require_write_permission,
    ],
)
async def create_assessment(
    case_id: UUID,
    payload: AssessmentCreateRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> AssessmentResponse:
    """
    Create a ClinicalAssessment draft for the given case.

    No PatientCase status change occurs at draft creation.
    Only clinical_reviewer and admin may create assessments.
    """
    assessment = await service.create_assessment(
        session=db,
        case_id=case_id,
        organization_id=auth.organization_id,
        payload=payload,
        reviewer_user_id=auth.user_id,
        actor_role=auth.role_key,
    )
    return AssessmentResponse.model_validate(assessment)


# ---------------------------------------------------------------------------
# AC5 — List assessment versions
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC5
@router.get(
    "/cases/{case_id}/assessments",
    response_model=AssessmentListResponse,
)
async def list_assessments(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> AssessmentListResponse:
    """
    Return all assessment versions for a case ordered chronologically.

    AC5: all versions returned with correct review_status on each.
    """
    assessments = await service.list_assessments(
        session=db,
        case_id=case_id,
        organization_id=auth.organization_id,
    )
    # Compute version_sequence as 1-based ordinal in chronological order (F37)
    versioned = [
        AssessmentVersionEntry(
            **AssessmentResponse.model_validate(a).model_dump(),
            version_sequence=seq,
        )
        for seq, a in enumerate(assessments, start=1)
    ]
    return AssessmentListResponse(
        assessments=versioned,
        total=len(versioned),
    )


# ---------------------------------------------------------------------------
# AC4, AC6, AC7 — Update assessment (creates new version row)
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC4
# @forgeplan-spec: AC6
# @forgeplan-spec: AC7
# @forgeplan-spec: AC10
@router.patch(
    "/assessments/{assessment_id}",
    response_model=AssessmentResponse,
    dependencies=[
        require_role("clinical_reviewer", "admin"),
        require_write_permission,
    ],
)
async def update_assessment(
    assessment_id: UUID,
    payload: AssessmentUpdateRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> AssessmentResponse:
    """
    Update an assessment by creating a new version row (append-only).

    The original row is NEVER modified — a new row with the merged fields is inserted.
    If review_status=finalized:
      - recommended_level_of_care must be present (AC7)
      - Case advances to ready_for_matching (AC6)
      - AuditEvent written with event_type=assessment_finalized (AC6)
    """
    assessment = await service.update_assessment(
        session=db,
        assessment_id=assessment_id,
        organization_id=auth.organization_id,
        payload=payload,
        actor_role=auth.role_key,
        actor_user_id=auth.user_id,
    )
    return AssessmentResponse.model_validate(assessment)


# ---------------------------------------------------------------------------
# AC9 — Backward transition (clinical-specific: requires reason)
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC9
@router.post(
    "/cases/{case_id}/clinical-transition",
    response_model=ClinicalTransitionResponse,
    dependencies=[
        require_role("clinical_reviewer", "admin"),
        require_write_permission,
    ],
)
async def clinical_transition(
    case_id: UUID,
    payload: BackwardTransitionRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> ClinicalTransitionResponse:
    """
    Execute a clinical status transition.

    For the backward transition under_clinical_review→needs_clinical_review,
    transition_reason is REQUIRED (AC9).
    400 if reason absent; 200 with reason present.
    """
    updated_case = await service.backward_transition(
        session=db,
        case_id=case_id,
        organization_id=auth.organization_id,
        to_status=payload.to_status,
        actor_role=auth.role_key,
        actor_user_id=auth.user_id,
        transition_reason=payload.transition_reason,
    )
    return ClinicalTransitionResponse(
        case_id=UUID(updated_case.id),
        new_status=updated_case.current_status,
        message=f"Case transitioned to {updated_case.current_status}",
    )


# ---------------------------------------------------------------------------
# AC11 — Latest finalized assessment (matching engine read)
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC11
@router.get(
    "/cases/{case_id}/assessments/latest-finalized",
    response_model=AssessmentResponse | None,
)
async def get_latest_finalized(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> AssessmentResponse | None:
    """
    Return the latest finalized assessment for a case.

    AC11: matching-module uses this endpoint to build hard-exclusion inputs.
    Returns the assessment with the latest created_at among finalized rows.
    Returns null if no finalized assessment exists.
    """
    assessment = await service.get_latest_finalized_assessment(
        session=db,
        case_id=case_id,
        organization_id=auth.organization_id,
    )
    if assessment is None:
        return None
    return AssessmentResponse.model_validate(assessment)
