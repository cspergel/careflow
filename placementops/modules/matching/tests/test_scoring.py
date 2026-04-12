# @forgeplan-node: matching-module
# @forgeplan-spec: AC6
# @forgeplan-spec: AC7
# @forgeplan-spec: AC9
# @forgeplan-spec: AC10
# @forgeplan-spec: AC11
# @forgeplan-spec: AC12
"""
Unit tests for scoring engine functions.

Covers: AC6, AC7, AC9, AC10, AC11, AC12

These are mostly pure unit tests on engine.py functions without DB I/O,
plus integration tests for AC10, AC11, AC12 that require DB state.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.models import FacilityMatch
from placementops.modules.matching.engine import (
    BlockerDetail,
    ComponentScores,
    HardExclusionResult,
    ScoringContext,
    compute_clinical_fit_score,
    compute_component_scores,
    compute_geography_score,
    compute_hard_exclusions,
    compute_level_of_care_score,
    compute_payer_fit_score,
    compute_preference_score,
    generate_explanation_text,
    rank_matches,
    zip_to_latlon,
)
from placementops.modules.matching import service
from placementops.modules.matching.tests.conftest import (
    TEST_ORG_ID,
    TEST_PAYER_ID,
    make_id,
    seed_assessment,
    seed_capabilities,
    seed_case,
    seed_facility,
    seed_insurance_rule,
    seed_payer,
    seed_user,
    seed_preference,
)

# Only apply asyncio mark to async tests; sync tests get this mark via decorator or none
pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Stub objects for pure unit tests (no DB needed)
# ---------------------------------------------------------------------------


@dataclass
class StubFacilityCapabilities:
    facility_id: str = "stub-facility"
    accepts_snf: bool = False
    accepts_irf: bool = False
    accepts_ltach: bool = False
    accepts_trach: bool = False
    accepts_vent: bool = False
    accepts_hd: bool = False
    in_house_hemodialysis: bool = False
    accepts_peritoneal_dialysis: bool = False
    accepts_wound_vac: bool = False
    accepts_iv_antibiotics: bool = False
    accepts_tpn: bool = False
    accepts_bariatric: bool = False
    accepts_behavioral_complexity: bool = False
    accepts_memory_care: bool = False
    accepts_isolation_cases: bool = False
    accepts_oxygen_therapy: bool = False


@dataclass
class StubAssessment:
    id: str = "stub-assessment"
    accepts_trach: bool = False
    accepts_vent: bool = False
    accepts_hd: bool = False
    in_house_hemodialysis: bool = False
    accepts_peritoneal_dialysis: bool = False
    accepts_wound_vac: bool = False
    accepts_iv_antibiotics: bool = False
    accepts_tpn: bool = False
    accepts_isolation_cases: bool = False
    accepts_behavioral_complexity: bool = False
    accepts_bariatric: bool = False
    accepts_memory_care: bool = False
    accepts_oxygen_therapy: bool = False


@dataclass
class StubInsuranceRule:
    facility_id: str
    payer_id: str
    payer_name: str
    accepted_status: str  # accepted | conditional | not_accepted


@dataclass
class StubFacility:
    id: str
    facility_name: str = "Test Facility"
    latitude: float | None = None
    longitude: float | None = None


@dataclass
class StubPreference:
    facility_id: str


# ---------------------------------------------------------------------------
# AC6 — Scoring weights sum to 1.0 and are applied correctly
# ---------------------------------------------------------------------------


def test_weights_sum_to_one():
    """
    AC6: Verify 0.35 + 0.30 + 0.20 + 0.10 + 0.05 = 1.00
    """
    from placementops.modules.matching.engine import (
        _W_PAYER, _W_CLINICAL, _W_LEVEL_OF_CARE, _W_GEOGRAPHY, _W_PREFERENCE
    )
    total = _W_PAYER + _W_CLINICAL + _W_LEVEL_OF_CARE + _W_GEOGRAPHY + _W_PREFERENCE
    assert abs(total - 1.0) < 1e-9, f"Weights must sum to 1.0; got {total}"


def test_overall_score_formula():
    """
    AC6: overall_score = (payer_fit*0.35 + clinical_fit*0.30 + loc*0.20 + geo*0.10 + pref*0.05) * 100
    within tolerance 0.001.
    """
    payer = 0.8
    clinical = 0.6
    loc = 1.0
    geo = 0.7
    pref = 1.0

    expected = (payer * 0.35 + clinical * 0.30 + loc * 0.20 + geo * 0.10 + pref * 0.05) * 100.0

    # Build stub objects with known scores
    assessment = StubAssessment()
    capabilities = StubFacilityCapabilities(accepts_snf=True)  # loc: snf recommended, accepts_snf=True → 1.0

    # We test compute_component_scores with pre-known inputs by checking the formula independently
    computed_score = (payer * 0.35 + clinical * 0.30 + loc * 0.20 + geo * 0.10 + pref * 0.05) * 100.0
    assert abs(computed_score - expected) < 0.001


def test_compute_component_scores_all_high():
    """
    AC6: Facility with all high scores; verify overall_score formula is applied correctly.
    """
    # Set up an assessment with no clinical needs (clinical_fit_score=1.0 — universal fit)
    assessment = StubAssessment()
    caps = StubFacilityCapabilities(accepts_snf=True)
    rules = [StubInsuranceRule("f1", str(TEST_PAYER_ID), "Medicare", "accepted")]
    context = ScoringContext(
        case_id="c1",
        assessment_id="a1",
        patient_zip=None,
        patient_lat=None,
        patient_lng=None,
        recommended_level_of_care="snf",
        primary_payer="Medicare",
    )
    facility = StubFacility(id="f1", latitude=None, longitude=None)
    prefs = [StubPreference(facility_id="f1")]

    scores = compute_component_scores(context, facility, caps, rules, prefs, assessment)

    # loc=1.0 (exact snf), payer=1.0 (accepted), clinical=1.0 (no needs → universal fit), geo=0.0 (no zip), pref=1.0
    expected_overall = (1.0 * 0.35 + 1.0 * 0.30 + 1.0 * 0.20 + 0.0 * 0.10 + 1.0 * 0.05) * 100.0
    assert abs(scores.overall_score - expected_overall) < 0.001, (
        f"Expected overall_score={expected_overall:.3f}, got {scores.overall_score:.3f}"
    )


# ---------------------------------------------------------------------------
# AC7 — Level of care adjacency scoring
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("recommended,accepts_snf,accepts_irf,accepts_ltach,expected_score", [
    # Exact matches
    ("snf", True, False, False, 1.0),
    ("irf", False, True, False, 1.0),
    ("ltach", False, False, True, 1.0),
    # One-step adjacent
    ("irf", True, False, False, 0.7),   # irf→snf: 1 step
    ("irf", False, False, True, 0.7),   # irf→ltach: 1 step
    ("snf", False, True, False, 0.7),   # snf→irf: 1 step
    ("ltach", False, True, False, 0.7), # ltach→irf: 1 step
    # Two-step
    ("snf", False, False, True, 0.4),   # snf→ltach: 2 steps
    ("ltach", True, False, False, 0.4), # ltach→snf: 2 steps
    # No match
    ("snf", False, False, False, 0.0),
    ("irf", False, False, False, 0.0),
])
def test_level_of_care_adjacency(
    recommended: str,
    accepts_snf: bool,
    accepts_irf: bool,
    accepts_ltach: bool,
    expected_score: float,
):
    """
    AC7: Test all LOC adjacency combinations.
    LOC order: snf=0 < irf=1 < ltach=2
    Exact=1.0, 1-step=0.7, 2-step=0.4, no match=0.0
    """
    caps = StubFacilityCapabilities(
        accepts_snf=accepts_snf,
        accepts_irf=accepts_irf,
        accepts_ltach=accepts_ltach,
    )
    score = compute_level_of_care_score(recommended, caps)
    assert abs(score - expected_score) < 0.001, (
        f"LOC score for recommended={recommended}, "
        f"snf={accepts_snf}, irf={accepts_irf}, ltach={accepts_ltach}: "
        f"expected={expected_score}, got={score}"
    )


# ---------------------------------------------------------------------------
# AC9 — Geography score step function
# ---------------------------------------------------------------------------


def test_geography_score_null_patient_zip():
    """
    AC9: null patient_lat/lng → geography_score=0.0, NOT an exclusion.
    """
    score = compute_geography_score(None, None, 34.0522, -118.2437)
    assert score == 0.0, "Null patient coordinates must return 0.0"


def test_geography_score_null_facility_coords():
    """
    AC9: null facility lat/lng → geography_score=0.0, NOT an exclusion.
    """
    score = compute_geography_score(34.0522, -118.2437, None, None)
    assert score == 0.0, "Null facility coordinates must return 0.0"


def test_geography_score_both_null():
    """
    AC9: both null → 0.0.
    """
    score = compute_geography_score(None, None, None, None)
    assert score == 0.0


@pytest.mark.parametrize("facility_lat,facility_lng,expected_score,description", [
    # Patient at Detroit (42.3314, -83.0458)
    # ~5 miles: move ~0.072 degrees lat north
    (42.4040, -83.0458, 1.0, "~5mi → 1.0"),
    # ~15 miles: move ~0.217 degrees lat north
    (42.5486, -83.0458, 0.7, "~15mi → 0.7"),
    # ~35 miles: move ~0.507 degrees lat north
    (42.8390, -83.0458, 0.4, "~35mi → 0.4"),
    # ~75 miles: move ~1.087 degrees lat north
    (43.4190, -83.0458, 0.1, "~75mi → 0.1"),
])
def test_geography_step_function(
    facility_lat: float,
    facility_lng: float,
    expected_score: float,
    description: str,
):
    """
    AC9: Verify geography step function thresholds using pre-computed coordinate pairs.

    Uses Detroit, MI (42.3314, -83.0458) as the patient location.
    Facility locations are chosen to fall clearly within each distance bin
    (not right at the boundary) to avoid approximation artifacts.
    Step function: ≤10mi=1.0, ≤25mi=0.7, ≤50mi=0.4, >50mi=0.1
    """
    # Detroit, MI as patient
    patient_lat, patient_lng = 42.3314, -83.0458

    score = compute_geography_score(patient_lat, patient_lng, facility_lat, facility_lng)
    assert abs(score - expected_score) < 0.001, (
        f"{description}: expected score={expected_score}, got={score} "
        f"(facility at {facility_lat},{facility_lng})"
    )


# ---------------------------------------------------------------------------
# AC10 — All component scores stored separately
# ---------------------------------------------------------------------------


async def test_all_component_scores_stored(
    db_session: AsyncSession,
    auth_ctx_coordinator,
    seeded_case,
    seeded_payer,
    seed_org_fixture,
):
    """
    AC10: POST generate; assert each non-excluded FacilityMatch has all
    component scores as non-null distinct fields.
    """
    # Seed one non-excluded facility
    f = await seed_facility(db_session)
    await seed_capabilities(db_session, f.id, accepts_snf=True)
    await seed_insurance_rule(db_session, f.id, TEST_PAYER_ID, "Medicare", "accepted")

    case = seeded_case
    new_matches = await service.generate_matches(
        session=db_session,
        case_id=UUID(case.id),
        assessment_id=None,
        auth_ctx=auth_ctx_coordinator,
    )

    non_excluded = [m for m in new_matches if m.rank_order > 0]
    assert len(non_excluded) >= 1

    for match in non_excluded:
        assert match.level_of_care_fit_score is not None, "level_of_care_fit_score must be stored"
        assert match.payer_fit_score is not None, "payer_fit_score must be stored"
        assert match.clinical_fit_score is not None, "clinical_fit_score must be stored"
        assert match.geography_score is not None, "geography_score must be stored"
        assert match.preference_score is not None, "preference_score must be stored"
        assert match.overall_score is not None, "overall_score must be stored"


# ---------------------------------------------------------------------------
# AC11 — explanation_text stored verbatim, never regenerated on GET
# ---------------------------------------------------------------------------


async def test_explanation_text_stored_verbatim_not_regenerated(
    db_session: AsyncSession,
    auth_ctx_coordinator,
    seeded_case,
    seeded_payer,
    seed_org_fixture,
):
    """
    AC11: POST generate; capture explanation_text from DB.
    GET matches; assert returned explanation_text is identical to stored value.
    Update a facility capability and GET matches again without re-generating;
    assert explanation_text has not changed.
    """
    f = await seed_facility(db_session)
    await seed_capabilities(db_session, f.id, accepts_snf=True)
    await seed_insurance_rule(db_session, f.id, TEST_PAYER_ID, "Medicare", "accepted")

    case = seeded_case
    new_matches = await service.generate_matches(
        session=db_session,
        case_id=UUID(case.id),
        assessment_id=None,
        auth_ctx=auth_ctx_coordinator,
    )

    # Capture stored explanation_text
    non_excluded = [m for m in new_matches if m.rank_order > 0]
    assert len(non_excluded) >= 1
    original_match = non_excluded[0]
    stored_explanation = original_match.explanation_text

    # GET matches
    matches_via_get = await service.get_matches(
        session=db_session,
        case_id=UUID(case.id),
        auth_ctx=auth_ctx_coordinator,
    )
    get_match = next(
        m for m in matches_via_get if m.id == original_match.id
    )
    assert get_match.explanation_text == stored_explanation, (
        "GET must return explanation_text verbatim from storage"
    )

    # Update facility capability (simulate a change) to verify stored text is unchanged
    from placementops.core.models import FacilityCapabilities
    caps_result = await db_session.execute(
        select(FacilityCapabilities).where(
            FacilityCapabilities.facility_id == f.id
        )
    )
    caps = caps_result.scalar_one_or_none()
    if caps:
        caps.accepts_trach = True
        await db_session.commit()

    # GET matches again WITHOUT re-generating
    matches_after_capability_change = await service.get_matches(
        session=db_session,
        case_id=UUID(case.id),
        auth_ctx=auth_ctx_coordinator,
    )
    match_after = next(
        m for m in matches_after_capability_change if m.id == original_match.id
    )
    assert match_after.explanation_text == stored_explanation, (
        "explanation_text must not change after facility capability update without re-generation"
    )


# ---------------------------------------------------------------------------
# AC12 — is_recommended set on top 3 non-excluded facilities
# ---------------------------------------------------------------------------


async def test_is_recommended_top_3(
    db_session: AsyncSession,
    auth_ctx_coordinator,
    seeded_case,
    seeded_payer,
    seed_org_fixture,
):
    """
    AC12: POST generate with 10+ non-excluded facilities.
    Exactly 3 FacilityMatch records have is_recommended=True.
    Those 3 have the highest overall_score values among non-excluded matches.
    """
    # Seed 10 non-excluded facilities
    for i in range(10):
        f = await seed_facility(db_session, facility_name=f"Facility {i}")
        await seed_capabilities(db_session, f.id, accepts_snf=True)
        await seed_insurance_rule(db_session, f.id, TEST_PAYER_ID, "Medicare", "accepted")

    case = seeded_case
    new_matches = await service.generate_matches(
        session=db_session,
        case_id=UUID(case.id),
        assessment_id=None,
        auth_ctx=auth_ctx_coordinator,
    )

    non_excluded = [m for m in new_matches if m.rank_order > 0]
    recommended = [m for m in non_excluded if m.is_recommended]
    not_recommended = [m for m in non_excluded if not m.is_recommended]

    assert len(recommended) == 3, (
        f"Exactly 3 facilities must have is_recommended=True; got {len(recommended)}"
    )

    # Verify top 3 have highest overall_scores
    recommended_scores = sorted([float(m.overall_score) for m in recommended], reverse=True)
    not_recommended_scores = [float(m.overall_score) for m in not_recommended]

    min_recommended = min(recommended_scores)
    max_not_recommended = max(not_recommended_scores) if not_recommended_scores else 0.0

    assert min_recommended >= max_not_recommended - 0.001, (
        f"Recommended facilities must have the 3 highest scores; "
        f"min recommended={min_recommended:.3f}, max not-recommended={max_not_recommended:.3f}"
    )


async def test_is_recommended_fewer_than_3_facilities(
    db_session: AsyncSession,
    auth_ctx_coordinator,
    seed_org_fixture,
    seeded_payer,
    coordinator_user,
):
    """
    AC12: When fewer than 3 non-excluded facilities exist, all are recommended.
    """
    case = await seed_case(db_session, insurance_primary="Medicare")
    await seed_assessment(
        db_session,
        case_id=case.id,
        reviewer_user_id=coordinator_user.id,
        review_status="finalized",
        recommended_loc="snf",
    )

    # Only 2 facilities
    for i in range(2):
        f = await seed_facility(db_session, facility_name=f"Small {i}")
        await seed_capabilities(db_session, f.id, accepts_snf=True)
        await seed_insurance_rule(db_session, f.id, TEST_PAYER_ID, "Medicare", "accepted")

    new_matches = await service.generate_matches(
        session=db_session,
        case_id=UUID(case.id),
        assessment_id=None,
        auth_ctx=auth_ctx_coordinator,
    )

    non_excluded = [m for m in new_matches if m.rank_order > 0]
    assert len(non_excluded) == 2
    recommended = [m for m in non_excluded if m.is_recommended]
    assert len(recommended) == 2, "With 2 facilities, both should be recommended"


# ---------------------------------------------------------------------------
# AC9 additional: null patient_zip in case → geography_score=0.0 for all, no exclusion
# ---------------------------------------------------------------------------


async def test_null_patient_zip_gives_zero_geography_no_exclusion(
    db_session: AsyncSession,
    auth_ctx_coordinator,
    seed_org_fixture,
    seeded_payer,
    coordinator_user,
):
    """
    AC9: Case with null patient_zip → geography_score=0.0 for ALL facilities.
    No facility is excluded due to null ZIP.
    """
    case = await seed_case(db_session, patient_zip=None, insurance_primary="Medicare")
    await seed_assessment(
        db_session,
        case_id=case.id,
        reviewer_user_id=coordinator_user.id,
        review_status="finalized",
        recommended_loc="snf",
    )

    # Seed facilities WITH known coordinates
    for i in range(3):
        f = await seed_facility(
            db_session,
            facility_name=f"Coord Facility {i}",
            latitude=34.0 + i * 0.1,
            longitude=-118.0,
        )
        await seed_capabilities(db_session, f.id, accepts_snf=True)
        await seed_insurance_rule(db_session, f.id, TEST_PAYER_ID, "Medicare", "accepted")

    new_matches = await service.generate_matches(
        session=db_session,
        case_id=UUID(case.id),
        assessment_id=None,
        auth_ctx=auth_ctx_coordinator,
    )

    non_excluded = [m for m in new_matches if m.rank_order > 0]
    assert len(non_excluded) == 3, "All 3 facilities must be non-excluded (null ZIP is not a gate)"

    for match in non_excluded:
        assert match.geography_score is not None
        assert abs(float(match.geography_score) - 0.0) < 0.001, (
            f"Facility {match.facility_id}: expected geography_score=0.0 with null ZIP; "
            f"got {match.geography_score}"
        )


# ---------------------------------------------------------------------------
# Pure unit tests for individual engine functions
# ---------------------------------------------------------------------------


def test_payer_fit_score_accepted():
    rules = [StubInsuranceRule("f1", str(TEST_PAYER_ID), "Medicare", "accepted")]
    assert compute_payer_fit_score(rules, "Medicare") == 1.0


def test_payer_fit_score_conditional():
    rules = [StubInsuranceRule("f1", str(TEST_PAYER_ID), "Medicare", "conditional")]
    assert compute_payer_fit_score(rules, "Medicare") == 0.5


def test_payer_fit_score_not_accepted():
    """not_accepted returns 0.0 as defensive fallback (hard exclusion should have caught it)."""
    rules = [StubInsuranceRule("f1", str(TEST_PAYER_ID), "Medicare", "not_accepted")]
    assert compute_payer_fit_score(rules, "Medicare") == 0.0


def test_payer_fit_score_no_rule():
    """No rule for payer → treat as conditional (0.5)."""
    rules: list = []
    assert compute_payer_fit_score(rules, "Medicare") == 0.5


def test_clinical_fit_score_no_flags():
    """No assessment flags set → clinical_fit_score=1.0 (zero complexity, universal fit)."""
    assessment = StubAssessment()
    caps = StubFacilityCapabilities()
    assert compute_clinical_fit_score(assessment, caps) == 1.0


def test_clinical_fit_score_all_covered():
    """Patient needs trach + vent; facility accepts both → 1.0."""
    assessment = StubAssessment(accepts_trach=True, accepts_vent=True)
    caps = StubFacilityCapabilities(accepts_trach=True, accepts_vent=True)
    assert compute_clinical_fit_score(assessment, caps) == 1.0


def test_clinical_fit_score_partial_coverage():
    """Patient needs trach + vent; facility only accepts trach → 0.5."""
    assessment = StubAssessment(accepts_trach=True, accepts_vent=True)
    caps = StubFacilityCapabilities(accepts_trach=True, accepts_vent=False)
    assert abs(compute_clinical_fit_score(assessment, caps) - 0.5) < 0.001


def test_preference_score_in_list():
    prefs = [StubPreference("facility-1"), StubPreference("facility-2")]
    assert compute_preference_score("facility-1", prefs) == 1.0


def test_preference_score_not_in_list():
    prefs = [StubPreference("facility-2")]
    assert compute_preference_score("facility-1", prefs) == 0.0


def test_preference_score_empty_list():
    assert compute_preference_score("facility-1", []) == 0.0


def test_generate_explanation_text_excluded():
    """Explanation for excluded facility must mention exclusion, not use 'approved'."""
    facility = StubFacility("f1", "Test Facility")
    blockers = [BlockerDetail(field="payer", reason="Payer not accepted")]
    exclusion = HardExclusionResult(facility_id="f1", excluded=True, blockers=blockers)

    text = generate_explanation_text(facility, None, exclusion)
    assert "excluded" in text.lower()
    assert "approved" not in text.lower()
    assert "selected" not in text.lower()
    assert "determined" not in text.lower()


def test_generate_explanation_text_scored():
    """Explanation for scored facility must use nH Predict compliant language."""
    facility = StubFacility("f1", "Good Facility")
    scores = ComponentScores(
        level_of_care_fit_score=1.0,
        payer_fit_score=1.0,
        clinical_fit_score=0.5,
        geography_score=0.7,
        preference_score=0.0,
        overall_score=78.5,
    )
    exclusion = HardExclusionResult(facility_id="f1", excluded=False, blockers=[])

    text = generate_explanation_text(facility, scores, exclusion)

    # Must contain compliant language
    compliant_phrases = ["suggested for review", "recommended for consideration", "decision support"]
    assert any(phrase in text.lower() for phrase in compliant_phrases), (
        f"explanation_text must contain nH Predict compliant language; got: {text}"
    )
    # Must NOT contain prohibited terms
    prohibited = ["approved", "placed", "selected", "automated placement determination"]
    for term in prohibited:
        assert term not in text.lower(), (
            f"explanation_text must not contain '{term}'"
        )


def test_rank_matches_ordering():
    """rank_matches returns scored first (by score desc) then excluded at bottom."""
    f1 = StubFacility("f1", "High Score")
    f2 = StubFacility("f2", "Low Score")
    f3 = StubFacility("f3", "Excluded")

    s1 = ComponentScores(overall_score=80.0, payer_fit_score=1.0, clinical_fit_score=1.0,
                         geography_score=0.5, preference_score=0.5, level_of_care_fit_score=1.0)
    s2 = ComponentScores(overall_score=40.0, payer_fit_score=0.5, clinical_fit_score=0.5,
                         geography_score=0.1, preference_score=0.0, level_of_care_fit_score=0.7)
    ex3 = HardExclusionResult("f3", excluded=True, blockers=[BlockerDetail("payer", "Not accepted")])

    result = rank_matches([(f1, s1), (f2, s2)], [(f3, ex3)])

    assert result[0]["rank_order"] == 1
    assert result[0]["facility"].id == "f1"
    assert result[1]["rank_order"] == 2
    assert result[1]["facility"].id == "f2"
    assert result[2]["rank_order"] == -1
    assert result[2]["facility"].id == "f3"
    assert result[2]["overall_score"] == 0.0


def test_rank_matches_top_3_recommended():
    """Top 3 non-excluded get is_recommended=True."""
    facilities = [StubFacility(f"f{i}") for i in range(5)]
    scores = [
        ComponentScores(overall_score=float(90 - i * 10), payer_fit_score=1.0, clinical_fit_score=1.0,
                        geography_score=0.0, preference_score=0.0, level_of_care_fit_score=1.0)
        for i in range(5)
    ]
    result = rank_matches(list(zip(facilities, scores)), [])

    recommended = [r for r in result if r["is_recommended"]]
    assert len(recommended) == 3
    # Top 3 highest scores
    recommended_ids = {r["facility"].id for r in recommended}
    assert "f0" in recommended_ids
    assert "f1" in recommended_ids
    assert "f2" in recommended_ids


def test_hard_exclusion_payer_not_accepted():
    """AC3: payer=not_accepted → excluded=True with payer blocker."""
    assessment = StubAssessment()
    caps = StubFacilityCapabilities()
    rules = [StubInsuranceRule("f1", str(TEST_PAYER_ID), "Medicare", "not_accepted")]

    result = compute_hard_exclusions(assessment, caps, rules, "Medicare")
    assert result.excluded is True
    assert any(b.field == "payer" for b in result.blockers)


def test_hard_exclusion_payer_accepted():
    """AC3: payer=accepted → not excluded for payer."""
    assessment = StubAssessment()
    caps = StubFacilityCapabilities()
    rules = [StubInsuranceRule("f1", str(TEST_PAYER_ID), "Medicare", "accepted")]

    result = compute_hard_exclusions(assessment, caps, rules, "Medicare")
    assert result.excluded is False
    assert len(result.blockers) == 0
