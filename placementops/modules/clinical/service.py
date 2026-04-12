# @forgeplan-node: clinical-module
"""
Clinical module service layer.

Business rules implemented here:
  - Reviewer assignment advances case from needs_clinical_review → under_clinical_review
  - PATCH creates a NEW ClinicalAssessment row (append-only — never updates in place)
  - Finalization validates recommended_level_of_care, advances case to ready_for_matching
  - Backward transition requires non-empty transition_reason
  - All reads and writes are scoped to organization_id (tenant isolation)
  - Only clinical_reviewer or admin may create or finalize assessments
  - Closed cases return 409 on all assessment write operations
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

import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.models.clinical_assessment import ClinicalAssessment
from placementops.core.models.patient_case import PatientCase
from placementops.core.models.user import User
from placementops.core.state_machine import transition_case_status
from placementops.modules.clinical.schemas import (
    AssessmentCreateRequest,
    AssessmentUpdateRequest,
)

logger = logging.getLogger(__name__)

# Roles permitted to create and finalize assessments (AC10)
_ASSESSMENT_WRITE_ROLES: frozenset[str] = frozenset({"clinical_reviewer", "admin"})

# Statuses where clinical-module may operate (AC1, AC12)
_REVIEWABLE_STATUSES: frozenset[str] = frozenset(
    {"needs_clinical_review", "under_clinical_review"}
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _get_case_scoped(
    session: AsyncSession,
    case_id: UUID,
    organization_id: UUID,
) -> PatientCase:
    """Load PatientCase scoped to org; 404 if not found."""
    result = await session.execute(
        select(PatientCase).where(
            and_(
                PatientCase.id == str(case_id),
                PatientCase.organization_id == str(organization_id),
            )
        )
    )
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case {case_id} not found",
        )
    return case


def _assert_not_closed(case: PatientCase) -> None:
    """Raise 409 if the case is closed (AC12)."""
    # @forgeplan-spec: AC12
    if case.current_status == "closed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Assessment write operations are not permitted on closed cases",
        )


def _assert_write_role(role_key: str) -> None:
    """Raise 403 if the role is not permitted to write assessments (AC10)."""
    # @forgeplan-spec: AC10
    if role_key not in _ASSESSMENT_WRITE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{role_key}' is not permitted to create or finalize assessments",
        )


# ---------------------------------------------------------------------------
# AC1 — Clinical reviewer queue
# ---------------------------------------------------------------------------


async def list_clinical_queue(
    session: AsyncSession,
    organization_id: UUID,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[PatientCase], int]:
    """
    Return paginated cases at needs_clinical_review scoped to organization.

    AC1: only org-scoped cases returned.
    """
    # @forgeplan-spec: AC1
    base_filter = and_(
        PatientCase.organization_id == str(organization_id),
        PatientCase.current_status == "needs_clinical_review",
    )
    count_result = await session.execute(
        select(func.count()).select_from(PatientCase).where(base_filter)
    )
    total = count_result.scalar_one()

    offset = (page - 1) * page_size
    cases_result = await session.execute(
        select(PatientCase)
        .where(base_filter)
        .order_by(PatientCase.created_at.asc())
        .offset(offset)
        .limit(page_size)
    )
    return list(cases_result.scalars().all()), total


# ---------------------------------------------------------------------------
# AC2 — Assign clinical reviewer
# ---------------------------------------------------------------------------


async def assign_clinical_reviewer(
    session: AsyncSession,
    case_id: UUID,
    organization_id: UUID,
    reviewer_user_id: UUID,
    actor_role: str,
    actor_user_id: UUID,
) -> PatientCase:
    """
    Assign a clinical reviewer to a case and advance status to under_clinical_review.

    Validates:
      - Case exists and is org-scoped
      - Assigned user exists and has role clinical_reviewer or admin
      - Case is at needs_clinical_review (state machine enforces this too)
    """
    # @forgeplan-spec: AC2
    case = await _get_case_scoped(session, case_id, organization_id)
    _assert_not_closed(case)

    # Validate reviewer user exists
    user_result = await session.execute(
        select(User).where(User.id == str(reviewer_user_id))
    )
    reviewer = user_result.scalar_one_or_none()
    if reviewer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {reviewer_user_id} not found",
        )
    if reviewer.role_key not in ("clinical_reviewer", "admin"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Assigned user must have role clinical_reviewer or admin",
        )

    # Advance case status via state machine (writes CaseStatusHistory + AuditEvent)
    updated_case = await transition_case_status(
        case_id=case_id,
        to_status="under_clinical_review",
        actor_role=actor_role,
        actor_user_id=actor_user_id,
        session=session,
        transition_reason=f"Reviewer {reviewer_user_id} assigned",
        organization_id=organization_id,
    )

    logger.info(
        "Clinical reviewer %s assigned to case %s by %s",
        reviewer_user_id,
        case_id,
        actor_user_id,
    )
    return updated_case


# ---------------------------------------------------------------------------
# AC3 — Create draft assessment
# ---------------------------------------------------------------------------


async def create_assessment(
    session: AsyncSession,
    case_id: UUID,
    organization_id: UUID,
    payload: AssessmentCreateRequest,
    reviewer_user_id: UUID,
    actor_role: str,
) -> ClinicalAssessment:
    """
    Create a ClinicalAssessment draft for a case.

    Constraints:
      - Case must be in needs_clinical_review or under_clinical_review
      - Only clinical_reviewer or admin may create (AC10)
      - Closed cases return 409 (AC12)
      - No PatientCase status change at draft creation (AC3)
    """
    # @forgeplan-spec: AC3
    # @forgeplan-spec: AC10
    _assert_write_role(actor_role)

    case = await _get_case_scoped(session, case_id, organization_id)
    _assert_not_closed(case)

    if case.current_status not in _REVIEWABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Case must be in {sorted(_REVIEWABLE_STATUSES)} to create an assessment; "
                f"current status is '{case.current_status}'"
            ),
        )

    assessment = ClinicalAssessment(
        id=str(uuid4()),
        patient_case_id=str(case_id),
        reviewer_user_id=str(reviewer_user_id),
        review_status="draft",
        recommended_level_of_care=payload.recommended_level_of_care or "",
        confidence_level=payload.confidence_level,
        clinical_summary=payload.clinical_summary,
        rehab_tolerance=payload.rehab_tolerance,
        mobility_status=payload.mobility_status,
        psych_behavior_flags=payload.psych_behavior_flags,
        special_equipment_needs=payload.special_equipment_needs,
        barriers_to_placement=payload.barriers_to_placement,
        payer_notes=payload.payer_notes,
        family_preference_notes=payload.family_preference_notes,
        # Clinical capability flags
        accepts_trach=payload.accepts_trach,
        accepts_vent=payload.accepts_vent,
        accepts_hd=payload.accepts_hd,
        in_house_hemodialysis=payload.in_house_hemodialysis,
        accepts_peritoneal_dialysis=payload.accepts_peritoneal_dialysis,
        accepts_wound_vac=payload.accepts_wound_vac,
        accepts_iv_antibiotics=payload.accepts_iv_antibiotics,
        accepts_tpn=payload.accepts_tpn,
        accepts_isolation_cases=payload.accepts_isolation_cases,
        accepts_behavioral_complexity=payload.accepts_behavioral_complexity,
        accepts_bariatric=payload.accepts_bariatric,
        accepts_memory_care=payload.accepts_memory_care,
        accepts_oxygen_therapy=payload.accepts_oxygen_therapy,
    )
    session.add(assessment)
    await session.commit()
    await session.refresh(assessment)

    logger.info("Assessment draft %s created for case %s", assessment.id, case_id)
    return assessment


# ---------------------------------------------------------------------------
# AC4 — Update assessment (append-only versioning)
# ---------------------------------------------------------------------------


async def update_assessment(
    session: AsyncSession,
    assessment_id: UUID,
    organization_id: UUID,
    payload: AssessmentUpdateRequest,
    actor_role: str,
    actor_user_id: UUID,
) -> ClinicalAssessment:
    """
    Create a new ClinicalAssessment version row based on existing assessment.

    CRITICAL: This NEVER modifies the existing row.  A new row is inserted with
    the merged field values.  The previous row remains unchanged in the DB (AC4).

    If review_status=finalized:
      - Validates recommended_level_of_care is non-empty (AC7)
      - Advances case to ready_for_matching (AC6)
      - Writes AuditEvent with event_type=assessment_finalized (AC6)
    """
    # @forgeplan-spec: AC4
    # @forgeplan-spec: AC6
    # @forgeplan-spec: AC7
    _assert_write_role(actor_role)

    # Load the existing assessment
    result = await session.execute(
        select(ClinicalAssessment).where(
            ClinicalAssessment.id == str(assessment_id)
        )
    )
    existing = result.scalar_one_or_none()
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment {assessment_id} not found",
        )

    # Verify tenant isolation — load case and check org (AC constraint)
    # @forgeplan-spec: AC12
    case_result = await session.execute(
        select(PatientCase).where(
            and_(
                PatientCase.id == existing.patient_case_id,
                PatientCase.organization_id == str(organization_id),
            )
        )
    )
    case = case_result.scalar_one_or_none()
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assessment {assessment_id} not found",
        )
    _assert_not_closed(case)

    # Determine the new review_status
    new_review_status = payload.review_status or existing.review_status

    # Determine recommended_level_of_care for the new row
    new_loc = (
        payload.recommended_level_of_care
        if payload.recommended_level_of_care is not None
        else existing.recommended_level_of_care
    )

    # AC7: finalization requires recommended_level_of_care
    if new_review_status == "finalized" and not new_loc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "missing_required_field",
                "field": "recommended_level_of_care",
                "message": "recommended_level_of_care is required when finalizing an assessment",
            },
        )

    # Build the new version row — merge existing fields with payload overrides
    def _pick(new_val, old_val):
        return new_val if new_val is not None else old_val

    new_assessment = ClinicalAssessment(
        id=str(uuid4()),
        patient_case_id=existing.patient_case_id,
        reviewer_user_id=str(actor_user_id),
        created_at=datetime.now(timezone.utc),  # Python microsecond precision; overrides server_default to ensure ordering
        review_status=new_review_status,
        recommended_level_of_care=new_loc,
        confidence_level=_pick(payload.confidence_level, existing.confidence_level),
        clinical_summary=_pick(payload.clinical_summary, existing.clinical_summary),
        rehab_tolerance=_pick(payload.rehab_tolerance, existing.rehab_tolerance),
        mobility_status=_pick(payload.mobility_status, existing.mobility_status),
        psych_behavior_flags=_pick(payload.psych_behavior_flags, existing.psych_behavior_flags),
        special_equipment_needs=_pick(payload.special_equipment_needs, existing.special_equipment_needs),
        barriers_to_placement=_pick(payload.barriers_to_placement, existing.barriers_to_placement),
        payer_notes=_pick(payload.payer_notes, existing.payer_notes),
        family_preference_notes=_pick(payload.family_preference_notes, existing.family_preference_notes),
        # Clinical capability flags
        accepts_trach=_pick(payload.accepts_trach, existing.accepts_trach),
        accepts_vent=_pick(payload.accepts_vent, existing.accepts_vent),
        accepts_hd=_pick(payload.accepts_hd, existing.accepts_hd),
        in_house_hemodialysis=_pick(payload.in_house_hemodialysis, existing.in_house_hemodialysis),
        accepts_peritoneal_dialysis=_pick(payload.accepts_peritoneal_dialysis, existing.accepts_peritoneal_dialysis),
        accepts_wound_vac=_pick(payload.accepts_wound_vac, existing.accepts_wound_vac),
        accepts_iv_antibiotics=_pick(payload.accepts_iv_antibiotics, existing.accepts_iv_antibiotics),
        accepts_tpn=_pick(payload.accepts_tpn, existing.accepts_tpn),
        accepts_isolation_cases=_pick(payload.accepts_isolation_cases, existing.accepts_isolation_cases),
        accepts_behavioral_complexity=_pick(payload.accepts_behavioral_complexity, existing.accepts_behavioral_complexity),
        accepts_bariatric=_pick(payload.accepts_bariatric, existing.accepts_bariatric),
        accepts_memory_care=_pick(payload.accepts_memory_care, existing.accepts_memory_care),
        accepts_oxygen_therapy=_pick(payload.accepts_oxygen_therapy, existing.accepts_oxygen_therapy),
    )
    session.add(new_assessment)

    # AC6: finalization advances case status and writes AuditEvent
    if new_review_status == "finalized" and existing.review_status != "finalized":
        # @forgeplan-spec: AC6
        # Flush to get new_assessment.id before the state_machine commit
        await session.flush()

        from placementops.core.models.audit_event import AuditEvent
        audit = AuditEvent(
            organization_id=case.organization_id,
            entity_type="clinical_assessment",
            entity_id=new_assessment.id,
            event_type="assessment_finalized",
            old_value_json={"assessment_id": str(assessment_id), "review_status": "draft"},
            new_value_json={"assessment_id": new_assessment.id, "review_status": "finalized"},
            actor_user_id=str(actor_user_id),
        )
        session.add(audit)

        # Advance case status to ready_for_matching via state machine
        await transition_case_status(
            case_id=UUID(case.id),
            to_status="ready_for_matching",
            actor_role=actor_role,
            actor_user_id=actor_user_id,
            session=session,
            transition_reason=f"Assessment {new_assessment.id} finalized",
            organization_id=UUID(case.organization_id),
        )
        # transition_case_status commits; refresh new_assessment afterward
    else:
        await session.commit()

    await session.refresh(new_assessment)
    logger.info(
        "Assessment version created: new=%s (prev=%s) case=%s status=%s",
        new_assessment.id,
        assessment_id,
        case.id,
        new_review_status,
    )
    return new_assessment


# ---------------------------------------------------------------------------
# AC5 — List assessment versions
# ---------------------------------------------------------------------------


async def list_assessments(
    session: AsyncSession,
    case_id: UUID,
    organization_id: UUID,
) -> list[ClinicalAssessment]:
    """
    Return all assessment versions for a case ordered by created_at ascending.

    AC5: all versions returned; ordering chronological.
    Tenant isolation: case must belong to organization_id.
    """
    # @forgeplan-spec: AC5
    # Verify case exists and is org-scoped
    await _get_case_scoped(session, case_id, organization_id)

    result = await session.execute(
        select(ClinicalAssessment)
        .where(ClinicalAssessment.patient_case_id == str(case_id))
        .order_by(ClinicalAssessment.created_at.asc())
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# AC9 — Backward transition with required reason
# ---------------------------------------------------------------------------


async def backward_transition(
    session: AsyncSession,
    case_id: UUID,
    organization_id: UUID,
    to_status: str,
    actor_role: str,
    actor_user_id: UUID,
    transition_reason: str | None,
) -> PatientCase:
    """
    Execute a backward transition under_clinical_review→needs_clinical_review.

    transition_reason is REQUIRED for this transition (AC9).
    Delegates to core state_machine for allowlist + role enforcement.
    """
    # @forgeplan-spec: AC9
    case = await _get_case_scoped(session, case_id, organization_id)

    if to_status == "needs_clinical_review" and not transition_reason:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "transition_reason_required",
                "message": (
                    "transition_reason is required when transitioning back to "
                    "needs_clinical_review"
                ),
            },
        )

    if len(transition_reason or "") > 1000:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="transition_reason must be at most 1000 characters",
        )

    updated_case = await transition_case_status(
        case_id=case_id,
        to_status=to_status,
        actor_role=actor_role,
        actor_user_id=actor_user_id,
        session=session,
        transition_reason=transition_reason,
        organization_id=organization_id,
    )
    return updated_case


# ---------------------------------------------------------------------------
# AC11 — Latest finalized assessment (for matching engine)
# ---------------------------------------------------------------------------


async def get_latest_finalized_assessment(
    session: AsyncSession,
    case_id: UUID,
    organization_id: UUID,
) -> ClinicalAssessment | None:
    """
    Return the most recently created finalized assessment for a case.

    AC11: latest is determined by created_at desc (the column that is set at
    insert time; updated_at is excluded to avoid tie-breaking ambiguity per
    the failure_modes in the spec).
    """
    # @forgeplan-spec: AC11
    await _get_case_scoped(session, case_id, organization_id)

    result = await session.execute(
        select(ClinicalAssessment)
        .where(
            and_(
                ClinicalAssessment.patient_case_id == str(case_id),
                ClinicalAssessment.review_status == "finalized",
            )
        )
        .order_by(desc(ClinicalAssessment.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()
