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
# @forgeplan-spec: AC17
"""
Matching engine — pure scoring functions with no DB I/O.

Four-stage pipeline: Retrieve → Exclude → Score → Rank

Hard exclusion semantics (AC3, AC4, AC5):
  - An excluded facility NEVER receives a non-zero overall_score.
  - Excluded facilities appear ONLY at the bottom of ranked results (rank_order=-1).
  - The payer not_accepted status is a hard gate — never treated as a low score.

Scoring weights (AC6): payer_fit=35%, clinical_fit=30%, level_of_care=20%,
geography=10%, preference=5% — sum=1.00 (verified below).

nH Predict compliance (constraint): explanation_text uses "suggested for review"
and "recommended for consideration" — never "approved", "placed", "selected", or
"determined".
"""
# @forgeplan-decision: D-matching-1-haversine-step-function -- Haversine step function (≤10mi=1.0, ≤25mi=0.7, ≤50mi=0.4, >50mi=0.1). Why: spec mandates discrete bins for predictable, auditable geography scoring rather than continuous decay
# @forgeplan-decision: D-matching-2-lru-cache-zip-lookup -- @functools.lru_cache on zip_to_latlon to avoid redundant zipcodes I/O within one scoring run. Why: a single match generation iterates N facilities per case; ZIP lookup is per-case not per-facility so caching avoids N identical lookups

from __future__ import annotations

import functools
import logging
from dataclasses import dataclass, field
from uuid import UUID

from haversine import haversine, Unit

import zipcodes

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Weight constants — MUST sum to 1.00 (AC6)
# ---------------------------------------------------------------------------

_W_PAYER: float = 0.35
_W_CLINICAL: float = 0.30
_W_LEVEL_OF_CARE: float = 0.20
_W_GEOGRAPHY: float = 0.10
_W_PREFERENCE: float = 0.05

# Compile-time sanity check — fail import if weights drift
assert abs((_W_PAYER + _W_CLINICAL + _W_LEVEL_OF_CARE + _W_GEOGRAPHY + _W_PREFERENCE) - 1.0) < 1e-9, (
    "Scoring weights must sum to 1.0"
)

# ---------------------------------------------------------------------------
# Level-of-care adjacency table (AC7)
# Order: snf=0, irf=1, ltach=2
# ---------------------------------------------------------------------------

_LOC_ORDER: dict[str, int] = {"snf": 0, "irf": 1, "ltach": 2}
_LOC_SCORE: dict[int, float] = {0: 1.0, 1: 0.7, 2: 0.4}
# step distance ≥ 3 → 0.0 (no match)


# ---------------------------------------------------------------------------
# Data classes (pure data — no ORM dependency)
# ---------------------------------------------------------------------------


@dataclass
class ScoringContext:
    """
    Resolved patient context for one scoring run.

    patient_lat / patient_lng are resolved from patient_zip via zipcodes library
    with LRU cache. Both are None when patient_zip is null or lookup fails.
    """

    case_id: str
    assessment_id: str
    patient_zip: str | None
    patient_lat: float | None
    patient_lng: float | None
    recommended_level_of_care: str  # snf | irf | ltach
    primary_payer: str  # raw payer name / id string from insurance_primary


@dataclass
class ComponentScores:
    """
    Per-component scores for one facility in one match run.

    All scores are 0.0–1.0 except overall_score which is 0.0–100.0.
    """

    level_of_care_fit_score: float = 0.0
    payer_fit_score: float = 0.0
    clinical_fit_score: float = 0.0
    geography_score: float = 0.0
    preference_score: float = 0.0
    overall_score: float = 0.0


@dataclass
class BlockerDetail:
    """One hard-exclusion reason for a single facility."""

    field: str
    reason: str


@dataclass
class HardExclusionResult:
    """Result of hard-exclusion evaluation for a single facility."""

    facility_id: str
    excluded: bool
    blockers: list[BlockerDetail] = field(default_factory=list)


# ---------------------------------------------------------------------------
# ZIP → lat/lng lookup with LRU cache (AC9, constraint)
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=4096)
def zip_to_latlon(zip_code: str) -> tuple[float, float] | None:
    """
    Resolve a US ZIP code to (latitude, longitude) using the zipcodes library.

    Uses @lru_cache to avoid redundant I/O per scoring run.
    Returns None if zip_code is empty, invalid, or lookup fails gracefully.
    geography_score=0.0 is returned by compute_geography_score when this returns None.
    That is NOT a hard exclusion (constraint).
    """
    # @forgeplan-spec: AC9
    if not zip_code or not zip_code.strip():
        return None
    try:
        results = zipcodes.matching(zip_code.strip())
        if not results:
            return None
        first = results[0]
        lat = float(first["lat"])
        lng = float(first["long"])
        return (lat, lng)
    except Exception:
        logger.debug("ZIP lookup failed for '%s'", zip_code, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Hard exclusion computation (AC3, AC4)
# ---------------------------------------------------------------------------


def compute_hard_exclusions(
    assessment: object,
    capabilities: object,
    insurance_rules: list[object],
    primary_payer: str,
) -> HardExclusionResult:
    """
    Evaluate binary hard-exclusion gates for one facility.

    13 clinical capability mappings + payer not_accepted gate.
    An excluded facility MUST NOT receive a non-zero overall_score (constraint).
    The payer=not_accepted path is a gate here — not a low payer_fit_score (AC3, AC8).

    Returns HardExclusionResult with excluded=True if ANY gate fails.

    Assessment flags use the same field names as FacilityCapabilities — no translation
    layer needed (spec constraint: field names must match exactly).
    """
    # @forgeplan-spec: AC3
    # @forgeplan-spec: AC4
    facility_id: str = str(capabilities.facility_id)
    blockers: list[BlockerDetail] = []

    # ── Payer hard exclusion (AC3, AC8) ───────────────────────────────────────
    payer_rule = _find_payer_rule(insurance_rules, primary_payer)
    if payer_rule is not None and payer_rule.accepted_status == "not_accepted":
        blockers.append(
            BlockerDetail(
                field="payer",
                reason=(
                    f"Facility does not accept payer '{primary_payer}' "
                    f"(accepted_status=not_accepted)"
                ),
            )
        )

    # ── 13 clinical capability mappings (AC4) ─────────────────────────────────
    # Mapping: assessment_flag → facility_capability_flag
    # When assessment flag=True and facility capability=False → hard exclusion.
    #
    # Special case: dialysis_type=hd with in_house_hd_required=True requires
    # BOTH accepts_hd=True AND in_house_hemodialysis=True (constraint).

    # 1. trach → accepts_trach
    if getattr(assessment, "accepts_trach", False) and not getattr(capabilities, "accepts_trach", False):
        blockers.append(
            BlockerDetail(
                field="accepts_trach",
                reason="Patient requires trach care; facility does not accept trach patients",
            )
        )

    # 2. vent → accepts_vent
    if getattr(assessment, "accepts_vent", False) and not getattr(capabilities, "accepts_vent", False):
        blockers.append(
            BlockerDetail(
                field="accepts_vent",
                reason="Patient requires ventilator support; facility does not accept vent patients",
            )
        )

    # 3. accepts_hd (hemodialysis needed) → accepts_hd
    # Also: if in_house_hemodialysis required, BOTH accepts_hd AND in_house_hemodialysis required
    assessment_hd = getattr(assessment, "accepts_hd", False)
    assessment_in_house_hd = getattr(assessment, "in_house_hemodialysis", False)
    if assessment_hd:
        if not getattr(capabilities, "accepts_hd", False):
            blockers.append(
                BlockerDetail(
                    field="accepts_hd",
                    reason="Patient requires hemodialysis; facility does not accept HD patients",
                )
            )
        # Dual check: if in-house HD specifically required (constraint)
        if assessment_in_house_hd and not getattr(capabilities, "in_house_hemodialysis", False):
            blockers.append(
                BlockerDetail(
                    field="in_house_hemodialysis",
                    reason=(
                        "Patient requires in-house hemodialysis; "
                        "facility does not have in-house HD capability"
                    ),
                )
            )

    # 4. accepts_peritoneal_dialysis → accepts_peritoneal_dialysis
    if getattr(assessment, "accepts_peritoneal_dialysis", False) and not getattr(
        capabilities, "accepts_peritoneal_dialysis", False
    ):
        blockers.append(
            BlockerDetail(
                field="accepts_peritoneal_dialysis",
                reason="Patient requires peritoneal dialysis; facility does not accept peritoneal dialysis patients",
            )
        )

    # 5. accepts_wound_vac → accepts_wound_vac
    if getattr(assessment, "accepts_wound_vac", False) and not getattr(capabilities, "accepts_wound_vac", False):
        blockers.append(
            BlockerDetail(
                field="accepts_wound_vac",
                reason="Patient requires wound VAC therapy; facility does not accept wound VAC patients",
            )
        )

    # 6. accepts_oxygen_therapy → accepts_oxygen_therapy
    if getattr(assessment, "accepts_oxygen_therapy", False) and not getattr(
        capabilities, "accepts_oxygen_therapy", False
    ):
        blockers.append(
            BlockerDetail(
                field="accepts_oxygen_therapy",
                reason="Patient requires supplemental oxygen; facility does not accept oxygen therapy patients",
            )
        )

    # 7. accepts_memory_care → accepts_memory_care
    if getattr(assessment, "accepts_memory_care", False) and not getattr(
        capabilities, "accepts_memory_care", False
    ):
        blockers.append(
            BlockerDetail(
                field="accepts_memory_care",
                reason="Patient requires memory care; facility does not accept memory care patients",
            )
        )

    # 8. accepts_bariatric → accepts_bariatric
    if getattr(assessment, "accepts_bariatric", False) and not getattr(capabilities, "accepts_bariatric", False):
        blockers.append(
            BlockerDetail(
                field="accepts_bariatric",
                reason="Patient requires bariatric care; facility does not accept bariatric patients",
            )
        )

    # 9. accepts_iv_antibiotics → accepts_iv_antibiotics
    if getattr(assessment, "accepts_iv_antibiotics", False) and not getattr(
        capabilities, "accepts_iv_antibiotics", False
    ):
        blockers.append(
            BlockerDetail(
                field="accepts_iv_antibiotics",
                reason="Patient requires IV antibiotics; facility does not accept IV antibiotic patients",
            )
        )

    # 10. accepts_tpn → accepts_tpn
    if getattr(assessment, "accepts_tpn", False) and not getattr(capabilities, "accepts_tpn", False):
        blockers.append(
            BlockerDetail(
                field="accepts_tpn",
                reason="Patient requires TPN; facility does not accept TPN patients",
            )
        )

    # 11. accepts_isolation_cases → accepts_isolation_cases
    if getattr(assessment, "accepts_isolation_cases", False) and not getattr(
        capabilities, "accepts_isolation_cases", False
    ):
        blockers.append(
            BlockerDetail(
                field="accepts_isolation_cases",
                reason="Patient requires isolation precautions; facility does not accept isolation cases",
            )
        )

    # 12. accepts_behavioral_complexity → accepts_behavioral_complexity
    if getattr(assessment, "accepts_behavioral_complexity", False) and not getattr(
        capabilities, "accepts_behavioral_complexity", False
    ):
        blockers.append(
            BlockerDetail(
                field="accepts_behavioral_complexity",
                reason=(
                    "Patient has behavioral complexity; "
                    "facility does not accept behavioral complexity patients"
                ),
            )
        )

    return HardExclusionResult(
        facility_id=facility_id,
        excluded=len(blockers) > 0,
        blockers=blockers,
    )


# ---------------------------------------------------------------------------
# Individual component score functions
# ---------------------------------------------------------------------------


def compute_level_of_care_score(
    recommended: str,
    facility_caps: object,
) -> float:
    """
    Level of care adjacency scoring (AC7).

    LOC order: snf=0 < irf=1 < ltach=2
    Exact match → 1.0, one-step adjacent → 0.7, two-step → 0.4, no accepted LOC → 0.0.
    If the facility accepts the recommended LOC exactly → 1.0.
    If the facility accepts a LOC one step away → 0.7.
    If the facility accepts a LOC two steps away → 0.4.
    Best (highest) score among all LOCs the facility accepts is returned.
    """
    # @forgeplan-spec: AC7
    recommended_lower = (recommended or "").lower().strip()
    recommended_idx = _LOC_ORDER.get(recommended_lower)
    if recommended_idx is None:
        # Unknown recommended LOC — cannot score
        return 0.0

    best_score = 0.0

    # Check each LOC the facility accepts
    loc_map: dict[str, str] = {
        "snf": "accepts_snf",
        "irf": "accepts_irf",
        "ltach": "accepts_ltach",
    }
    for loc_name, cap_field in loc_map.items():
        if getattr(facility_caps, cap_field, False):
            facility_idx = _LOC_ORDER.get(loc_name, -1)
            if facility_idx < 0:
                continue
            step_distance = abs(facility_idx - recommended_idx)
            score = _LOC_SCORE.get(step_distance, 0.0)
            if score > best_score:
                best_score = score

    return best_score


def _find_payer_rule(insurance_rules: list[object], primary_payer: str) -> object | None:
    """
    Find the FacilityInsuranceRule for the patient's primary payer.

    Matches by payer_name (case-insensitive) or payer_id.
    Returns None if no rule found for this payer.
    """
    if not primary_payer:
        return None
    primary_lower = primary_payer.strip().lower()
    for rule in insurance_rules:
        payer_name = getattr(rule, "payer_name", "") or ""
        payer_id = getattr(rule, "payer_id", "") or ""
        if payer_name.strip().lower() == primary_lower or payer_id.strip().lower() == primary_lower:
            return rule
    return None


def compute_payer_fit_score(
    insurance_rules: list[object],
    primary_payer: str,
) -> float:
    """
    Payer fit scoring (AC8).

    accepted → 1.0
    conditional → 0.5
    not_found (no rule for this payer) → 0.5 (treat as conditional)
    not_accepted → 0.0 (but this case should have been hard-excluded first; see compute_hard_exclusions)

    NOTE: not_accepted is a hard exclusion. This function should only be called
    for facilities that passed the hard-exclusion gate. If called for a not_accepted
    facility, it returns 0.0 (fail-safe).
    """
    # @forgeplan-spec: AC8
    rule = _find_payer_rule(insurance_rules, primary_payer)
    if rule is None:
        # No rule for this payer — treat as conditional (0.5)
        return 0.5
    status = getattr(rule, "accepted_status", "") or ""
    if status == "accepted":
        return 1.0
    elif status == "conditional":
        return 0.5
    elif status == "not_accepted":
        # Hard exclusion should have caught this — defensive fallback
        return 0.0
    else:
        # Unknown status — treat as conditional
        return 0.5


def compute_clinical_fit_score(
    assessment: object,
    capabilities: object,
) -> float:
    """
    Clinical fit scoring (AC6).

    Score = count of boolean assessment flags that are True WHERE the
    facility capability is also True, divided by total True assessment flags.
    Returns 0.0 if no assessment flags are True (no clinical complexity).

    This measures how well the facility covers the patient's clinical needs.
    """
    # @forgeplan-spec: AC6
    # The 13 clinical boolean flags used for matching
    clinical_flags = [
        "accepts_trach",
        "accepts_vent",
        "accepts_hd",
        "in_house_hemodialysis",
        "accepts_peritoneal_dialysis",
        "accepts_wound_vac",
        "accepts_iv_antibiotics",
        "accepts_tpn",
        "accepts_isolation_cases",
        "accepts_behavioral_complexity",
        "accepts_bariatric",
        "accepts_memory_care",
        "accepts_oxygen_therapy",
    ]

    total_needed = 0
    total_covered = 0

    for flag in clinical_flags:
        assessment_val = getattr(assessment, flag, False)
        if assessment_val:
            total_needed += 1
            facility_val = getattr(capabilities, flag, False)
            if facility_val:
                total_covered += 1

    if total_needed == 0:
        # No clinical complexity — patient is universally suitable, every facility qualifies
        return 1.0

    return total_covered / total_needed


def compute_geography_score(
    patient_lat: float | None,
    patient_lng: float | None,
    facility_lat: float | None,
    facility_lng: float | None,
) -> float:
    """
    Geography score using haversine step function (AC9).

    ≤10 miles → 1.0
    ≤25 miles → 0.7
    ≤50 miles → 0.4
    >50 miles → 0.1

    Any None coordinate → 0.0 (NOT a hard exclusion — constraint).
    geography_score=0.0 when patient_zip is null or facility has no coordinates.
    """
    # @forgeplan-spec: AC9
    # Null-safety: any missing coordinate returns 0.0 without raising (constraint / failure_modes)
    if patient_lat is None or patient_lng is None:
        return 0.0
    if facility_lat is None or facility_lng is None:
        return 0.0

    try:
        distance_miles = haversine(
            (float(patient_lat), float(patient_lng)),
            (float(facility_lat), float(facility_lng)),
            unit=Unit.MILES,
        )
    except Exception:
        logger.debug("Haversine calculation failed", exc_info=True)
        return 0.0

    if distance_miles <= 10.0:
        return 1.0
    elif distance_miles <= 25.0:
        return 0.7
    elif distance_miles <= 50.0:
        return 0.4
    else:
        return 0.1


def compute_preference_score(
    facility_id: str,
    facility_preferences: list[object],
) -> float:
    """
    Preference score bonus (AC17).

    Returns 1.0 if the facility is in the facility_preferences list, 0.0 otherwise.
    """
    # @forgeplan-spec: AC17
    for pref in facility_preferences:
        pref_facility_id = str(getattr(pref, "facility_id", "") or "")
        if pref_facility_id == str(facility_id):
            return 1.0
    return 0.0


def compute_component_scores(
    context: ScoringContext,
    facility: object,
    capabilities: object,
    insurance_rules: list[object],
    facility_preferences: list[object],
    assessment: object,
) -> ComponentScores:
    """
    Compute all component scores for one facility (AC6).

    Calls individual scoring functions and applies weights:
      payer_fit (35%) + clinical_fit (30%) + level_of_care (20%) +
      geography (10%) + preference (5%)  = 100% of overall_score (0–100).
    """
    # @forgeplan-spec: AC6
    loc_score = compute_level_of_care_score(
        recommended=context.recommended_level_of_care,
        facility_caps=capabilities,
    )

    payer_score = compute_payer_fit_score(
        insurance_rules=insurance_rules,
        primary_payer=context.primary_payer,
    )

    clinical_score = compute_clinical_fit_score(
        assessment=assessment,
        capabilities=capabilities,
    )

    geo_score = compute_geography_score(
        patient_lat=context.patient_lat,
        patient_lng=context.patient_lng,
        facility_lat=getattr(facility, "latitude", None),
        facility_lng=getattr(facility, "longitude", None),
    )

    pref_score = compute_preference_score(
        facility_id=str(facility.id),
        facility_preferences=facility_preferences,
    )

    overall = (
        payer_score * _W_PAYER
        + clinical_score * _W_CLINICAL
        + loc_score * _W_LEVEL_OF_CARE
        + geo_score * _W_GEOGRAPHY
        + pref_score * _W_PREFERENCE
    ) * 100.0

    return ComponentScores(
        level_of_care_fit_score=round(loc_score, 4),
        payer_fit_score=round(payer_score, 4),
        clinical_fit_score=round(clinical_score, 4),
        geography_score=round(geo_score, 4),
        preference_score=round(pref_score, 4),
        overall_score=round(overall, 2),
    )


# ---------------------------------------------------------------------------
# Explanation text generation (AC11)
# ---------------------------------------------------------------------------


def generate_explanation_text(
    facility: object,
    scores: ComponentScores | None,
    exclusion: HardExclusionResult,
) -> str:
    """
    Generate human-readable explanation text at write time (AC11).

    This function is called ONCE per FacilityMatch at INSERT time.
    The result is stored verbatim; GET requests return stored text unchanged.

    nH Predict compliance: uses "suggested for review" and
    "recommended for consideration" — NEVER "approved", "placed",
    "selected", or "determined" (constraint).
    """
    # @forgeplan-spec: AC11
    facility_name = getattr(facility, "facility_name", str(facility.id))

    if exclusion.excluded:
        blocker_summaries = "; ".join(b.reason for b in exclusion.blockers)
        return (
            f"{facility_name} was excluded from consideration for the following reasons: "
            f"{blocker_summaries}. "
            f"This facility does not meet the minimum clinical or payer criteria and "
            f"has not been suggested for review."
        )

    if scores is None:
        return (
            f"{facility_name} has been included in the facility options suggested for review. "
            f"Component scoring data is unavailable."
        )

    overall = scores.overall_score
    loc = scores.level_of_care_fit_score
    payer = scores.payer_fit_score
    clinical = scores.clinical_fit_score
    geo = scores.geography_score
    pref = scores.preference_score

    # Determine overall recommendation language
    if overall >= 70.0:
        recommendation_phrase = "strongly recommended for consideration"
    elif overall >= 40.0:
        recommendation_phrase = "suggested for review"
    else:
        recommendation_phrase = "included in the options for coordinator review"

    text = (
        f"{facility_name} is {recommendation_phrase} with an overall score of "
        f"{overall:.1f}/100. "
        f"Component breakdown: level-of-care fit={loc:.2f}, payer fit={payer:.2f}, "
        f"clinical fit={clinical:.2f}, geography={geo:.2f}, preference={pref:.2f}. "
        f"This scoring is provided as decision support for human coordinators only "
        f"and requires clinical judgment before any facility contact is initiated."
    )
    return text


# ---------------------------------------------------------------------------
# Ranking (AC5, AC12)
# ---------------------------------------------------------------------------


def rank_matches(
    scored_items: list[tuple[object, ComponentScores]],
    excluded_items: list[tuple[object, HardExclusionResult]],
) -> list[dict]:
    """
    Rank scored and excluded facilities into final ordered result list (AC5, AC12).

    Ranked (non-excluded) facilities ordered by overall_score descending (rank_order 1..N).
    Top 3 non-excluded facilities receive is_recommended=True (AC12).
    Excluded facilities appended at bottom with rank_order=-1 (AC3, AC5).

    Returns a list of dicts with all fields needed for FacilityMatch insertion.
    """
    # @forgeplan-spec: AC5
    # @forgeplan-spec: AC12

    # Sort scored facilities by overall_score descending
    sorted_scored = sorted(
        scored_items,
        key=lambda x: x[1].overall_score,
        reverse=True,
    )

    result = []

    for rank_idx, (facility, scores) in enumerate(sorted_scored, start=1):
        is_recommended = rank_idx <= 3
        exclusion = HardExclusionResult(
            facility_id=str(facility.id), excluded=False, blockers=[]
        )
        explanation = generate_explanation_text(facility, scores, exclusion)

        result.append({
            "facility": facility,
            "scores": scores,
            "exclusion": None,
            "rank_order": rank_idx,
            "is_recommended": is_recommended,
            "selected_for_outreach": False,
            "overall_score": scores.overall_score,
            "payer_fit_score": scores.payer_fit_score,
            "clinical_fit_score": scores.clinical_fit_score,
            "geography_score": scores.geography_score,
            "preference_score": scores.preference_score,
            "level_of_care_fit_score": scores.level_of_care_fit_score,
            "blockers_json": None,
            "explanation_text": explanation,
        })

    # Append excluded facilities at the bottom with rank_order=-1
    for facility, exclusion in excluded_items:
        explanation = generate_explanation_text(facility, None, exclusion)
        blockers_list = [
            {"field": b.field, "reason": b.reason} for b in exclusion.blockers
        ]

        result.append({
            "facility": facility,
            "scores": None,
            "exclusion": exclusion,
            "rank_order": -1,
            "is_recommended": False,
            "selected_for_outreach": False,
            "overall_score": 0.0,
            "payer_fit_score": None,
            "clinical_fit_score": None,
            "geography_score": None,
            "preference_score": None,
            "level_of_care_fit_score": None,
            "blockers_json": blockers_list,
            "explanation_text": explanation,
        })

    return result


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------


def build_scoring_context(
    case: object,
    assessment: object,
) -> ScoringContext:
    """
    Build ScoringContext from PatientCase and ClinicalAssessment ORM objects.

    Resolves patient_zip → lat/lng via ZIP lookup with LRU cache.
    Handles null patient_zip gracefully (geography_score=0.0, not an exclusion).
    """
    patient_zip: str | None = getattr(case, "patient_zip", None)
    patient_lat: float | None = None
    patient_lng: float | None = None

    if patient_zip:
        coords = zip_to_latlon(patient_zip)
        if coords is not None:
            patient_lat, patient_lng = coords

    primary_payer: str = getattr(case, "insurance_primary", None) or ""

    return ScoringContext(
        case_id=str(case.id),
        assessment_id=str(assessment.id),
        patient_zip=patient_zip,
        patient_lat=patient_lat,
        patient_lng=patient_lng,
        recommended_level_of_care=getattr(assessment, "recommended_level_of_care", "") or "",
        primary_payer=primary_payer,
    )
