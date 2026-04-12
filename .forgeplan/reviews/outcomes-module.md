## Review: outcomes-module
**Date:** 2026-04-11T00:00:00Z
**Reviewer:** Claude Sonnet 4.6
**Review type:** native
**Cycle:** 1

---

### Acceptance Criteria

- **AC1: FAIL** — Role gate partially incorrect. The spec requires that `manager` role receives 403 on POST outcomes (spec: "intake_staff, clinical_reviewer, manager, or read_only returns 403"). However, `router.py:45` defines `_TRANSITION_ROLES = ("placement_coordinator", "admin", "manager")` and `router.py:191-194` allows `manager` to call the status-transition endpoint at the router level. This is correct for closure. The outcomes endpoint `_OUTCOMES_ROLES = ("placement_coordinator", "admin")` at `router.py:41` correctly excludes manager from `POST /outcomes`. However, no test exists for `manager` receiving 403 on POST outcomes (the test suite at `test_outcomes.py:49-143` tests intake_staff, clinical_reviewer, read_only — but not manager). The test coverage gap means the role boundary for `manager` on POST outcomes is untested and the spec requirement is only partially verified.

- **AC2: PASS** — `service.py:131-166` (`_validate_sent_outreach`) correctly queries `OutreachAction.approval_status == "sent"` for the given `facility_id` and `patient_case_id`, raising HTTP 400 with `error: "no_sent_outreach"` when absent. Tests `test_ac2_accepted_with_sent_outreach_returns_201`, `test_ac2_accepted_without_sent_outreach_returns_400`, and `test_ac2_accepted_no_outreach_at_all_returns_400` all present and correct.

- **AC3: FAIL** — Spec states "AuditEvent written with entity_type=patient_case". Implementation writes `entity_type="placement_outcome"` (`service.py:310`). This is a direct spec-vs-implementation mismatch. The test at `test_outcomes.py:256-263` also queries for `entity_type == "placement_outcome"`, so both test and implementation diverge from the spec. The test for AC3 does verify a status advance to `accepted` and a PlacementOutcome row, which are correct. The case_activity_event is described in the spec output contract as part of AC3; the implementation relies on `transition_case_status` publishing a `CaseActivityEvent` to an in-process event bus (ephemeral), and the spec's CaseActivityEvent with `event_type=outcome_recorded` is not separately written — `transition_case_status` uses `event_type="status_changed"`. The event_type mismatch (`status_changed` vs `outcome_recorded`) is a secondary discrepancy in the spec test description for AC3.

- **AC4: PASS** — Schema validator at `schemas.py:74-81` enforces `facility_id` required for `declined` and `decline_reason_code` required for `declined`, returning 422 on schema violations. Service validates sent outreach at `service.py:285-286` and decline reason code at `service.py:289-291`. Tests cover null facility (422), no sent outreach (400), invalid reason code (400), missing reason code (422), and valid full payload (201). One note: the service guard at `service.py:285` reads `if payload.outcome_type in _FACILITY_REQUIRED_TYPES and payload.facility_id is not None` — the second condition (`is not None`) is redundant given schema enforcement, but is not a defect since schemas run first.

- **AC5: PASS** — `_OUTCOME_STATUS_MAP` at `service.py:75-81` maps `declined` → `declined_retry_needed`. `transition_case_status` is called at `service.py:336-344` with `to_status="declined_retry_needed"`. Test `test_ac5_declined_advances_case_and_writes_records` verifies `case.current_status == "declined_retry_needed"`, PlacementOutcome row with reason fields, and AuditEvent.

- **AC6: PASS** — State machine allowlist at `state_machine.py:86` includes `"accepted": {"declined_retry_needed": ["placement_coordinator", "admin"]}`. The declined outcome handler at `service.py:332-344` delegates to `transition_case_status`, which enforces this allowlist. Test `test_ac6_rescinded_acceptance_advances_to_declined_retry_needed` seeds case at `accepted`, posts declined outcome, and verifies `case.current_status == "declined_retry_needed"`.

- **AC7: PASS** — `_OUTCOME_STATUS_MAP` at `service.py:79-80` maps `family_declined` and `withdrawn` to `None`. The branch at `service.py:344-348` issues `session.commit()` without calling `transition_case_status`, so no status advance occurs. Schema at `schemas.py:74-78` only requires `facility_id` for `accepted/declined/placed`, leaving it nullable for `family_declined/withdrawn`. Tests `test_ac7_family_declined_null_facility_returns_201` and `test_ac7_withdrawn_null_facility_returns_201` verify 201 and that `case.current_status` remains unchanged.

- **AC8: PASS** — `_CANCELABLE_OUTREACH_STATES = ["draft", "pending_approval", "approved"]` at `service.py:72` matches the spec's requirement exactly (not sent, not failed). `_auto_cancel_open_outreach` at `service.py:199-239` uses `OutreachAction.approval_status.in_(_CANCELABLE_OUTREACH_STATES)` as the filter, ensuring `sent` records are untouched. Called only for `_AUTO_CANCEL_TYPES = {"accepted", "placed"}` at `service.py:324-325`. Flush-before-commit atomicity at `service.py:329` followed by `transition_case_status` commit ensures atomic execution. Test `test_ac8_accepted_auto_cancels_draft_and_approved_not_sent` verifies all three cancelable states are set to `canceled` and one sent action remains `sent`.

- **AC9: PASS** — `status_transition` service function at `service.py:440-512` delegates to `transition_case_status`. State machine allowlist at `state_machine.py:87-90` permits `declined_retry_needed → ready_for_matching` and `declined_retry_needed → outreach_pending_approval` for `placement_coordinator` and `admin`. Router at `router.py:45` includes `manager` in `_TRANSITION_ROLES` (permissible since the state machine then enforces the role gate). Tests `test_ac9_retry_to_ready_for_matching_returns_200`, `test_ac9_retry_to_outreach_pending_approval_returns_200`, `test_ac9_intake_staff_retry_returns_403`, and `test_ac9_admin_retry_returns_200` cover the full matrix.

- **AC10: PASS** — `_OUTCOME_STATUS_MAP["placed"] = "placed"` at `service.py:78`. `_AUTO_CANCEL_TYPES` includes `"placed"` at `service.py:69`. Test `test_ac10_placed_advances_case_and_auto_cancels` verifies case advances to `placed`, PlacementOutcome written with `facility_id`, and draft outreach is canceled.

- **AC11: PASS** — Closure guard at `service.py:465-483` checks `payload.to_status == "closed"`, then validates non-empty `transition_reason` (HTTP 400) and `auth_ctx.role_key not in _CLOSURE_ROLES` (HTTP 403). `_CLOSURE_ROLES = {"manager", "admin"}` at `service.py:84`. Full test matrix in `test_timeline.py:349-480`: no reason → 400, empty reason → 400, coordinator → 403, manager with reason → 200, admin with reason → 200, and the integrated AC7+AC11 path for `family_declined` followed by manager closure.

- **AC12: PARTIAL FAIL** — `GET /timeline` endpoint returns `CaseStatusHistory` rows (`service.py:397-437`) ordered by `entered_at` ascending, which satisfies chronological ordering. However, the spec states "events from all modules (intake, clinical, outreach, outcomes) are included." The implementation only reads `CaseStatusHistory`, which captures status-change events written by `transition_case_status`. Non-status-change events from intake, outreach, etc. that do not produce a status transition are not represented. More critically, the spec's `CaseActivityEvent` model includes `event_type: string` per the data model — the implementation hardcodes `event_type="status_changed"` for every entry (`router.py:173`), but the spec's AC3 test specifies `event_type=outcome_recorded`. An `outcome_recorded` event type is never present in the timeline. This is a partial coverage gap against the spec's intent for the timeline to be a multi-event feed.

- **AC13: PASS** — `get_outcomes` at `service.py:362-394` queries `PlacementOutcome` ordered by `created_at`, scoped through case ownership check. Router at `router.py:108-134` returns `OutcomeHistoryResponse` with `items` and `total`. Tenant isolation tested at `test_ac13_outcome_history_tenant_isolation`.

- **AC14: FAIL** — Spec states: "After recording each outcome_type (accepted, declined, placed, family_declined, withdrawn), query audit_events where entity_type=patient_case and entity_id=case_id." The implementation writes `entity_type="placement_outcome"` with `entity_id=outcome.id` (the placement outcome's UUID, not the case UUID) at `service.py:308-319`. This means querying `entity_type=patient_case` and `entity_id=case_id` would return zero results for the outcome audit. The separate AuditEvent written by `transition_case_status` (state_machine.py:189-197) uses `entity_type="patient_case"` and `entity_id=case_id`, but that only fires for accepted/declined/placed — not for family_declined/withdrawn. Additionally, `test_ac14_all_outcome_types_produce_audit_event` at `test_outcomes.py:686-721` only exercises `family_declined` and `withdrawn` (the parametrize list at lines 697-700 omits `accepted`, `declined`, and `placed`), so audit coverage for three of the five outcome types is not tested end-to-end in the AC14-specific test (though individual AC3, AC5, and AC10 tests do check audit presence indirectly).

- **AC15: PASS** — `_get_case` at `service.py:108-128` raises `HTTP 409` when `case.current_status == "closed"`. Test `test_ac15_closed_case_returns_409` seeds a closed case and verifies 409.

- **AC16: PASS** — `_validate_decline_reason_code` at `service.py:169-196` queries `DeclineReasonReference` by code and raises HTTP 400 with `error: "invalid_decline_reason_code"` for unknown codes. Parametrized test `test_ac16_valid_seed_codes_return_201` covers all four required codes (`bed_no_longer_available`, `insurance_issue_post_acceptance`, `clinical_criteria_not_met`, `no_response`). Test `test_ac16_unlisted_code_returns_400` verifies rejection.

---

### Constraints

- **"All outcomes MUST write an AuditEvent regardless of outcome_type": VIOLATED** — `service.py:307-319` does unconditionally call `emit_audit_event` for all five outcome types, satisfying the unconditional write requirement. However, the `entity_type` is `"placement_outcome"` rather than the spec-expected `entity_type=patient_case` (AC3/AC14). The constraint is satisfied in intent (an AuditEvent is always written) but the entity_type does not match what the spec tests prescribe, making the audit un-queryable by the pattern specified in AC14. Verdict: PARTIALLY VIOLATED — AuditEvent is always written but does not conform to the queryable spec pattern.

- **"facility_id MUST be validated against OutreachAction.approval_status=sent for the same case before recording accepted or declined outcomes": ENFORCED** — `service.py:284-286` with `_validate_sent_outreach` called for `_FACILITY_REQUIRED_TYPES` (accepted, declined, placed). Note: guard condition `and payload.facility_id is not None` is redundant due to schema enforcement but not harmful.

- **"facility_id MUST be null-permitted for family_declined and withdrawn": ENFORCED** — `schemas.py:74-78` requires facility_id only for `{accepted, declined, placed}`; the `family_declined` and `withdrawn` types are not in that set.

- **"Auto-cancel MUST execute in the same database transaction as the case status advance to accepted or placed": ENFORCED** — `service.py:325,329,336-344`: `_auto_cancel_open_outreach` adds updates to the session, then `session.flush()` sends them to the DB within the same transaction, then `transition_case_status` commits all in one atomic commit.

- **"sent OutreachAction records MUST NOT be canceled by the auto-cancel logic": ENFORCED** — `_CANCELABLE_OUTREACH_STATES = ["draft", "pending_approval", "approved"]` at `service.py:72` explicitly excludes `sent`. The filter at `service.py:220` uses `.in_(_CANCELABLE_OUTREACH_STATES)`, not a NOT IN on sent.

- **"Retry routing MUST be delegated to the core-infrastructure shared state-machine handler; this module MUST NOT write PatientCase.current_status directly": ENFORCED** — `service.py:502-510` calls `transition_case_status`. No direct `case.current_status = ...` assignment exists in the outcomes module (the only assignment is inside `state_machine.py:171` which is core-infrastructure).

- **"Case closure MUST require closure_reason text and MUST be restricted to manager or admin role": ENFORCED** — `service.py:465-483` checks both conditions before delegating to state machine.

- **"organization_id scoping MUST be applied to all queries": ENFORCED** — All case lookup queries include `PatientCase.organization_id == str(auth_ctx.organization_id)` (`service.py:111-115`, `service.py:377-381`, `service.py:413-417`, `service.py:486-490`). `CaseStatusHistory` query at `service.py:430-433` also adds `CaseStatusHistory.organization_id == str(auth_ctx.organization_id)`.

- **"decline_reason_code MUST be validated against the decline_reason_reference seed table": ENFORCED** — `service.py:180-182` queries `DeclineReasonReference.code == code` and raises 400 on no match.

---

### Interfaces

- **core-infrastructure (write):** PARTIAL FAIL — Writes PlacementOutcome and AuditEvent rows correctly. Delegates PatientCase status transitions to `transition_case_status` (never writes `current_status` directly). Auto-cancel executes in the same transaction. However, the `entity_type` on the AuditEvent written by the outcomes module is `"placement_outcome"` rather than `"patient_case"`, diverging from the spec's AC3 and AC14 test assertions which query by `entity_type=patient_case` and `entity_id=case_id`.

- **auth-module (read):** PASS — `router.py:27` imports `require_role` and `require_write_permission` from `placementops.modules.auth.dependencies`. Role enforcement at router layer for `_OUTCOMES_ROLES` and `_TRANSITION_ROLES`. Service layer further enforces `_CLOSURE_ROLES` for closure. `AuthContext` provides `role_key` throughout.

- **outreach-module (read):** PASS — Reads `OutreachAction` records for sent-outreach validation (`service.py:144-152`) and for auto-cancel (`service.py:216-223`). No writes to OutreachAction from this module beyond the `approval_status = "canceled"` mutation in `_auto_cancel_open_outreach`, which is the contractually permitted auto-cancel operation.

---

### Pattern Consistency

- Consistent with the outreach-module and matching-module patterns: in-memory SQLite for tests, `seed_*` helpers in conftest, `auth_headers()` + JWT approach, `AsyncClient` + `ASGITransport`, `@forgeplan-node` + `@forgeplan-spec` annotation style.
- `service.py` uses the same import structure and `_get_case` helper pattern seen in other modules.
- Return type from `post_status_transition` at `router.py:201` is `dict` with a manual `__dict__`-style serialization (`router.py:221-229`), whereas other POST endpoints return a typed response model. This is inconsistent with the `PlacementOutcomeResponse` pattern used on the same router, but is not a spec violation.
- `schemas.py` header annotation at line 2 references only `AC1` through `AC13`, omitting `AC14`, `AC15`, and `AC16` — minor annotation gap, not a functional defect.

---

### Anchor Comments

- `placementops/modules/outcomes/__init__.py`: Has `# @forgeplan-node: outcomes-module`. PASS.
- `placementops/modules/outcomes/service.py`: Has `# @forgeplan-node: outcomes-module` at line 1; `@forgeplan-spec` annotations on every major function and key code sections. PASS.
- `placementops/modules/outcomes/router.py`: Has `# @forgeplan-node: outcomes-module` at line 1; `@forgeplan-spec` annotations on every endpoint. PASS.
- `placementops/modules/outcomes/schemas.py`: Has `# @forgeplan-node: outcomes-module` at line 1; `@forgeplan-spec` annotations on validator. Line 2 omits AC14/AC15/AC16 from the header list — minor. PASS overall.
- `placementops/modules/outcomes/tests/conftest.py`: Has `# @forgeplan-node: outcomes-module`. PASS.
- `placementops/modules/outcomes/tests/test_outcomes.py`: Has `# @forgeplan-node: outcomes-module`. PASS.
- `placementops/modules/outcomes/tests/test_timeline.py`: Has `# @forgeplan-node: outcomes-module`. PASS.
- All source files have node annotations. Coverage is complete.

---

### Non-Goals

- **"Does not implement matching or outreach approval workflow":** CLEAN — No matching or outreach approval logic present.
- **"Does not own case timeline storage; reads case_activity_events written by all modules via core-infrastructure":** CLEAN — Timeline is read from `CaseStatusHistory` (written by `transition_case_status`). The module writes no `CaseStatusHistory` rows directly.
- **"Does not implement analytics or KPI aggregation":** CLEAN — No aggregation, breakdown, or rate computation found.
- **"Does not cancel sent outreach actions":** CLEAN — `_CANCELABLE_OUTREACH_STATES` explicitly excludes `sent`; filter confirmed correct.
- **"Does not implement manager queue views or SLA aging":** CLEAN — No queue views or SLA logic present.
- **"Does not perform family communication or notification":** CLEAN — No notification, email, or messaging calls found.

---

### Failure Modes

- **"Accepted outcome without sent outreach validation":** HANDLED — `_validate_sent_outreach` at `service.py:131-166` raises HTTP 400 if no `approval_status=sent` row exists for the facility+case combination.

- **"Non-atomic auto-cancel":** HANDLED — `_auto_cancel_open_outreach` returns without flushing (`service.py:214`); `session.flush()` at `service.py:329` sends all pending writes; `transition_case_status` commits at `state_machine.py:201`. Single atomic commit covers outcome row + audit + cancel updates + status change.

- **"Sent actions incorrectly auto-canceled":** HANDLED — Filter at `service.py:220` uses `.in_(["draft", "pending_approval", "approved"])`, not a `NOT IN ["sent"]` guard. The positive allowlist approach is safer against filter bugs.

- **"All outcomes not audited":** HANDLED — `emit_audit_event` at `service.py:307-319` is called unconditionally for every outcome type, outside any conditional block. However, the `entity_type` mismatch (`placement_outcome` vs `patient_case`) means the audit exists but may not satisfy HIPAA audit query patterns as specified in AC14.

- **"Declined outcome with null facility_id accepted":** HANDLED — Schema validator at `schemas.py:75-78` raises `ValueError` (→ 422) when `outcome_type == "declined"` and `facility_id is None`. Service does not execute.

- **"Rescinded acceptance skips declined_retry_needed":** HANDLED — State machine allowlist at `state_machine.py:84-86` includes `"accepted" → "declined_retry_needed"` for `placement_coordinator` and `admin`. The declined outcome path at `service.py:332-344` calls `transition_case_status` which validates this allowlist.

- **"family_declined advances to closed without manager confirmation":** HANDLED — `_OUTCOME_STATUS_MAP["family_declined"] = None` at `service.py:79`. The `to_status is None` branch at `service.py:345-348` commits only the outcome row without calling `transition_case_status`, leaving case status unchanged. Manager must call the status-transition endpoint separately.

---

### Summary of Failures

| ID | Dimension | Severity | Description |
|----|-----------|----------|-------------|
| F1 | AC3, AC14, Constraint | HIGH | `entity_type="placement_outcome"` with `entity_id=outcome.id` instead of spec-required `entity_type="patient_case"` / `entity_id=case_id`; makes AC14's query pattern return zero results for outcome audits on patient_case |
| F2 | AC14 | MEDIUM | `test_ac14_all_outcome_types_produce_audit_event` only parametrizes `family_declined` and `withdrawn`; `accepted`, `declined`, and `placed` audit coverage is absent from the AC14-specific test |
| F3 | AC1 | LOW | No test for `manager` role receiving 403 on POST `/outcomes`; spec explicitly lists manager as a blocked role |
| F4 | AC12 | LOW | Timeline `event_type` is hardcoded to `"status_changed"` for all entries; spec's AC3 test describes `event_type=outcome_recorded` in timeline; non-status-change outcome events are not surfaced in timeline |

---

### Recommendation: REQUEST CHANGES (4 failures: F1-entity_type-mismatch, F2-AC14-test-gap, F3-AC1-manager-test-gap, F4-AC12-event_type)

**Top 3 most critical findings:**

1. **F1 (HIGH) — AuditEvent entity_type/entity_id mismatch (AC3, AC14, Constraint):** `service.py:308-313` writes `entity_type="placement_outcome"` and `entity_id=UUID(outcome.id)`. The spec's AC3 test asserts `entity_type=patient_case` and the AC14 test asserts querying by `entity_type=patient_case, entity_id=case_id` returns one AuditEvent per outcome. The current implementation makes those spec queries return empty results. The `test_ac3` and `test_ac5` tests have already been written to query `entity_type="placement_outcome"` and will pass against the current code, but both the spec assertions and HIPAA audit query patterns are violated.

2. **F2 (MEDIUM) — AC14 test incomplete coverage:** `test_ac14_all_outcome_types_produce_audit_event` at `test_outcomes.py:686-721` only includes `family_declined` and `withdrawn` in the parametrize list (lines 697-700). The `accepted`, `declined`, and `placed` outcome types are absent from this consolidated audit coverage test. While separate AC3/AC5/AC10 tests verify audit presence for those types indirectly, the AC14-specific "all 5 types" test is structurally incomplete.

3. **F3/F4 (LOW) — AC1 manager role gap and AC12 event_type:** The `manager` role is listed in the spec as receiving 403 on POST `/outcomes`, but no test covers this. Separately, the timeline always emits `event_type="status_changed"` (`router.py:173`) whereas the spec's CaseActivityEvent model implies outcome events would appear with `event_type=outcome_recorded`; non-transition outcome events (family_declined/withdrawn) leave no timeline entry.
