## Review: matching-module
**Date:** 2026-04-11T00:00:00Z
**Reviewer:** Claude Sonnet 4.6
**Review type:** native
**Cycle:** 1

---

### Acceptance Criteria

- **AC1: PASS** — `service.py:_resolve_assessment` (lines 107-168) returns HTTP 400 with detail containing "finalized" when no finalized assessment exists (auto-resolve path, line 160-167) and when an explicitly-provided assessment has review_status != "finalized" (lines 137-144). Three tests cover this: `test_generate_returns_400_when_no_finalized_assessment`, `test_generate_returns_400_when_no_assessment_at_all`, `test_generate_returns_400_when_explicit_assessment_not_finalized`. All assert status_code==400 and "finalized" in detail. No FacilityMatch rows are created because the 400 is raised before the INSERT loop.

- **AC2: PASS** — `service.py:_load_active_facilities` (lines 171-190) queries with `Facility.active_status.is_(True)` and `Facility.organization_id == str(organization_id)`. `test_generate_creates_matches_only_for_active_facilities` seeds 10 active + 2 inactive, asserts exactly 10 matches returned, asserts no inactive facility_id appears in results, and asserts case advances to `facility_options_generated`. Case status transition via `transition_case_status` at service.py lines 425-434.

- **AC3: PASS** — `engine.py:compute_hard_exclusions` (lines 188-199) appends a `BlockerDetail(field="payer", reason=...)` when `payer_rule.accepted_status == "not_accepted"`. `rank_matches` (engine.py lines 741-763) sets `overall_score=0.0`, `rank_order=-1`, `blockers_json=list` for excluded items. `test_payer_not_accepted_produces_blocked_match` verifies `rank_order==-1`, `overall_score==0.0`, `blockers_json` non-empty with `field=="payer"`, and absence from positive-rank results.

- **AC4: PASS (with spec-text discrepancy noted below)** — All 13 clinical capability mappings are implemented in `engine.py:compute_hard_exclusions`:
  1. `accepts_trach` (line 209)
  2. `accepts_vent` (line 218)
  3. `accepts_hd` (line 231)
  4. `in_house_hemodialysis` dual-check (lines 239-248) — triggered when `assessment.accepts_hd=True AND assessment.in_house_hemodialysis=True` but `capabilities.in_house_hemodialysis=False`
  5. `accepts_peritoneal_dialysis` (line 251)
  6. `accepts_wound_vac` (line 262)
  7. `accepts_oxygen_therapy` (line 271)
  8. `accepts_memory_care` (line 282)
  9. `accepts_bariatric` (line 293)
  10. `accepts_iv_antibiotics` (line 302)
  11. `accepts_tpn` (line 313)
  12. `accepts_isolation_cases` (line 322)
  13. `accepts_behavioral_complexity` (line 333)

  Tests: `test_clinical_hard_exclusion_mapping` parametrizes all 12 direct-flag mappings; `test_dialysis_hd_dual_check_accepts_hd_missing` and `test_dialysis_hd_dual_check_in_house_missing` cover the 13th compound check.

  **Spec-text discrepancy (non-blocking):** The spec constraint (line 164) and AC4 test description name the triggering assessment field `in_house_hd_required`, but the ORM model (`core/models/clinical_assessment.py:38`) and the actual DB column (alembic migration 0004) use `in_house_hemodialysis`. The engine correctly reads `assessment.in_house_hemodialysis` (engine.py line 229) which matches the live ORM field. The spec text was not updated after migration 0004 renamed the column. The behavior is correct; the spec text is stale.

- **AC5: PASS (with test quality defect noted)** — `engine.py:rank_matches` (lines 692-765) places all excluded items at `rank_order=-1` with `overall_score=0.0` and all scored items at positive rank. `service.py:get_matches` (lines 500-515) uses a custom SQL CASE expression to sort `rank_order=-1` last. `test_excluded_facilities_only_have_negative_rank` verifies that excluded facilities only appear at `rank_order==-1` and no excluded `facility_id` appears in the positive-rank set.

  **Test quality defect:** `test_generate.py:507` reads `assert float(m.overall_score) > 0.0 or True`. The `or True` renders this assertion vacuously true — it can never fail regardless of the actual score. This means the sub-assertion that "all ranked matches have positive overall_score" is untested. This is a test quality issue, not a logic defect (the engine itself enforces non-zero scores for scored facilities), but the Builder should remove `or True` from this assertion.

- **AC6: PASS** — Weights are defined at engine.py lines 52-56 as `_W_PAYER=0.35, _W_CLINICAL=0.30, _W_LEVEL_OF_CARE=0.20, _W_GEOGRAPHY=0.10, _W_PREFERENCE=0.05`. A compile-time `assert` at lines 59-61 verifies sum==1.0 within 1e-9 tolerance. The weighted formula is applied at engine.py lines 605-611. `test_weights_sum_to_one` and `test_overall_score_formula` verify both the sum and the formula.

- **AC7: PASS** — `engine.py:compute_level_of_care_score` (lines 358-397) uses `_LOC_ORDER={"snf":0,"irf":1,"ltach":2}` and `_LOC_SCORE={0:1.0, 1:0.7, 2:0.4}` with step_distance ≥ 3 returning 0.0. The function iterates all LOCs the facility accepts and returns the best score. `test_level_of_care_adjacency` parametrizes all exact-match, one-step, two-step, and no-match cases including irf→ltach (1 step), snf→ltach (2 steps), and ltach→snf (2 steps).

- **AC8: PASS** — `engine.py:compute_payer_fit_score` (lines 418-449) returns 1.0 for `accepted`, 0.5 for `conditional`, 0.5 for no-rule-found, 0.0 for `not_accepted` (defensive fallback; hard exclusion gate fires first). `test_payer_scoring_three_statuses` seeds three facilities at accepted/conditional/not_accepted and asserts `payer_fit_score==1.0`, `payer_fit_score==0.5`, and hard-excluded with `payer_fit_score is None` respectively.

- **AC9: PASS** — `engine.py:compute_geography_score` (lines 501-542) returns 0.0 when any coordinate is None (lines 520-523) without raising; uses haversine step function (≤10mi→1.0, ≤25mi→0.7, ≤50mi→0.4, >50mi→0.1). `engine.py:build_scoring_context` (lines 773-802) resolves ZIP via `zip_to_latlon` with `@lru_cache(maxsize=4096)`. Tests: `test_geography_score_null_patient_zip`, `test_geography_score_null_facility_coords`, `test_geography_step_function` (parametrized at ~5mi, ~15mi, ~35mi, ~75mi from Detroit), and `test_null_patient_zip_gives_zero_geography_no_exclusion`.

- **AC10: PASS** — `FacilityMatchResponse` schema (schemas.py lines 78-83) exposes all five component scores as separate nullable float fields. Service inserts them as individual columns at service.py lines 389-392. `test_all_component_scores_stored` asserts all five scores are non-null on non-excluded matches.

- **AC11: PASS** — `engine.py:generate_explanation_text` (lines 628-684) is called once per match in `engine.py:rank_matches` (lines 722 and 743) at write time. The service inserts the result verbatim into `FacilityMatch.explanation_text` (service.py line 395). `get_matches` returns the stored DB field unchanged — no regeneration on read. `test_explanation_text_stored_verbatim_not_regenerated` captures the DB text, GETs matches, confirms identity, then mutates a capability and GETs again without re-generating to confirm the text is unchanged.

- **AC12: PASS** — `engine.py:rank_matches` (line 718) sets `is_recommended = rank_idx <= 3`, which means exactly the top 3 ranked facilities (or all if < 3) receive True. `test_is_recommended_top_3` seeds 10 facilities and asserts exactly 3 recommended, with the highest scores. `test_is_recommended_fewer_than_3_facilities` asserts both facilities are recommended when only 2 exist.

- **AC13: PASS** — `service.py:get_matches` (lines 460-516) identifies the latest `generated_at` via a descending-ordered single-row query (lines 482-488), then retrieves all matches for that timestamp with the custom rank_order ordering (lines 500-515). `test_get_matches_returns_latest_generation` runs two generate calls, GETs matches, and asserts `generated_at` belongs to the second run and all component scores + rank + is_recommended + explanation_text are non-null on non-excluded results. `test_get_matches_ordering_excluded_at_bottom` verifies excluded facilities appear after all positive-rank facilities in the GET response.

- **AC14: PASS** — `service.py:toggle_select` (lines 524-609) toggles `selected_for_outreach`, writes an `AuditEvent`, and publishes a `CaseActivityEvent` on every toggle. Multiple facilities can be selected simultaneously (each is an independent toggle). `test_select_toggles_facility` exercises the full scenario: select A → True, select B → True, verify both True simultaneously, re-select A → False, verify B still True. `test_select_writes_audit_event` asserts audit events for both select and deselect transitions.

- **AC15: PASS** — `service.py:generate_matches` (lines 376-401) uses `session.add(match)` only — no DELETE statement anywhere in service.py or engine.py. `selected_for_outreach=False` is hardcoded at service.py line 394 for all new matches. `test_rescore_inserts_new_rows_does_not_delete_old` generates twice, queries all FacilityMatch rows, asserts total >= first + second runs, asserts new rows have `selected_for_outreach=False`, and asserts the first-run row still exists with its original `selected_for_outreach=True`.

- **AC16: PASS** — Router (router.py lines 56-59 and lines 141-144) applies `require_role("clinical_reviewer", "placement_coordinator", "admin")` and `require_write_permission` as FastAPI dependencies on both POST generate and PATCH select. GET matches has no role restriction. `test_generate_403_intake_staff`, `test_generate_403_readonly`, `test_patch_select_403_intake_staff_http`, `test_patch_select_403_readonly_http` exercise HTTP-level enforcement. Note: the service layer itself does not enforce roles — this is by design (role enforcement delegated to router dependencies) but means direct service calls bypass RBAC. This matches the architecture of other completed nodes.

- **AC17: PASS** — `service.py:_load_facility_preferences` (lines 226-260) loads FacilityPreference rows scoped to org facilities, filtering to `scope="global"` and `scope="hospital"` with matching `scope_reference_id`. `engine.py:compute_preference_score` (lines 545-559) returns 1.0 if facility_id matches any preference, else 0.0. `test_preference_score_higher_for_preferred_facility` seeds a hospital-scoped preference and asserts preferred facility gets `preference_score==1.0` vs `0.0`. `test_global_preference_applies_across_cases` verifies global scope applies even when case has no hospital.

---

### Constraints

- **"Hard exclusions are binary gates. An excluded facility must never receive a non-zero overall_score and must never appear in the ranked (non-excluded) portion of results"**: ENFORCED — `engine.py:rank_matches` explicitly sets `overall_score=0.0` for all excluded items (line 755). The compute path is bifurcated in `service.py` (lines 359-371): excluded facilities skip `compute_component_scores` entirely and receive no non-zero score. No code path between hard-exclusion and INSERT assigns a positive score to an excluded facility.

- **"All scoring must be framed as decision support... explanation_text must include language such as 'suggested' or 'recommended for review' rather than 'approved' or 'selected'"**: ENFORCED — `engine.py:generate_explanation_text` (lines 669-683) uses "strongly recommended for consideration", "suggested for review", and "included in the options for coordinator review". The hardcoded footer (line 682-683) reads "This scoring is provided as decision support for human coordinators only and requires clinical judgment before any facility contact is initiated." Tests `test_generate_explanation_text_excluded` and `test_generate_explanation_text_scored` assert absence of "approved", "placed", "selected", "determined" and presence of compliant phrases.

- **"The haversine library (MIT license) must be used for distance calculation. Facility coordinates from the Facility model (lat/lng) are the authoritative distance input."**: ENFORCED — `engine.py` imports `from haversine import haversine, Unit` (line 42). `compute_component_scores` passes `facility.latitude` and `facility.longitude` (lines 596-597) as the coordinate inputs.

- **"The zipcodes library (MIT license) must be used for ZIP→lat/lng resolution with @lru_cache on the lookup function"**: ENFORCED — `engine.py` imports `import zipcodes` (line 44); `zip_to_latlon` decorated with `@functools.lru_cache(maxsize=4096)` (lines 134-157).

- **"geography_score=0.0 is never a hard exclusion. A facility with unknown distance is still eligible for placement."**: ENFORCED — `compute_geography_score` returns 0.0 on any null coordinate (lines 520-523) without appending to any exclusion list. Null-coord facilities proceed through scoring normally. `test_null_patient_zip_gives_zero_geography_no_exclusion` explicitly verifies all 3 facilities remain non-excluded with geography_score=0.0.

- **"Explanation text must be generated once at match write time and stored verbatim in FacilityMatch.explanation_text. It must never be dynamically regenerated on GET requests."**: ENFORCED — `generate_explanation_text` is called only inside `rank_matches` (the write path). `get_matches` executes a SELECT and returns ORM objects directly without calling any generation function.

- **"Re-scoring must not overwrite or delete old FacilityMatch rows. New rows are inserted with the current generated_at timestamp."**: ENFORCED — No DELETE statement exists anywhere in `service.py` or `engine.py`. Each call to `generate_matches` generates a fresh `generated_at = datetime.now(timezone.utc)` (service.py line 334) and inserts all new rows via `session.add()`.

- **"selected_for_outreach must not be carried forward from a previous match generation run. All new FacilityMatch rows start with selected_for_outreach=false."**: ENFORCED — `service.py:generate_matches` line 394 hardcodes `selected_for_outreach=False` for every new FacilityMatch. No code reads prior `selected_for_outreach` values during INSERT.

- **"All PatientCase status transitions must be delegated to core-infrastructure's shared status-transition handler."**: ENFORCED — `service.py` imports `from placementops.core.state_machine import transition_case_status` (line 57) and calls it at lines 426-434. The case is never updated directly via ORM attribute assignment.

- **"organization_id tenant isolation enforced on every facility read and every FacilityMatch read/write."**: ENFORCED — `_load_active_facilities` filters by `Facility.organization_id == str(organization_id)` (service.py line 185). `_get_case_scoped` filters by `PatientCase.organization_id == str(organization_id)` (service.py line 93), and this is called at the top of all three public service functions. `_load_facility_preferences` uses a subquery scoped to org facility IDs (service.py lines 242-244). FacilityMatch reads are scoped via case ownership (verified by `_get_case_scoped` on the parent case).

- **"dialysis_type=hd with in_house_hd_required=true requires BOTH accepts_hd=true AND in_house_hemodialysis=true; failing either flag is a hard exclusion."**: ENFORCED — `engine.py` lines 228-248 implement the dual check. `assessment_hd = getattr(assessment, "accepts_hd", False)` and `assessment_in_house_hd = getattr(assessment, "in_house_hemodialysis", False)`. Failing `accepts_hd` appends blocker for `accepts_hd`; independently, failing `in_house_hemodialysis` appends a second blocker for `in_house_hemodialysis`. Note: the spec constraint text calls the assessment field `in_house_hd_required` but the actual ORM column was renamed to `in_house_hemodialysis` by alembic migration 0004. The engine reads the correct live field name.

---

### Interfaces

- **core-infrastructure (outbound):** PASS — Status transition delegated to `transition_case_status` (service.py line 57, called at lines 426-434). `AuditEvent` rows written for `matches_generated` (service.py lines 407-421) and for `facility_selected`/`facility_deselected` (service.py lines 570-579). `CaseActivityEvent` published via `publish_case_activity_event` (service.py line 599) on every `selected_for_outreach` toggle. All three contract obligations fulfilled.

- **auth-module (inbound):** PASS — Router reads JWT claims via `get_auth_context` dependency (router.py lines 65, 107, 148). `require_role("clinical_reviewer", "placement_coordinator", "admin")` enforced on POST generate and PATCH select (router.py lines 57-58, 141-142). `auth_ctx.organization_id` used for tenant isolation in all service functions. `auth_ctx.user_id` recorded in all audit events and the state machine call.

- **clinical-module (inbound):** PASS — `_resolve_assessment` queries `ClinicalAssessment` filtered by `patient_case_id` and `review_status=="finalized"`, ordered by `created_at DESC` (service.py lines 148-158). All 20+ clinical boolean fields are read via `getattr` in both `compute_hard_exclusions` and `compute_clinical_fit_score`. `recommended_level_of_care` read via `build_scoring_context` (engine.py line 800).

- **facilities-module (inbound):** PASS — `_load_active_facilities` reads Facility with `active_status=True` and `organization_id` scoping (service.py lines 182-190). `_load_capabilities_map` reads `FacilityCapabilities` (service.py lines 193-205). `_load_insurance_rules_map` reads `FacilityInsuranceRule` (service.py lines 208-223). `_load_facility_preferences` reads `FacilityPreference` (service.py lines 226-260). `facility.latitude` and `facility.longitude` passed to haversine (engine.py lines 596-597).

- **outreach-module (outbound):** PASS — `selected_for_outreach` flag on `FacilityMatch` is owned by `toggle_select` (service.py line 565). The PATCH endpoint is the only write path for this flag. New match rows always start at `False` (service.py line 394). The contract is a clean ownership boundary: matching-module writes, outreach-module reads.

---

### Pattern Consistency

- **File organization:** Consistent with other completed nodes (auth-module, clinical-module). Four source files (`__init__.py`, `engine.py`, `service.py`, `router.py`, `schemas.py`) with a `tests/` subdirectory containing `conftest.py` plus three test modules organized by concern.

- **Naming conventions:** `generate_matches`, `get_matches`, `toggle_select` match FastAPI service-layer naming seen in other nodes. Route path `/api/v1/cases/{case_id}/matches/...` is consistent with the resource-scoped URL convention.

- **Auth pattern:** `require_role(...)` dependency applied at router level, `AuthContext` passed through to service, consistent with auth-module and clinical-module patterns.

- **ORM pattern:** Async SQLAlchemy with `session.execute(select(...))` + `scalar_one_or_none()`, `session.add()`, `session.flush()`, `session.commit()` — consistent with other nodes.

- **`@functools.lru_cache`:** Applied at module level as a top-level decorated function (engine.py line 134), which is the correct usage pattern. The cache is shared across the process lifetime, appropriate for read-only ZIP lookups that do not change at runtime.

- **Dataclasses for pure data:** `ScoringContext`, `ComponentScores`, `BlockerDetail`, `HardExclusionResult` are plain `@dataclass` objects with no ORM dependency, enabling clean unit testing without a DB session. This is a sound separation of concerns.

---

### Anchor Comments

All source files have `# @forgeplan-node: matching-module` at the top:

- `engine.py` line 1: present
- `service.py` line 1: present
- `router.py` line 1: present
- `schemas.py` line 1: present
- `__init__.py` line 1: present
- `tests/__init__.py`: not read but empty (no functions requiring annotation)
- `tests/conftest.py` line 1: present
- `tests/test_scoring.py` line 1: present
- `tests/test_generate.py` line 1: present
- `tests/test_select.py` line 1: present

Major functions have `# @forgeplan-spec` annotations:

- `engine.py`: `zip_to_latlon` (AC9 at line 144), `compute_hard_exclusions` (AC3, AC4 at lines 183-184), `compute_level_of_care_score` (AC7 at line 372), `compute_payer_fit_score` (AC8 at line 434), `compute_clinical_fit_score` (AC6 at line 465), `compute_geography_score` (AC9 at line 518), `compute_preference_score` (AC17 at line 554), `compute_component_scores` (AC6 at line 577), `generate_explanation_text` (AC11 at line 643), `rank_matches` (AC5, AC12 at lines 705-706)
- `service.py`: `_resolve_assessment` (AC1 at line 121), `_load_active_facilities` (AC2 at line 181), `_load_facility_preferences` (AC17 at line 240), `generate_matches` (AC2, AC15 at lines 293-294), `get_matches` (AC13 at line 474), `toggle_select` (AC14 at line 540)
- `router.py`: endpoint functions annotated at lines 49-51, 98, 135-136
- `schemas.py`: `FacilityMatchResponse` (AC10, AC11 at lines 71-72), `SelectToggleResponse` (AC14 at line 110)

Coverage: comprehensive. No source files or major functions are missing annotations.

---

### Non-Goals

- **"This module does not send outreach communications."**: CLEAN — No outreach delivery, email, or SMS code exists. The module's boundary is the `selected_for_outreach` flag and `CaseActivityEvent` publication, which is the defined boundary.

- **"This module does not create or edit ClinicalAssessment records."**: CLEAN — `service.py` and `engine.py` only `SELECT` from `clinical_assessments`. No INSERT, UPDATE, or DELETE on that table.

- **"This module does not manage Facility or FacilityCapabilities records."**: CLEAN — All facility data access is read-only. No CREATE, UPDATE, or DELETE on `facilities` or `facility_capabilities` tables.

- **"This module does not perform AI or LLM-based scoring."**: CLEAN — All scoring is deterministic arithmetic. No calls to any AI/LLM library or service. `generated_by="rules_engine"` (service.py line 397) is accurate.

- **"This module does not record placement outcomes."**: CLEAN — No references to outcome models or tables.

- **"This module does not generate analytics reports or aggregations."**: CLEAN — No aggregate queries or reporting functions.

---

### Failure Modes

- **"A missing null-check for patient_zip causes a zipcodes lookup to raise an exception instead of returning geography_score=0.0"**: HANDLED — `zip_to_latlon` (engine.py lines 145-146) returns None when `not zip_code or not zip_code.strip()`. `build_scoring_context` (engine.py lines 787-790) only calls `zip_to_latlon` when `patient_zip` is truthy. `compute_geography_score` returns 0.0 when `patient_lat is None` (line 520). The exception is also caught inside `zip_to_latlon` via bare `except Exception` (line 155).

- **"The payer not_accepted exclusion check is implemented as a low score (0.0) rather than a hard gate"**: HANDLED — `compute_hard_exclusions` fires before `compute_component_scores` in the service pipeline (service.py lines 352-371). Excluded facilities are placed in `excluded_items` and never enter `scored_items`. `rank_matches` keeps the two lists completely separate. A `not_accepted` facility can never receive a positive `payer_fit_score` through the main code path.

- **"explanation_text is generated dynamically on GET instead of stored at write time"**: HANDLED — `get_matches` (service.py lines 460-516) executes a single SELECT and returns ORM objects directly. `generate_explanation_text` is not called anywhere in the GET path.

- **"Re-scoring deletes old FacilityMatch rows before inserting new ones"**: HANDLED — No DELETE statement exists in service.py or engine.py. Only `session.add()` is used for FacilityMatch (service.py lines 400-401).

- **"The dialysis_type=hd hard-exclusion check tests only accepts_hd and ignores in_house_hemodialysis when in_house_hd_required=true"**: HANDLED — `engine.py` lines 239-248 explicitly perform the second check. Two separate `BlockerDetail` entries are appended for failing either flag independently.

- **"selected_for_outreach values from a previous match run are copied into new FacilityMatch rows"**: HANDLED — `service.py:generate_matches` line 394 hardcodes `selected_for_outreach=False`. The pipeline never reads prior match rows during INSERT.

- **"The weighted sum formula applies weights that do not sum to 1.0"**: HANDLED — Compile-time `assert` at engine.py lines 59-61 will crash the import if weights drift. The current weights sum exactly to 1.0 (0.35+0.30+0.20+0.10+0.05=1.00).

- **"Tenant isolation is omitted from the facility retrieval query"**: HANDLED — `_load_active_facilities` (service.py line 185) includes `Facility.organization_id == str(organization_id)`. The `organization_id` originates from `auth_ctx.organization_id` extracted from the verified JWT.

- **"The re-score warning is enforced only on the frontend with no server-side acknowledgement token, allowing a direct API call to silently clear selections"**: UNHANDLED — The `POST .../matches/generate` endpoint accepts no acknowledgement token or confirmation flag in `MatchGenerateRequest` (schemas.py lines 36-51, which has only `assessment_id`). A caller can POST directly to the API without any confirmation, and their previously selected facilities will not be cleared (they remain in old rows) but the coordinator will be viewing the new match set with no selections. The spec identifies this as a failure mode and there is no server-side guard. Note: the spec's failure mode description says "silently clearing selections" — technically old rows are preserved (AC15) so selections are not destroyed, but the new match set has no selections and the coordinator has no server-side prompt. The failure mode as stated in the spec is partially mitigated by the insert-not-delete behavior, but there is still no acknowledgement token.

---

### Additional Finding: AC5 Test Defect

**Location:** `tests/test_generate.py:507`

```python
assert float(m.overall_score) > 0.0 or True  # Some may have 0 if no scoring data but rank > 0
```

The `or True` makes this assertion vacuously true and can never fail. The intent (verifying ranked matches have positive scores) is not tested. While the engine logic itself is correct, this is a dead assertion. The Builder should either remove `or True` or justify in the spec why a ranked facility could have `overall_score==0.0`.

---

### Recommendation: REQUEST CHANGES (2 failures: [FM-rescore-warning, AC5-test-defect])

**Summary of failures:**

1. **FM-rescore-warning (UNHANDLED failure mode):** The spec failure mode at line 183 explicitly calls out the absence of a server-side acknowledgement token on the re-score endpoint. No such token exists in `MatchGenerateRequest` or the router. While existing FacilityMatch data is preserved by the insert-not-delete behavior, the spec names this as a required guard. The Builder should either implement a confirmation flag (e.g., `confirm_rescore: bool = False` that returns a 409 if existing matches are present and the flag is absent/False) or get the spec updated to explicitly designate this as a frontend-only concern (which the current spec does not do — it calls it a failure mode).

2. **AC5-test-defect (vacuous assertion):** `tests/test_generate.py:507` contains `assert float(m.overall_score) > 0.0 or True` which cannot fail. This leaves the AC5 invariant "ranked matches have positive scores" untested. The Builder should remove `or True`.

**Non-blocking findings that should be addressed in a follow-up spec update:**

- The spec constraint text (line 164) and AC4 test description use `in_house_hd_required` as the assessment field name, but the ORM column is `in_house_hemodialysis` (renamed by migration 0004). The spec should be updated to reflect the live field name to prevent future Builder confusion.
