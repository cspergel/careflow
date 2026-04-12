# outreach-module Build Log

## Pre-Build Spec Challenge

### Assumptions Documented

**A1 — state_machine role for outreach transitions**
The state machine in `core/state_machine.py` shows `outreach_pending_approval → outreach_in_progress` requires role `system`, and `outreach_in_progress → pending_facility_response` requires role `system`. Since service code is calling `transition_case_status` and is not a human actor, we pass `actor_role="system"` for these internal advance calls. This matches the pattern used in generate_matches when advancing case status.

**A2 — facility_options_generated → outreach_pending_approval transition requires placement_coordinator or admin**
The state machine shows `facility_options_generated → outreach_pending_approval` requires `["placement_coordinator", "admin"]`. For `submit_for_approval`, the service will call `transition_case_status` with the actual user's role_key for this forward advance. But for cases that are already past `facility_options_generated` (e.g. at `outreach_in_progress`), no advance is needed.

**A3 — phone_manual/task atomic advance uses "system" role**
For `outreach_pending_approval → outreach_in_progress` and `outreach_in_progress → pending_facility_response`, the state machine requires role `system`. The service code will pass `actor_role="system"` for these advances since they are triggered by the system (non-human) in a single atomic create operation.

**A4 — patch_outreach_action — spec says 409 if not in draft; spec note says "sent/approved/pending records"**
We interpret this as: only `draft` state allows editing. Any other state (pending_approval, approved, sent, canceled, failed) returns 409.

**A5 — AuditEvent for mark-sent: "new_value_json MUST NOT include draft_body or draft_subject"**
The new_value_json for mark-sent will contain only: `{action_id, sent_at, sent_by_user_id, delivery_status, approval_status}`. Draft content is never logged.

**A6 — Case advance for submit_for_approval**
The spec says advance case to `outreach_pending_approval` "if not already there." We check `case.current_status` before calling `transition_case_status`. Only transition if case is at `facility_options_generated`. If already at `outreach_pending_approval` or further, skip. For `facility_options_generated → outreach_pending_approval`, the state machine requires `["placement_coordinator", "admin"]` — we pass `auth_ctx.role_key`.

**A7 — AC5 first-approved logic: check for existing approved/sent actions**
The query checks for any `OutreachAction` for the case where `approval_status IN ('approved', 'sent')`. If none → advance to `outreach_in_progress`. The transition from `outreach_pending_approval → outreach_in_progress` requires role `system`, so we use `actor_role="system"`.

**A8 — declined_retry_needed → outreach_pending_approval is valid per state machine**
If the case is at `declined_retry_needed`, the state machine allows `outreach_pending_approval` with `["placement_coordinator", "admin"]`. We handle this in submit_for_approval by checking statuses that need advancing.

**A9 — phone_manual/task: case may be at any pre-outreach state**
For `facility_options_generated → outreach_pending_approval → outreach_in_progress → pending_facility_response`, we must advance through multiple intermediate states. Each call to `transition_case_status` commits, so we must call it three times within the same conceptual "operation." However, the constraint says "single atomic write" for the action record. We interpret this as: the OutreachAction is created at `sent` in one write, then the case advances (which may require multiple transitions via state machine). The state machine commits on each call, so each transition is individually committed. The OutreachAction creation + first commit is atomic; subsequent case transitions are sequential commits.

**A10 — approved → outreach_in_progress transition requires role "system"**
Based on state_machine.py: `outreach_pending_approval → outreach_in_progress: ["system"]`. The approve service function uses `actor_role="system"`.

**A11 — Template variables allowlist applied to dict keys only**
We validate all keys in `template_variables` dict against `ALLOWED_VARIABLES`. The values may be any string. The rendered body replaces the draft_body if a template is used.

**A12 — OutreachAction.created_by_user_id not in model**
The model has no `created_by_user_id` field. We don't set this. AuditEvent captures who created it.

---

## Build Progress

- [x] Pre-build spec challenge complete, assumptions documented
- [x] `__init__.py` created
- [x] `template_renderer.py` created (AC1, AC2)
- [x] `schemas.py` created
- [x] `service.py` created (AC1–AC12)
- [x] `router.py` created
- [x] `tests/__init__.py` created
- [x] `tests/conftest.py` created
- [x] `tests/test_outreach_flow.py` created (AC1–AC8, AC11, AC12)
- [x] `tests/test_queue_templates.py` created (AC9, AC10)

---

## Decisions Made During Build

- D-outreach-1: Used `actor_role="system"` for `outreach_pending_approval → outreach_in_progress` and `outreach_in_progress → pending_facility_response` transitions. Why: state machine only allows `system` role for these transitions, matching how internal pipeline advances work in matching-module.
- D-outreach-2: `patch_outreach_action` accepts only `draft` state; returns 409 for ALL other states. Why: spec says "sent records cannot be edited" and approved/pending records should not be modified in-flight as that would invalidate the approval.
- D-outreach-3: For phone_manual/task creation, we advance case status using sequential `transition_case_status` calls each with `actor_role="system"` since state machine requires it. The OutreachAction itself is committed atomically at `sent`.
- D-outreach-4: AuditEvent old_value_json for mark-sent contains `{approval_status: "approved"}`, new_value_json contains `{action_id, sent_at, sent_by_user_id, approval_status: "sent"}`. No body content.
- [2026-04-11T19:44:53.446Z] Created: `placementops/modules/outreach/__init__.py`
- [2026-04-11T19:44:53.808Z] Created: `placementops/modules/outreach/tests/__init__.py`
- [2026-04-11T19:45:10.773Z] Created: `placementops/modules/outreach/template_renderer.py`
- [2026-04-11T19:45:25.815Z] Created: `placementops/modules/outreach/schemas.py`
- [2026-04-11T19:46:45.170Z] Created: `placementops/modules/outreach/service.py`
- [2026-04-11T19:47:19.187Z] Created: `placementops/modules/outreach/router.py`
- [2026-04-11T19:47:53.569Z] Created: `placementops/modules/outreach/tests/conftest.py`
- [2026-04-11T19:49:23.601Z] Created: `placementops/modules/outreach/tests/test_outreach_flow.py`
- [2026-04-11T19:49:53.328Z] Created: `placementops/modules/outreach/tests/test_queue_templates.py`
- [2026-04-11T19:50:20.713Z] Created: `placementops/modules/outreach/service.py`
- [2026-04-11T19:50:32.427Z] Created: `placementops/modules/outreach/service.py`
- [2026-04-11T23:14:42.979Z] Created: `placementops/modules/outreach/template_renderer.py`
- [2026-04-12T00:00:12.118Z] Created: `placementops/modules/outreach/template_renderer.py`
- [2026-04-12T01:06:41.699Z] Created: `placementops/modules/outreach/tests/test_outreach_flow.py`
- [2026-04-12T13:18:40.646Z] Edited: `.env.example`
- [2026-04-12T13:18:43.311Z] Created: `placementops/modules/outreach/template_renderer.py`
- [2026-04-12T13:18:43.934Z] Created: `.env.example`
- [2026-04-12T15:41:31.154Z] Edited: `placementops/modules/outreach/service.py`
- [2026-04-12T15:41:38.114Z] Created: `placementops/modules/outreach/service.py`
- [2026-04-12T15:41:47.007Z] Created: `placementops/modules/outreach/service.py`
- [2026-04-12T15:42:02.893Z] Created: `placementops/modules/outreach/service.py`
- [2026-04-12T15:42:11.087Z] Created: `placementops/modules/outreach/service.py`
- [2026-04-12T15:42:21.164Z] Created: `placementops/modules/outreach/service.py`
- [2026-04-12T15:42:59.755Z] Edited: `placementops/modules/outreach/tests/test_outreach_flow.py`
- [2026-04-12T15:43:11.599Z] Created: `placementops/modules/outreach/tests/test_outreach_flow.py`
- [2026-04-12T15:43:16.179Z] Created: `placementops/modules/outreach/tests/test_outreach_flow.py`
- [2026-04-12T15:43:38.910Z] Created: `placementops/modules/outreach/tests/test_outreach_flow.py`

---

## Rebuild — Review Fixes Applied

### F3 (HIGH) — phone_manual/task case advance atomicity

**Problem:** OutreachAction was committed at line 324 (one transaction), then `_advance_case_through_outreach_to_pending` called `transition_case_status` up to 3 times, each with its own `session.commit()`. A crash between commits left the case stuck.

**Fix:** Removed the early `await session.commit()` after the bypass-channel audit event write. The OutreachAction and its AuditEvent are now `session.flush()`ed only (pending in session), and the first call to `transition_case_status` inside `_advance_case_through_outreach_to_pending` commits all pending writes (OutreachAction + its AuditEvent + first case status history row) together in one transaction. `session.refresh(action)` moved to after all transitions complete.

**Decision D-outreach-4-bypass-atomicity:** Defer commit until first `transition_case_status` call. Why: this makes the OutreachAction creation and the first case-status change atomic without modifying `state_machine.py` (which is in `core-infrastructure` scope).

### F1 (MEDIUM) — `approve_action` missing `case_activity_event`

**Fix:** Added `await _write_case_activity_event(...)` at the end of `approve_action`, after the case advance, with `event_type="outreach_approved"`, `old_status="pending_approval"`, `new_status="approved"`. Mirrors the pattern from `submit_for_approval` and `mark_sent`.

Added test `test_f1_approve_action_writes_case_activity_event` that registers a temporary event-bus subscriber, calls `approve_action`, and asserts a `CaseActivityEvent` with `event_type="outreach_approved"`, `old_status="pending_approval"`, `new_status="approved"` was published.

### F2 (MEDIUM) — facility_id matching-module interface contract not implemented

**Fix:** Added a query in `create_outreach_action` after the closed-case check: when `payload.facility_id is not None`, query `FacilityMatch` for a record matching `patient_case_id + facility_id + selected_for_outreach=True`. If not found, return HTTP 400 with message "facility must be selected for outreach before drafting outreach actions". Tenant isolation is achieved via `patient_case_id` (which is already verified to belong to `organization_id`).

Added tests `test_f2_facility_not_selected_returns_400` and `test_f2_facility_selected_allows_creation`.

### F4 (LOW) — dead code removed

**Fix:** Deleted `_advance_case_if_needed` function (lines 188–212 in original) entirely — it was defined but never called anywhere in the module.

### F5 (LOW) — closed-case check wired to action-level endpoints

**Fix:** Modified `_get_action_scoped` to return both `OutreachAction` and `PatientCase` in one query (using `select(OutreachAction, PatientCase).join(...)`), then checks `case.current_status == "closed"` and raises HTTP 409 if so. All action-level mutation functions (`patch_outreach_action`, `submit_for_approval`, `approve_action`, `mark_sent`, `cancel_action`) call `_get_action_scoped` — so all get the check automatically.

Added tests `test_f5_patch_action_on_closed_case_returns_409` and `test_f5_submit_for_approval_on_closed_case_returns_409`.

### Test run result

All 58 tests pass.
- [2026-04-12T20:40:50.023Z] Created: `placementops/modules/outreach/service.py`
