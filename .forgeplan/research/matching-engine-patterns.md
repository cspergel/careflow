# Research: Weighted Rules Scoring Engine — Python Facility Matching (Healthcare)

**Researched:** 2026-04-11
**Tech stack context:** Python backend, Django/FastAPI, PostgreSQL (via Drizzle ORM or SQLAlchemy), no ML dependency

---

## Recommended Packages

### Geography / ZIP Geocoding

1. **haversine** (v2.9.0) — Great-circle distance between two lat/lng points
   - Downloads: 767,542/week | License: MIT | Last published: 2024-11-28 | Status: APPROVED
   - Quality: 354 GitHub stars, 24 contributors, zero dependencies, 117 dependent packages
   - Why: Lightweight (7.7 kB), pure-Python with optional NumPy/Numba acceleration, vectorized `haversine_vector` for scoring all facilities in one call. No network required at runtime.
   - Install: `pip install haversine`

2. **zipcodes** (v1.3.0) — Offline US ZIP code lookup returning lat/long
   - Downloads: 82,940/week | License: MIT | Last published: 2025-02-16 | Status: APPROVED
   - Quality: 78 GitHub stars, 3 open issues, actively maintained (commit Feb 2025)
   - Why: Data stored as compressed JSON (no SQLite required), returns `lat` and `long` float strings per ZIP, works entirely offline in production. Data updated Feb 2025 — recent enough for US facility coordinates.
   - Install: `pip install zipcodes`
   - Alternative: **pgeocode** (v0.5.0, BSD-3, 228,254 downloads/week) — more downloads but requires pandas + numpy and downloads GeoNames data at first run (~4 MB cache). Prefer `zipcodes` for zero-dependency offline usage; prefer `pgeocode` if you need international postal code support.

3. **pgeocode** (v0.5.0) — Postal code geocoding via GeoNames database
   - Downloads: 228,254/week | License: BSD-3-Clause | Last published: 2024-04-13 | Status: APPROVED
   - Quality: 264 GitHub stars, 16 open issues, 9 releases since 2018
   - Why: Strong option if the patient ZIP lookup needs fuzzy matching or you want the broader GeoNames dataset. Caches to `~/.cache/pgeocode` after first download.
   - Install: `pip install pgeocode`

### Scoring / Rule Engine (optional — see patterns section for pure-Python approach)

4. **rule-engine** (v4.5.3) — Typed expression language for rule evaluation
   - Downloads: not individually tracked (niche) | License: BSD-3-Clause | Last published: 2025-02-09 | Status: APPROVED
   - Why: Only relevant if you want non-developer staff to write exclusion rules in a config file. For this project the boolean field-comparison exclusions are deterministic enough to be pure Python — skip this unless product requirements evolve.
   - Install: `pip install rule-engine`

---

## License Report

| Package | License | Downloads/wk | Last Published | Status |
|---------|---------|-------------|----------------|--------|
| haversine | MIT | 767,542 | 2024-11-28 | APPROVED |
| zipcodes | MIT | 82,940 | 2025-02-16 | APPROVED |
| pgeocode | BSD-3-Clause | 228,254 | 2024-04-13 | APPROVED |
| rule-engine | BSD-3-Clause | (niche) | 2025-02-09 | APPROVED |

**Flagged Packages:** None. All candidates carry permissive licenses suitable for commercial healthcare software.

Summary: 4 approved, 0 warnings, 0 flagged

---

## Architecture Pattern: Retrieve → Exclude → Score → Rank

This is the production-standard two/three-stage pattern used by large recommendation systems (Google, Netflix, etc.) and maps cleanly onto the facility matching problem. The key insight is that these stages have very different computational costs and should be separated explicitly:

```
Stage 1 — RETRIEVE
  Load all active facilities from DB (or cache)
  → [FacilityRecord, ...]

Stage 2 — EXCLUDE  (hard gates, O(n) boolean checks, fast)
  For each facility, run all exclusion predicates
  If any predicate returns True → drop facility, record reason
  → [eligible_facilities, ...], [excluded_facilities_with_reason, ...]

Stage 3 — SCORE  (weighted arithmetic, O(n * components))
  For each eligible facility, compute component scores
  Apply weights, sum to composite
  → [FacilityMatch(facility, scores, composite, explanation), ...]

Stage 4 — RANK
  Sort FacilityMatch list by composite desc
  Return top-N (or all) with pagination
```

### Why stages must stay separated

The four-stage separation (retrieve → filter → score → rank) is explicitly documented in production recommendation systems literature. For the facility matching use case:

- **Correctness:** Hard exclusions are not "low scores" — a facility that rejects a patient's payer should never appear in results at rank 99, even at score 0.01. Hard exclusions must be binary gates.
- **Auditability:** Separation means each dropped facility has a recorded exclusion reason, not just an absence from results.
- **Performance:** Exclusions run in microseconds (boolean field comparisons). Running the heavier geography/scoring computation only on eligible facilities keeps the engine fast even with 5,000+ facility records.

---

## Implementation Patterns

### 1. Data Structures

Use standard dataclasses (stdlib, no dependencies) for the scoring pipeline. Use Pydantic only at the API boundary (validated input/output), not inside the scoring engine. Benchmarks show Pydantic adds 6.5× slower performance and 2.5× more memory versus dataclasses for internal computation.

```python
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

class ExclusionReason(str, Enum):
    PAYER_NOT_ACCEPTED = "payer_not_accepted"
    LEVEL_OF_CARE_MISMATCH = "level_of_care_mismatch"
    CAPABILITY_MISSING = "capability_missing"
    GEOGRAPHIC_OUT_OF_RANGE = "geographic_out_of_range"
    CAPACITY_FULL = "capacity_full"

@dataclass
class ExclusionResult:
    facility_id: str
    reason: ExclusionReason
    detail: str  # human-readable, stored for audit

@dataclass
class ComponentScores:
    payer_fit: float       # 0.0–1.0, weight 0.35
    clinical_fit: float    # 0.0–1.0, weight 0.30
    level_of_care: float   # 0.0–1.0, weight 0.20
    geography: float       # 0.0–1.0, weight 0.10
    preference: float      # 0.0–1.0, weight 0.05

@dataclass
class FacilityMatch:
    facility_id: str
    facility_name: str
    composite_score: float
    component_scores: ComponentScores
    explanation: str       # human-readable, stored on the DB record
    rank: int
    distance_miles: Optional[float] = None
```

### 2. Weighted Scoring Engine

The pattern used in production signal-scoring systems (Crosley, 2025) is a pure weighted linear combination — the Weighted Sum Model (WSM), one of the oldest and most defensible MCDA methods. Weights must sum to 1.0.

```python
WEIGHTS = {
    "payer_fit":     0.35,
    "clinical_fit":  0.30,
    "level_of_care": 0.20,
    "geography":     0.10,
    "preference":    0.05,
}
# assert: sum(WEIGHTS.values()) == 1.0

def compute_composite(scores: ComponentScores) -> float:
    return round(
        scores.payer_fit     * WEIGHTS["payer_fit"]     +
        scores.clinical_fit  * WEIGHTS["clinical_fit"]  +
        scores.level_of_care * WEIGHTS["level_of_care"] +
        scores.geography     * WEIGHTS["geography"]     +
        scores.preference    * WEIGHTS["preference"],
        4,
    )
```

Keep each component scorer as a pure function (no side effects, no I/O, no DB calls). This makes unit testing trivial and allows the pipeline to be benchmarked cleanly.

### 3. Hard Exclusion Pattern

The exclusion stage iterates predicates and short-circuits on first failure. Using a list of predicate functions makes it easy to add new exclusion rules without modifying core logic.

```python
from typing import Callable

# Each predicate returns (passed: bool, reason: ExclusionReason | None, detail: str)
ExclusionPredicate = Callable[
    [ClinicalAssessment, FacilityRecord],
    tuple[bool, Optional[ExclusionReason], str]
]

def check_payer_acceptance(
    assessment: ClinicalAssessment,
    facility: FacilityRecord,
) -> tuple[bool, Optional[ExclusionReason], str]:
    if assessment.primary_payer_id not in facility.accepted_payer_ids:
        return (
            False,
            ExclusionReason.PAYER_NOT_ACCEPTED,
            f"Facility does not accept payer {assessment.primary_payer_id!r}",
        )
    return True, None, ""

def check_level_of_care(
    assessment: ClinicalAssessment,
    facility: FacilityRecord,
) -> tuple[bool, Optional[ExclusionReason], str]:
    if assessment.required_loc not in facility.supported_levels_of_care:
        return (
            False,
            ExclusionReason.LEVEL_OF_CARE_MISMATCH,
            f"Facility does not offer level of care {assessment.required_loc!r}",
        )
    return True, None, ""

def check_capabilities(
    assessment: ClinicalAssessment,
    facility: FacilityRecord,
) -> tuple[bool, Optional[ExclusionReason], str]:
    # Boolean field mapping: assessment.needs_detox → facility.has_detox, etc.
    required_caps = {
        "has_detox":         assessment.needs_detox,
        "has_dual_diagnosis": assessment.has_dual_diagnosis,
        "has_medication_assisted": assessment.needs_mat,
        "accepts_minors":    assessment.patient_age < 18,
    }
    for field_name, required in required_caps.items():
        if required and not getattr(facility.capabilities, field_name, False):
            return (
                False,
                ExclusionReason.CAPABILITY_MISSING,
                f"Facility missing required capability: {field_name}",
            )
    return True, None, ""

EXCLUSION_PREDICATES: list[ExclusionPredicate] = [
    check_payer_acceptance,
    check_level_of_care,
    check_capabilities,
]

def apply_exclusions(
    assessment: ClinicalAssessment,
    facilities: list[FacilityRecord],
) -> tuple[list[FacilityRecord], list[ExclusionResult]]:
    eligible = []
    excluded = []
    for facility in facilities:
        passed = True
        for predicate in EXCLUSION_PREDICATES:
            ok, reason, detail = predicate(assessment, facility)
            if not ok:
                excluded.append(ExclusionResult(
                    facility_id=facility.id,
                    reason=reason,
                    detail=detail,
                ))
                passed = False
                break  # short-circuit: one failure is enough
        if passed:
            eligible.append(facility)
    return eligible, excluded
```

**Key design decision:** Each predicate records exactly one reason. If a facility fails multiple checks, only the first failure is recorded. This is intentional — showing all failures to users is confusing; showing the first (most important) failure is actionable.

### 4. Geography Scoring: ZIP to Haversine Distance

The two-step pattern: lookup patient ZIP lat/lng offline → compute haversine to facility coordinates → normalize to [0, 1] score with configurable cutoff.

```python
import zipcodes
from haversine import haversine, Unit
from functools import lru_cache

MAX_DISTANCE_MILES = 150.0  # facilities beyond this score 0.0

@lru_cache(maxsize=5000)
def zip_to_latlong(zip_code: str) -> tuple[float, float] | None:
    """Offline lookup; cached to avoid repeated JSON decompression."""
    results = zipcodes.matching(zip_code)
    if not results:
        return None
    z = results[0]
    return float(z["lat"]), float(z["long"])

def score_geography(
    patient_zip: str,
    facility_lat: float,
    facility_lng: float,
    max_miles: float = MAX_DISTANCE_MILES,
) -> tuple[float, float | None]:
    """
    Returns (score: 0.0-1.0, distance_miles: float | None).
    Score is 1.0 at distance 0, linearly decays to 0.0 at max_miles.
    Returns (0.5, None) if patient ZIP cannot be geocoded (neutral score).
    """
    patient_coords = zip_to_latlong(patient_zip)
    if patient_coords is None:
        return 0.5, None  # neutral fallback; flag for review

    distance = haversine(
        patient_coords,
        (facility_lat, facility_lng),
        unit=Unit.MILES,
    )
    score = max(0.0, 1.0 - (distance / max_miles))
    return round(score, 4), round(distance, 1)
```

**Linear decay vs exponential decay:** Linear (1 - d/max) is simpler and more explainable to clinical staff. Exponential decay (e.g., `exp(-d/50)`) rewards nearby facilities more aggressively. Start with linear; adjust if business rules dictate strong preference for <25-mile facilities.

**Vectorized option for bulk scoring:** The `haversine_vector` function can compute distances from one point to N points in a single call when scoring 500+ facilities:

```python
from haversine import haversine_vector, Unit
import numpy as np

patient_coords = zip_to_latlong(patient_zip)  # (lat, lng)
facility_coords = [(f.lat, f.lng) for f in eligible_facilities]

distances = haversine_vector(
    [patient_coords] * len(facility_coords),
    facility_coords,
    unit=Unit.MILES,
    comb=False,  # paired, not cross-product
)
```

### 5. Human-Readable Explanation Text

The explanation text should be a single string generated from component scores and stored on the `FacilityMatch` DB record. Pure f-string template — no external library needed. The pattern is additive: build a list of clauses, join them.

```python
def generate_explanation(
    scores: ComponentScores,
    distance_miles: float | None,
    facility_name: str,
) -> str:
    """
    Generates a one-paragraph human-readable explanation suitable for
    display to care coordinators and for audit log storage.
    """
    clauses = []

    # Payer fit
    if scores.payer_fit >= 0.90:
        clauses.append("payer is in-network and accepted without restriction")
    elif scores.payer_fit >= 0.60:
        clauses.append("payer is accepted with minor limitations")
    else:
        clauses.append("payer coverage is limited but present")

    # Clinical fit
    if scores.clinical_fit >= 0.85:
        clauses.append("clinical capabilities are a strong match for the patient's needs")
    elif scores.clinical_fit >= 0.60:
        clauses.append("clinical capabilities meet core treatment needs")
    else:
        clauses.append("clinical capabilities partially address treatment needs")

    # Level of care
    if scores.level_of_care >= 0.90:
        clauses.append("level of care is an exact match")
    elif scores.level_of_care >= 0.60:
        clauses.append("level of care is clinically appropriate")
    else:
        clauses.append("level of care is a partial match")

    # Geography
    if distance_miles is not None:
        if distance_miles < 25:
            clauses.append(f"facility is {distance_miles:.0f} miles away (local)")
        elif distance_miles < 75:
            clauses.append(f"facility is {distance_miles:.0f} miles away (regional)")
        else:
            clauses.append(f"facility is {distance_miles:.0f} miles away")
    else:
        clauses.append("geographic distance could not be calculated")

    # Composite summary
    composite = compute_composite(scores)
    summary = f"{facility_name} scored {composite:.0%} overall. "
    summary += "; ".join(clauses).capitalize() + "."
    return summary
```

**Example output:**
> "Sunrise Recovery Center scored 82% overall. Payer is in-network and accepted without restriction; clinical capabilities are a strong match for the patient's needs; level of care is an exact match; facility is 18 miles away (local)."

**Design rule:** Explanation text is derived from scores, not from the facility record directly. This ensures the stored explanation is always consistent with the stored component scores — no drift.

### 6. Complete Pipeline Sketch

```python
def match_facilities(
    assessment: ClinicalAssessment,
    all_active_facilities: list[FacilityRecord],
) -> tuple[list[FacilityMatch], list[ExclusionResult]]:
    """
    Main entry point for the matching engine.
    Returns (ranked_matches, excluded_with_reasons).
    """
    # Stage 1: Hard exclusions
    eligible, excluded = apply_exclusions(assessment, all_active_facilities)

    # Stage 2: Score eligible facilities
    matches = []
    for facility in eligible:
        geo_score, distance_miles = score_geography(
            assessment.patient_zip,
            facility.lat,
            facility.lng,
        )
        scores = ComponentScores(
            payer_fit=score_payer_fit(assessment, facility),
            clinical_fit=score_clinical_fit(assessment, facility),
            level_of_care=score_level_of_care(assessment, facility),
            geography=geo_score,
            preference=score_preference(assessment, facility),
        )
        composite = compute_composite(scores)
        explanation = generate_explanation(scores, distance_miles, facility.name)

        matches.append(FacilityMatch(
            facility_id=facility.id,
            facility_name=facility.name,
            composite_score=composite,
            component_scores=scores,
            explanation=explanation,
            rank=0,  # assigned below
            distance_miles=distance_miles,
        ))

    # Stage 3: Rank
    matches.sort(key=lambda m: m.composite_score, reverse=True)
    for i, match in enumerate(matches):
        match.rank = i + 1

    return matches, excluded
```

---

## Reference Projects

### 1. PatientMatcher (Clinical-Genomics/patientMatcher)

**URL:** https://github.com/Clinical-Genomics/patientMatcher
**Stack:** Python, MongoDB, REST API, MME (Matchmaker Exchange) protocol
**Architecture:** Standalone MME server with pluggable scoring algorithms

**What to learn:**
- Separates the "match candidate retrieval" from "score computation" — patients are retrieved by genomic proximity, then scored by a configurable similarity function. The same retrieve-then-score pattern applies to facility matching.
- Scoring algorithm is configurable via settings (weights, thresholds) without code changes. Relevant pattern: put your `WEIGHTS` dict in Django settings or an environment variable, not hardcoded.
- Provides a `matching_score` composite plus `phenotype_score` and `genotype_score` separately — analogous to your composite plus component_scores. Both are stored for auditability.

**What to avoid:**
- The MME protocol requires HTTP-based exchange between nodes — this is an over-engineered integration layer for a self-contained facility matching use case. Don't adopt the server-to-server protocol.

### 2. Signal Scoring Pipeline (Crosley, 2025)

**URL:** https://blakecrosley.com/blog/signal-scoring-pipeline
**Stack:** Pure Python, no dependencies
**Architecture:** Pure-function scoring with hard thresholds as gates

**What to learn:**
- Component scores are stored as a flat dict (`{"relevance": 0.72, "actionability": 0.60, ..., "composite": 0.81}`). This maps directly to your `ComponentScores` dataclass — each field is independently auditable.
- Weights evolved from equal (25/25/25/25) to empirically tuned (35/30/20/15) over months of production use. Plan for the same evolution — make weights configurable from day one.
- Routing logic uses hard thresholds on the composite score (>= 0.55 → auto-route, >= 0.30 → review queue, < 0.30 → reject). Consider analogous thresholds: >= 0.70 → recommend with confidence, 0.40–0.70 → recommend with caveats, < 0.40 → flag for manual review.
- Scoring logic is factored into pure functions with zero I/O. The pipeline calls them; the functions know nothing about the pipeline.

**What to avoid:**
- The article uses plain dicts instead of typed dataclasses. For a healthcare audit system, the dataclass pattern (with field names, typed fields, and `asdict()` serialization) is safer and more maintainable.

### 3. Multi-Stage Recommendation Architecture (Google ML Crash Course)

**URL:** https://developers.google.com/machine-learning/recommendation/overview/candidate-generation
**Stack:** General (Python examples)
**Architecture:** Retrieve → Filter → Score → Re-rank

**What to learn:**
- The standard multi-stage architecture decouples computational cost from scoring accuracy. The filtering stage is explicitly described as O(n) boolean checks that run after retrieval but before expensive scoring. This validates the hard-exclusion-before-scoring design.
- The ordering/re-ranking stage is described as "usually simple, lightweight logic" — consistent with a straightforward `sort(composite_score)`.

**What to avoid:**
- The Google architecture uses vector embeddings and approximate nearest neighbor search for candidate generation — entirely unnecessary for a facility set capped at ~5,000 records. All facilities can be scored directly.

---

## Performance Analysis

### How many facilities to score at once?

Based on the architecture of the scoring engine (pure Python arithmetic, no I/O per facility):

- **At 500 facilities:** Scoring completes in under 5ms in CPython 3.11+ assuming pure arithmetic scorers. The bottleneck is ZIP lookup and database round-trips.
- **At 5,000 facilities:** Still under 50ms for the scoring arithmetic. Exclusion filtering will reduce the eligible pool; expect 500–2,000 eligible facilities after exclusions in a typical US market.
- **At 50,000+ facilities:** Consider pre-filtering by state or region before running the full exclusion pipeline.

The recommendation for this project: **load all active facilities at application startup, cache them in memory, and run the full pipeline per request**. At <5,000 facilities, this is always faster than a DB query per match request.

### Caching Strategy

```python
from functools import lru_cache
import time

# Level 1: ZIP code geocoding — pure lookup, highly cacheable
@lru_cache(maxsize=10_000)  # US has ~42,000 ZIP codes; 10k covers most markets
def zip_to_latlong(zip_code: str) -> tuple[float, float] | None:
    ...

# Level 2: Facility list — cached with TTL to pick up new facilities
_facility_cache: list[FacilityRecord] = []
_cache_loaded_at: float = 0.0
FACILITY_CACHE_TTL = 300  # seconds (5 minutes)

def get_active_facilities() -> list[FacilityRecord]:
    global _facility_cache, _cache_loaded_at
    now = time.monotonic()
    if not _facility_cache or (now - _cache_loaded_at) > FACILITY_CACHE_TTL:
        _facility_cache = load_active_facilities_from_db()
        _cache_loaded_at = now
    return _facility_cache

# Level 3: If using Django, use Django's cache framework with a short TTL
# from django.core.cache import cache
# facilities = cache.get_or_set("active_facilities", load_active_facilities_from_db, 300)
```

**What to cache vs what not to cache:**
- CACHE: ZIP lat/lng lookups (static data), active facility list (changes rarely)
- DO NOT CACHE: Individual match results (patient-specific, never reused), exclusion results (payer rules change)

### Pydantic vs Dataclass inside the scoring engine

Per benchmark data (2025): Pydantic adds 6.5× overhead and 2.5× memory versus stdlib dataclasses for internal computation. Use Pydantic at API request/response boundaries, dataclasses inside the scoring engine. For 500 facilities × 5 component scores, this difference is ~2ms vs ~13ms — meaningful at scale.

---

## Gotchas

### ZIP Code Geocoding

- ZIP codes are not points — they are delivery route areas. The centroid lat/lng returned by any library is the approximate center of the delivery route, which can be several miles from the actual patient address. For the purposes of facility matching, this imprecision is acceptable and expected.
- ZIP codes change over time (USPS adds/retires routes). The `zipcodes` package data was last updated February 2025. For a production healthcare system, plan to update the package annually or switch to `pgeocode` (GeoNames data) which allows data refresh without a code change.
- Approximately 22% of US ZIP codes are PO Box-only (no lat/lng centroid). The `uszipcode` database (1.0.1, last updated 2022) notes this. The `zipcodes` package v1.3.0 includes 2025 data and handles this by returning empty results for PO Box ZIPs — your geocoder fallback (0.5 neutral score) covers this case.
- International addresses: if any patients have Canadian or other non-US ZIP/postal codes, `zipcodes` will return empty. Use `pgeocode` as the fallback for non-US lookups.

### Scoring Design

- **Component scores must be normalized to [0, 1].** If a component scorer returns a raw count (e.g., "3 out of 5 capabilities matched"), divide by the maximum before storing. Raw counts break the weighted sum math.
- **Payer fit is binary in most real cases** (payer accepted or not). If it is binary, the payer_fit scorer should return 1.0 or 0.0. However, many facilities accept a payer with limitations (e.g., "Medicaid accepted for detox only, not residential"). Model this as 0.5 rather than 1.0 or 0.0 — this requires explicit data in the FacilityCapabilities model.
- **Level of care adjacency:** In behavioral health, ASAM criteria allow adjacent levels of care (e.g., a patient assessed at 3.5 may be appropriately placed at 3.7 or 3.3). Scoring exact LOC match at 1.0 and adjacent LOC at 0.7 (one step) is more clinically appropriate than binary match/no-match.
- **Do not use MCDM libraries** (mcdm, pyscoring, etc.) for this use case. These libraries are designed for decision problems with dozens of criteria and complex normalization schemes. For 5 weighted components, the arithmetic is 5 multiplications and 4 additions — adding a library creates a dependency for a one-liner.

### Hard Exclusions

- **The order of exclusion predicates matters for the audit trail.** Put the most common exclusion (payer rejection, typically the highest-volume disqualifier in US behavioral health) first. This produces the most informative audit record for the most facilities.
- **Capacity exclusion is time-sensitive.** A facility's capacity changes in real time; the DB record may be stale. Consider a separate "soft" capacity flag rather than a hard exclusion for capacity, unless the facility explicitly marks itself as full.
- **Do not conflate hard exclusions with low scores.** A facility that scores 0.0 on clinical fit should still appear in results (it might be the only facility that accepts the payer). Hard exclusion means the facility is legally or clinically unable to accept the patient.

### Explanation Text

- **Write explanations for coordinators, not for developers.** "payer_fit score: 0.91" is not useful. "Payer is in-network and accepted without restriction" is actionable.
- **Store the explanation text verbatim in the DB.** Do not regenerate it from scores on read — weight thresholds may change, which would retroactively alter the explanation of a historical placement decision.
- **Keep explanation templates in a constants file**, not scattered across scorer functions. This makes it easy to review all possible outputs for clinical accuracy.

### Performance

- Calling `zipcodes.matching()` in a tight loop without `@lru_cache` decompresses the bz2 JSON file on every call. Cache aggressively — patient ZIPs repeat across many match requests.
- If using Django signals or Celery tasks to run matching asynchronously, ensure the facility cache is warmed before the first task runs (use `AppConfig.ready()` or a post-migration signal).
- Profile with a realistic dataset before optimizing. At 1,000 facilities, CPython is fast enough with no vectorization. Only reach for `haversine_vector` (NumPy) if profiling shows geography scoring is the bottleneck at your scale.

---

## Domain Context: Healthcare Placement Criteria

The LOCUS (Level of Care Utilization System) and ASAM criteria are the dominant clinical frameworks used by US behavioral health payers:

- **LOCUS domains:** risk of harm, functional status, comorbidity, recovery environment, treatment history
- **ASAM dimensions:** acute intoxication, biomedical conditions, emotional/behavioral conditions, readiness to change, relapse potential, recovery environment

These map to the `ClinicalAssessment` fields your engine will score against. The `level_of_care` component scorer should reflect ASAM's six levels (0.5, I, II.1, II.5, III.1, III.3, III.5, III.7, IV) with adjacency scoring rather than strict binary match.

The payer-network scoring (35% weight) being the highest weight is defensible: in US behavioral health, payer rejection is the single most common reason a placement fails. Payer fit being the dominant scoring factor aligns with clinical operations reality.

---

## Research Gaps

- **No benchmark found** comparing `zipcodes` vs `pgeocode` vs a raw SQLite lookup at 10,000+ ZIP resolutions per minute. The `lru_cache` on `zip_to_latlong` makes this moot for most deployments, but if geocoding is called uncached at high volume, a benchmark would be worth running.
- **uszipcode (v1.0.1, last updated 2022)** appeared in several recommendations but has not been maintained. Data is from Census 2010 with 2020 demographic updates. Do not use for lat/lng lookups — use `zipcodes` (2025 data) or `pgeocode` instead.
- **No open-source reference found** for a Python behavioral health facility-to-patient placement scoring engine specifically. The PatientMatcher project is closest in spirit but operates on genomic matching, not clinical/payer/geographic criteria. This means the implementation patterns must be derived from first principles — which is what this research provides.
- **Payer fit scoring complexity** was not fully researched. Real payer matching in US behavioral health involves NPI numbers, payer plan IDs, network tiers (in-network vs out-of-network vs exception), and prior authorization requirements. The 0.0/0.5/1.0 scoring model described here is a simplification — the actual payer fit scorer will need access to a payer contracting data model.
- **Geographic preference vs geographic exclusion:** The research found no clear industry consensus on whether geography should be a hard cutoff (e.g., exclude facilities >200 miles) or always a soft score (as modeled here). The current design (soft score, linear decay) is more flexible but allows technically-eligible facilities at 400 miles to appear in results. Consider adding a configurable geographic hard-exclusion threshold in addition to the soft score.
