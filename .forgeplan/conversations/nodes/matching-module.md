# matching-module Build Log

## Pre-Build Spec Challenge

### Ambiguities Resolved / Assumptions Documented

**1. ClinicalAssessment boolean flag naming:**
The spec's AC4 describes mappings like `trach→accepts_trach`, `vent→accepts_vent`. The actual ORM model (`ClinicalAssessment`) uses `accepts_trach`, `accepts_vent`, etc. — the same field names as `FacilityCapabilities`. No translation layer needed. Implementation uses direct attribute lookup by name.

**2. `dialysis_type` field absence:**
The spec mentions `dialysis_type=hd` but `ClinicalAssessment` has no `dialysis_type` field — it uses `accepts_hd` and `in_house_hemodialysis` booleans directly. The dual-check constraint (`accepts_hd AND in_house_hemodialysis` when `in_house_hd_required=True`) is implemented as: when `assessment.accepts_hd=True` AND `assessment.in_house_hemodialysis=True`, BOTH facility flags must be True.

**3. `facility_preferences` structure:**
`FacilityPreference` is in `placementops.modules.facilities.models` (not core models). It has `scope` (global/market/hospital) and `scope_reference_id`. Preference loading includes `scope=global` always, plus `scope=hospital` where `scope_reference_id=case.hospital_id` when hospital_id is present.

**4. `primary_payer` matching:**
`PatientCase.insurance_primary` is a free-text string. `FacilityInsuranceRule.payer_name` is also a string. Matching is case-insensitive by `payer_name` OR by `payer_id`. This handles the common case where the payer name matches exactly.

**5. `case_activity_events` for toggle_select:**
Spec says "writes case_activity_events on selected_for_outreach toggle". Implemented by calling `publish_case_activity_event` with event_type=`facility_selected` or `facility_deselected`.

**6. AuditEvent for match_generated:**
The spec says "writes AuditEvent rows for match generation". Implemented inline in `service.generate_matches`. When case advances via `transition_case_status` (first generation), the state machine writes its own AuditEvent for the status change. For re-scoring (already at `facility_options_generated`), a separate `matches_generated` AuditEvent is written.

**7. GET matches ordering with rank_order=-1:**
SQLite doesn't support `NULLS LAST` syntax. Used `sqlalchemy.case` expression to sort -1 values last: excluded rows (rank_order=-1) mapped to 99999, all others sort by actual rank_order ASC.

**8. Facilities without FacilityCapabilities rows:**
Not specified. Decision: skip with a warning log rather than crash. A facility with no capabilities row would fail all clinical exclusion checks anyway.

**9. `clinical_fit_score=0.0` when no clinical flags:**
Documented assumption: if no assessment boolean flags are True (patient has no special clinical needs), `clinical_fit_score=0.0`. This means all facilities tie on clinical fit, which is correct — no needs means no differentiation needed.

## Decisions

- `@forgeplan-decision: D-matching-1-haversine-step-function` — Haversine step function per spec, not continuous decay. Matches spec AC9 exactly.
- `@forgeplan-decision: D-matching-2-lru-cache-zip-lookup` — LRU cache on `zip_to_latlon` to avoid redundant zipcodes I/O per scoring run.
- `@forgeplan-decision: D-matching-3-insert-never-delete` — Re-scoring inserts new rows, never deletes. Preserves audit trail and satisfies AC15/constraint.

## Post-Build Fixes (2026-04-11)

**JSONB/SQLite compatibility patch:**
`SQLiteTypeCompiler` does not have `visit_JSONB`, causing `Base.metadata.create_all` to fail on SQLite test engines for any module that imports `OutreachTemplate`, `AuditEvent`, `FacilityMatch`, or `ImportJob` (all use `JSONB`). Fixed by adding a one-liner patch in `tests/conftest.py`:
```python
if not hasattr(SQLiteTypeCompiler, "visit_JSONB"):
    SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON
```
This patch affects DDL compilation only — SQLite stores JSON values as text, which is correct for in-memory tests.

**`generate_explanation_text` disclaimer wording:**
The original disclaimer used "automated placement determination" which was in the test's prohibited-phrases list (per nH Predict compliance constraint). Rewrote disclaimer to: "requires clinical judgment before any facility contact is initiated." — avoids all prohibited terms while preserving compliance intent.

**`test_explanation_text_stored_verbatim_not_regenerated` dead code:**
Removed stale `select(type(new_matches[0]).__class__)` call that was immediately overwritten by the correct `select(FacilityCapabilities).where(...)` query.

**Concern — `haversine` and `zipcodes` not in `requirements.txt`:**
Both packages are installed in the environment (`haversine==2.9.0`, `zipcodes==1.3.0`) but not listed in `requirements.txt` (outside `file_scope`). The sweep should add these two lines to `requirements.txt`:
```
haversine==2.9.0
zipcodes==1.3.0
```

**Concern — `main.py` not updated with matching router:**
`placementops/modules/matching/router.py` is created but `main.py` (outside `file_scope`) has not been updated to register it. Add:
```python
from placementops.modules.matching.router import router as matching_router
app.include_router(matching_router, prefix="/api/v1")
```

**Final test results:** 78/78 tests pass (42 scoring + 26 generate + 10 select).

## Files Created

- [2026-04-11T19:10:11.088Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/modules/matching/__init__.py`
- [2026-04-11T19:10:26.047Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/modules/matching/schemas.py`
- [2026-04-11T19:11:58.429Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/modules/matching/engine.py`
- [2026-04-11T19:13:08.090Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/modules/matching/service.py`
- [2026-04-11T19:13:28.974Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/modules/matching/router.py`
- [2026-04-11T19:13:40.911Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/modules/matching/tests/__init__.py`
- [2026-04-11T19:14:34.101Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/modules/matching/tests/conftest.py`
- [2026-04-11T19:15:54.392Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/modules/matching/tests/test_generate.py`
- [2026-04-11T19:17:24.132Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/modules/matching/tests/test_scoring.py`
- [2026-04-11T19:18:24.744Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/modules/matching/tests/test_select.py`
- [2026-04-11T19:19:18.491Z] Edited: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/.forgeplan/conversations/nodes/matching-module.md`
- [2026-04-11T19:19:27.044Z] Edited: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/.forgeplan/state.json`
- [2026-04-12T14:37:46.399Z] Edited: `placementops/modules/matching/engine.py`
- [2026-04-12T14:38:13.324Z] Edited: `placementops/modules/matching/tests/test_scoring.py`
- [2026-04-12T14:38:18.384Z] Created: `placementops/modules/matching/tests/test_scoring.py`
- [2026-04-12T20:44:41.047Z] Edited: `placementops/modules/matching/tests/test_generate.py`
- [2026-04-12T20:44:45.906Z] Created: `placementops/modules/matching/tests/test_generate.py`
- [2026-04-12T22:16:59.608Z] Created: `placementops/modules/matching/engine.py`
