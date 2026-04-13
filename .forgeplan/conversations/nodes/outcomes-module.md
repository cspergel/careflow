# outcomes-module — Build Log

## Pre-Build Spec Challenge

### Ambiguities Identified and Resolved

**A1: AC7 — family_declined/withdrawn case status advance**
The spec has conflicting language: "advance case toward closed (manager/admin must confirm via status-transition to close)" and "advance case to closed". The CRITICAL RULES section clarifies that recording family_declined/withdrawn does NOT change case status immediately. The outcome row is written, audit event written, case_activity_event published, but `current_status` is NOT changed. The manager later uses POST /status-transition to close.

*Assumption documented:* family_declined and withdrawn outcomes write the PlacementOutcome, AuditEvent, and case_activity_event but do NOT call `transition_case_status`. The case_activity_event event_type will be `"outcome_recorded"` with `new_status=None` for these types (since no status change occurs). This satisfies AC7's "manager/admin must confirm via status-transition."

**A2: Atomicity of PlacementOutcome + auto-cancel + case status transition**
`transition_case_status` calls `await session.commit()` internally. To achieve atomicity, we must:
1. Add PlacementOutcome row via `session.add()`
2. Add AuditEvent row for the outcome via `session.add()`
3. Add auto-cancel updates via `session.add_all()` / bulk update
4. Call `await session.flush()` to flush all pending writes WITHOUT committing
5. Call `transition_case_status()` which will commit everything in step 6

This means all writes (outcome row, audit event, cancel updates) land in the SAME commit as the status transition.

*Assumption documented:* Pre-flush then delegate to `transition_case_status` which commits.

**A3: Timeline endpoint — data source**
The spec says timeline reads `case_activity_events` but the CRITICAL RULES section clarifies this is the in-process event bus (no persistence). The `case_status_history` table (written by `transition_case_status`) is the persisted timeline. The timeline GET will read from `case_status_history`.

*Assumption documented:* GET /timeline reads `CaseStatusHistory` rows for the case, ordered by `entered_at` ascending.

**A4: AC9 retry routing — `transition_reason` requirement**
The spec says `transition_reason` is required for closure (AC11) but AC9 test says "transition_reason text required." Reading the spec description: "Retry routing — POST /api/v1/cases/{case_id}/status-transition with placement_coordinator or admin. Delegates to transition_case_status." The status-transition endpoint accepts optional `transition_reason`, but closure requires non-empty `transition_reason`. For retry routing (declined_retry_needed → ready_for_matching), `transition_reason` is optional.

*Assumption documented:* `transition_reason` is optional for retry routing, required (non-empty) only for closure.

**A5: PlacementOutcome does not have organization_id column**
The ORM model does not have `organization_id`. Tenant scoping for outcomes queries is done by joining through `patient_case_id` to `PatientCase` which does have `organization_id`.

**A6: AuditEvent for outcome vs AuditEvent for status change**
`transition_case_status` already writes its own AuditEvent (for the status_changed event). The outcomes module must write a SEPARATE AuditEvent with event_type=`"outcome_recorded"` for the PlacementOutcome record itself (capturing outcome_type, facility_id, etc.). This satisfies AC14's requirement that ALL outcome types produce an AuditEvent.

**A7: Case closure from family_declined/withdrawn**
After recording family_declined/withdrawn, the case status is unchanged (e.g. still at `pending_facility_response` or wherever it was). The manager then POSTs to /status-transition to close. The state machine must support the current status → closed transition for manager/admin. All states except `placed` already have `closed: ["manager", "admin"]` in the allowlist. `placed → closed` also exists.

**A8: state machine re: family_declined/withdrawn**
Looking at the state machine, there is no dedicated path that explicitly uses family_declined/withdrawn. Since we don't call `transition_case_status` for these, the case stays at its current status and manager closes it directly. This is correct per spec.

## Architecture Decisions

- **D-outcomes-1-pre-flush-atomicity**: Flush all pending DB writes (outcome row, outcome audit event, auto-cancel updates) via `await session.flush()` before calling `transition_case_status()`. `transition_case_status` then issues `await session.commit()` which atomically commits everything in the session. Why: avoids the double-commit problem while preserving full atomicity of the outcome write + status advance + auto-cancel.

- **D-outcomes-2-timeline-from-csh**: Read timeline from `CaseStatusHistory` (not in-process event bus). Why: the in-process event bus is ephemeral (in-memory list); `CaseStatusHistory` is the persisted record written by `transition_case_status` on every status change; it is the only durable timeline store available.

- **D-outcomes-3-family-withdrawn-no-transition**: family_declined and withdrawn outcomes do NOT call `transition_case_status`. Why: the spec states manager/admin must confirm closure via a separate status-transition; auto-advancing to closed removes required managerial oversight (explicitly listed as a failure mode in the spec).

- **D-outcomes-4-outcome-audit-separate**: Write a dedicated AuditEvent with entity_type="placement_outcome" and event_type="outcome_recorded" for every outcome type, in addition to the status-change AuditEvent written by transition_case_status. Why: AC14 requires every outcome type to have an audit record; the status-change AuditEvent only covers accepted/declined/placed (not family_declined/withdrawn which don't transition); a separate outcome-level audit event ensures HIPAA compliance for all 5 outcome types.

## Build Status: COMPLETE
- [2026-04-11T19:55:43.703Z] Created: `placementops/modules/outcomes/__init__.py`
- [2026-04-11T19:55:59.060Z] Created: `placementops/modules/outcomes/schemas.py`
- [2026-04-11T19:56:59.344Z] Created: `placementops/modules/outcomes/service.py`
- [2026-04-11T19:57:24.208Z] Created: `placementops/modules/outcomes/router.py`
- [2026-04-11T19:57:27.982Z] Created: `placementops/modules/outcomes/tests/__init__.py`
- [2026-04-11T19:58:02.349Z] Created: `placementops/modules/outcomes/tests/conftest.py`
- [2026-04-11T19:59:21.053Z] Created: `placementops/modules/outcomes/tests/test_outcomes.py`
- [2026-04-11T20:00:06.097Z] Created: `placementops/modules/outcomes/tests/test_timeline.py`
- [2026-04-12T20:41:52.529Z] Created: `placementops/modules/outcomes/router.py`
- [2026-04-12T20:41:57.138Z] Created: `placementops/modules/outcomes/router.py`
- [2026-04-12T20:42:02.185Z] Created: `placementops/modules/outcomes/router.py`
- [2026-04-12T20:42:29.240Z] Created: `placementops/modules/outcomes/tests/test_outcomes.py`
- [2026-04-12T20:42:56.639Z] Created: `placementops/modules/outcomes/tests/test_outcomes.py`
- [2026-04-13T00:33:12.844Z] Created: `placementops/modules/outcomes/tests/test_outcomes.py`
