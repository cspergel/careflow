# @forgeplan-node: matching-module
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
# @forgeplan-spec: AC13
# @forgeplan-spec: AC14
# @forgeplan-spec: AC15
# @forgeplan-spec: AC16
# @forgeplan-spec: AC17
"""
Matching module service layer — DB I/O and orchestration.

Implements the four-stage pipeline:
  1. Retrieve — load all active facilities for the org
  2. Exclude — hard-exclusion gate per facility
  3. Score  — weighted component scoring for non-excluded facilities
  4. Rank   — sort by overall_score desc; excluded at bottom

Constraints enforced here:
  - Hard exclusions never receive overall_score > 0 (AC3, AC5)
  - Re-scoring inserts NEW rows; old rows are NEVER deleted (AC15)
  - selected_for_outreach=False on all new match rows (AC15)
  - Tenant isolation: every facility and match query includes organization_id (constraint)
  - Case status transitions delegated to core state machine (constraint)
  - explanation_text written at INSERT time only (AC11)
"""
# @forgeplan-decision: D-matching-3-insert-never-delete -- Re-scoring inserts new FacilityMatch rows with current generated_at; old rows retained. Why: spec constraint and AC15 require auditability of all historical match runs; DELETE would destroy audit trail

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.auth import AuthContext
from placementops.core.events import CaseActivityEvent, publish_case_activity_event
from placementops.core.models.audit_event import AuditEvent
from placementops.core.models.clinical_assessment import ClinicalAssessment
from placementops.core.models.facility import Facility
from placementops.core.models.facility_capabilities import FacilityCapabilities
from placementops.core.models.facility_insurance_rule import FacilityInsuranceRule
from placementops.core.models.facility_match import FacilityMatch
from placementops.core.models.patient_case import PatientCase
from placementops.core.state_machine import transition_case_status
from placementops.modules.facilities.models import FacilityPreference
from placementops.modules.matching.engine import (
    build_scoring_context,
    compute_component_scores,
    compute_hard_exclusions,
    rank_matches,
)

logger = logging.getLogger(__name__)

# Roles permitted to generate matches and select facilities (AC16)
_MATCH_WRITE_ROLES: frozenset[str] = frozenset(
    {"clinical_reviewer", "placement_coordinator", "admin"}
)

# Case statuses from which match generation is permitted (input validation)
_MATCHABLE_STATUSES: frozenset[str] = frozenset(
    {"ready_for_matching", "facility_options_generated"}
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


async def _resolve_assessment(
    session: AsyncSession,
    case_id: UUID,
    assessment_id: UUID | None,
    organization_id: UUID,
) -> ClinicalAssessment:
    """
    Resolve the ClinicalAssessment to use for scoring.

    When assessment_id is provided: load it and verify it belongs to case_id
    and has review_status=finalized.
    When omitted: load the latest finalized assessment for the case.
    Returns 400 if no finalized assessment exists (AC1).
    """
    # @forgeplan-spec: AC1
    if assessment_id is not None:
        result = await session.execute(
            select(ClinicalAssessment).where(
                and_(
                    ClinicalAssessment.id == str(assessment_id),
                    ClinicalAssessment.patient_case_id == str(case_id),
                )
            )
        )
        assessment = result.scalar_one_or_none()
        if assessment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Assessment {assessment_id} not found for case {case_id}",
            )
        if assessment.review_status != "finalized":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Assessment {assessment_id} has review_status='{assessment.review_status}'; "
                    "only finalized assessments may be used for match generation"
                ),
            )
        return assessment

    # Auto-resolve: latest finalized by created_at desc
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
    assessment = result.scalar_one_or_none()
    if assessment is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Case {case_id} has no finalized ClinicalAssessment. "
                "A finalized assessment is required before generating facility matches."
            ),
        )
    return assessment


async def _load_active_facilities(
    session: AsyncSession,
    organization_id: UUID,
) -> list[Facility]:
    """
    Load all active Facility records for the organization (AC2, tenant isolation constraint).

    Inactive facilities (active_status=False) are excluded entirely — they never
    appear in match results.
    """
    # @forgeplan-spec: AC2
    result = await session.execute(
        select(Facility).where(
            and_(
                Facility.organization_id == str(organization_id),
                Facility.active_status.is_(True),
            )
        )
    )
    return list(result.scalars().all())


async def _load_capabilities_map(
    session: AsyncSession,
    facility_ids: list[str],
) -> dict[str, FacilityCapabilities]:
    """Load FacilityCapabilities keyed by facility_id for efficient lookup."""
    if not facility_ids:
        return {}
    result = await session.execute(
        select(FacilityCapabilities).where(
            FacilityCapabilities.facility_id.in_(facility_ids)
        )
    )
    return {caps.facility_id: caps for caps in result.scalars().all()}


async def _load_insurance_rules_map(
    session: AsyncSession,
    facility_ids: list[str],
) -> dict[str, list[FacilityInsuranceRule]]:
    """Load FacilityInsuranceRule rows grouped by facility_id."""
    if not facility_ids:
        return {}
    result = await session.execute(
        select(FacilityInsuranceRule).where(
            FacilityInsuranceRule.facility_id.in_(facility_ids)
        )
    )
    rules_map: dict[str, list[FacilityInsuranceRule]] = {}
    for rule in result.scalars().all():
        rules_map.setdefault(rule.facility_id, []).append(rule)
    return rules_map


async def _load_facility_preferences(
    session: AsyncSession,
    organization_id: UUID,
    hospital_id: str | None,
) -> list[FacilityPreference]:
    """
    Load facility preferences for the case's hospital scope and org-global scope (AC17).

    Includes:
      - scope='global' preferences (org-wide preferred facilities)
      - scope='hospital' preferences matching the case's hospital_id (when present)

    Tenant isolation: filters by org-scoped facility_ids via subquery.
    """
    # @forgeplan-spec: AC17
    # Subquery: facility IDs belonging to this org
    org_facility_ids_subq = select(Facility.id).where(
        Facility.organization_id == str(organization_id)
    )

    # Load ALL preferences for org facilities, then filter by scope in Python.
    # This avoids needing an OR in SQLAlchemy (SQLite handles IN+filter fine).
    result = await session.execute(
        select(FacilityPreference).where(
            FacilityPreference.facility_id.in_(org_facility_ids_subq)
        )
    )
    all_prefs = list(result.scalars().all())

    # Keep global preferences always; keep hospital preferences only for this hospital
    return [
        p for p in all_prefs
        if p.scope == "global"
        or (p.scope == "hospital" and hospital_id and p.scope_reference_id == hospital_id)
    ]


# ---------------------------------------------------------------------------
# AC2 + main orchestration: generate_matches
# ---------------------------------------------------------------------------


async def generate_matches(
    session: AsyncSession,
    case_id: UUID,
    assessment_id: UUID | None,
    auth_ctx: AuthContext,
) -> list[FacilityMatch]:
    """
    Run the matching pipeline for a case and insert FacilityMatch rows.

    Pipeline:
      1. Validate case status (ready_for_matching or facility_options_generated)
      2. Resolve finalized assessment (AC1)
      3. Load active facilities + capabilities + insurance rules (AC2)
      4. Load facility preferences (AC17)
      5. For each facility: compute hard exclusions (AC3, AC4)
      6. For non-excluded: compute component scores (AC6–AC9)
      7. Rank results (AC5, AC12)
      8. INSERT new FacilityMatch rows — NEVER delete old rows (AC15)
      9. Advance case to facility_options_generated via state machine (constraint)
     10. Write AuditEvent for match_generated
     11. Return new match rows

    Re-scoring: inserts new rows with current generated_at.
    Old rows are retained with their original generated_at (AC15, constraint).
    """
    # @forgeplan-spec: AC2
    # @forgeplan-spec: AC15
    organization_id = auth_ctx.organization_id

    # Step 1: Validate case status
    case = await _get_case_scoped(session, case_id, organization_id)

    if case.current_status == "closed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Match generation is not permitted on closed cases",
        )
    if case.current_status not in _MATCHABLE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Case must be in {sorted(_MATCHABLE_STATUSES)} to generate matches; "
                f"current status is '{case.current_status}'"
            ),
        )

    # Step 2: Resolve finalized assessment (AC1)
    assessment = await _resolve_assessment(session, case_id, assessment_id, organization_id)

    # Step 3: Load active facilities (AC2, tenant isolation)
    facilities = await _load_active_facilities(session, organization_id)
    facility_ids = [f.id for f in facilities]

    # Step 4: Load capabilities and insurance rules
    caps_map = await _load_capabilities_map(session, facility_ids)
    rules_map = await _load_insurance_rules_map(session, facility_ids)

    # Step 5: Load facility preferences (AC17)
    preferences = await _load_facility_preferences(
        session, organization_id, getattr(case, "hospital_id", None)
    )

    # Build scoring context from case + assessment
    scoring_ctx = build_scoring_context(case, assessment)

    # Step 6: Classify each facility as excluded or scored
    generated_at = datetime.now(timezone.utc)

    scored_items: list = []
    excluded_items: list = []

    for facility in facilities:
        capabilities = caps_map.get(facility.id)
        if capabilities is None:
            # No capabilities row — skip this facility with a default (fail-safe)
            logger.warning(
                "Facility %s has no FacilityCapabilities row; skipping in match generation",
                facility.id,
            )
            continue

        facility_rules = rules_map.get(facility.id, [])

        # Hard exclusion gate (AC3, AC4)
        exclusion = compute_hard_exclusions(
            assessment=assessment,
            capabilities=capabilities,
            insurance_rules=facility_rules,
            primary_payer=scoring_ctx.primary_payer,
        )

        if exclusion.excluded:
            excluded_items.append((facility, exclusion))
        else:
            # Compute component scores only for non-excluded facilities (AC5)
            scores = compute_component_scores(
                context=scoring_ctx,
                facility=facility,
                capabilities=capabilities,
                insurance_rules=facility_rules,
                facility_preferences=preferences,
                assessment=assessment,
            )
            scored_items.append((facility, scores))

    # Step 7: Rank (AC5, AC12)
    ranked = rank_matches(scored_items, excluded_items)

    # Step 8: INSERT new FacilityMatch rows (NEVER delete old — AC15, constraint)
    new_matches: list[FacilityMatch] = []

    for entry in ranked:
        facility = entry["facility"]
        match = FacilityMatch(
            id=str(uuid4()),
            patient_case_id=str(case_id),
            facility_id=str(facility.id),
            assessment_id=str(assessment.id),
            overall_score=entry["overall_score"],
            payer_fit_score=entry["payer_fit_score"],
            clinical_fit_score=entry["clinical_fit_score"],
            geography_score=entry["geography_score"],
            preference_score=entry["preference_score"],
            level_of_care_fit_score=entry["level_of_care_fit_score"],
            rank_order=entry["rank_order"],
            is_recommended=entry["is_recommended"],
            selected_for_outreach=False,  # NEVER carry forward from prior run (AC15)
            blockers_json=entry["blockers_json"],
            explanation_text=entry["explanation_text"],
            generated_by="rules_engine",
            generated_at=generated_at,
        )
        session.add(match)
        new_matches.append(match)

    # Flush to assign IDs before audit event
    await session.flush()

    # Step 10: Write AuditEvent for matches_generated (both first run and re-score)
    audit = AuditEvent(
        organization_id=str(organization_id),
        entity_type="patient_case",
        entity_id=str(case_id),
        event_type="matches_generated",
        old_value_json={"case_status": case.current_status},
        new_value_json={
            "match_count": len(new_matches),
            "excluded_count": len(excluded_items),
            "assessment_id": str(assessment.id),
            "generated_at": generated_at.isoformat(),
        },
        actor_user_id=str(auth_ctx.user_id),
    )
    session.add(audit)

    # Step 9: Advance case to facility_options_generated via state machine (constraint)
    # Only transition if case is at ready_for_matching (re-scoring keeps it at facility_options_generated)
    if case.current_status == "ready_for_matching":
        await transition_case_status(
            case_id=case_id,
            to_status="facility_options_generated",
            actor_role=auth_ctx.role_key,
            actor_user_id=auth_ctx.user_id,
            session=session,
            transition_reason=f"Match generation completed: {len(new_matches)} matches created",
            organization_id=organization_id,
        )
        # transition_case_status commits all pending rows (match rows + audit event)
    else:
        # Already at facility_options_generated — commit match rows + audit event
        await session.commit()

    # Refresh all new match objects
    for match in new_matches:
        await session.refresh(match)

    logger.info(
        "Match generation complete for case %s: %d scored, %d excluded, generated_at=%s",
        case_id,
        len(scored_items),
        len(excluded_items),
        generated_at.isoformat(),
    )

    return new_matches


# ---------------------------------------------------------------------------
# AC13: get_matches
# ---------------------------------------------------------------------------


async def get_matches(
    session: AsyncSession,
    case_id: UUID,
    auth_ctx: AuthContext,
) -> list[FacilityMatch]:
    """
    Return the latest match set for a case (AC13).

    Latest match set = all FacilityMatch rows with the maximum generated_at
    for the case, ordered by rank_order ASC (blocked facilities at bottom
    with rank_order=-1).

    Tenant isolation: case must belong to auth_ctx.organization_id.
    """
    # @forgeplan-spec: AC13
    organization_id = auth_ctx.organization_id

    # Verify case exists and is org-scoped
    await _get_case_scoped(session, case_id, organization_id)

    # Find the latest generated_at for this case
    # Join through patient_case to enforce tenant isolation on match reads
    latest_ts_result = await session.execute(
        select(FacilityMatch.generated_at)
        .where(FacilityMatch.patient_case_id == str(case_id))
        .order_by(desc(FacilityMatch.generated_at))
        .limit(1)
    )
    latest_ts = latest_ts_result.scalar_one_or_none()

    if latest_ts is None:
        # No matches generated yet
        return []

    # Load all matches for the latest generated_at, ordered by rank_order
    # rank_order=-1 (excluded) sorts last when we ORDER BY rank_order ASC with
    # the caveat that -1 < 1, so we use a custom ordering:
    # positive rank_orders first (ASC), then -1 last.
    from sqlalchemy import case as sql_case

    result = await session.execute(
        select(FacilityMatch)
        .where(
            and_(
                FacilityMatch.patient_case_id == str(case_id),
                FacilityMatch.generated_at == latest_ts,
            )
        )
        .order_by(
            # Positive rank_orders (scored facilities) first, then -1 (excluded) last
            sql_case(
                (FacilityMatch.rank_order == -1, 99999),
                else_=FacilityMatch.rank_order,
            ).asc()
        )
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# AC14: toggle_select
# ---------------------------------------------------------------------------


async def toggle_select(
    session: AsyncSession,
    case_id: UUID,
    match_id: UUID,
    auth_ctx: AuthContext,
) -> FacilityMatch:
    """
    Toggle selected_for_outreach on a FacilityMatch (AC14).

    Multiple facilities may be selected simultaneously — this is a per-facility toggle.
    Writes a case_activity_event and AuditEvent for each toggle.
    Returns the updated FacilityMatch.

    Tenant isolation: match must belong to the given case_id which must
    belong to auth_ctx.organization_id.
    """
    # @forgeplan-spec: AC14
    organization_id = auth_ctx.organization_id

    # Verify case ownership
    await _get_case_scoped(session, case_id, organization_id)

    # Load the specific match
    result = await session.execute(
        select(FacilityMatch).where(
            and_(
                FacilityMatch.id == str(match_id),
                FacilityMatch.patient_case_id == str(case_id),
            )
        )
    )
    match = result.scalar_one_or_none()
    if match is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"FacilityMatch {match_id} not found for case {case_id}",
        )

    old_value = match.selected_for_outreach
    new_value = not old_value

    match.selected_for_outreach = new_value

    event_type = "facility_selected" if new_value else "facility_deselected"

    # Write AuditEvent
    audit = AuditEvent(
        organization_id=str(organization_id),
        entity_type="facility_match",
        entity_id=str(match_id),
        event_type=event_type,
        old_value_json={"selected_for_outreach": old_value, "facility_id": match.facility_id},
        new_value_json={"selected_for_outreach": new_value, "facility_id": match.facility_id},
        actor_user_id=str(auth_ctx.user_id),
    )
    session.add(audit)

    await session.commit()
    await session.refresh(match)

    # Publish case_activity_event for outreach-module consumption
    activity_event = CaseActivityEvent(
        case_id=case_id,
        actor_user_id=auth_ctx.user_id,
        event_type=event_type,
        old_status=None,
        new_status=event_type,
        occurred_at=datetime.now(timezone.utc),
        organization_id=organization_id,
        metadata={
            "match_id": str(match_id),
            "facility_id": match.facility_id,
            "selected_for_outreach": new_value,
        },
    )
    await publish_case_activity_event(activity_event)

    logger.info(
        "Facility match %s %s by %s for case %s",
        match_id,
        event_type,
        auth_ctx.user_id,
        case_id,
    )

    return match
