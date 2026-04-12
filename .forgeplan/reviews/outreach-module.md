## Review: outreach-module
**Date:** 2026-04-12T00:00:00Z
**Reviewer:** Claude Sonnet 4.6
**Review type:** native
**Cycle:** 2

---

## Cycle 2 Focus: Fix Verification

### F3 (High) — phone_manual/task bypass atomicity
**Status: FIXED — VERIFIED**

The Cycle 1 premature commit was at `service.py:314` (formerly a `session.commit()`). In Cycle 2 it is now `await session.flush()` at line 314, with a comment explicitly stating "Do NOT commit here — advance case first; transition_case_status commits everything." The AuditEvent is enqueued to the session after the flush (lines 317–331) without a commit. The first call to `transition_case_status` inside `_advance_case_through_outreach_to_pending` (line 391 or 404, depending on case status) issues `await session.commit()` at `state_machine.py:214`, which atomically commits the OutreachAction, its AuditEvent, and the first case status change together. Subsequent transitions within the same bypass path each commit independently but correctly — no intermediate `pending_approval` or `approved` states are written to the OutreachAction row. Test `test_ac8_no_intermediate_states_stored` (line 814) validates this invariant explicitly.

**One residual observation (not a blocker):** `transition_case_status` unconditionally commits after every transition (`state_machine.py:214`). In the bypass path, this means up to three separate database transactions are issued (one per `facility_options_generated→outreach_pending_approval→outreach_in_progress→pending_facility_response` step). The OutreachAction itself lands in the first commit, but the three case transitions are in three separate commits. This does not violate the AC8 constraint as written ("SINGLE ATOMIC OPERATION" applies to the OutreachAction row never touching `pending_approval` or `approved` states) — the OutreachAction is created at `sent` in the first commit. However, if a crash occurs between the second and third transitions, the case could be left at `outreach_in_progress` with the OutreachAction already at `sent`. This is a pre-existing design characteristic of `transition_case_status` and is outside the F3 fix scope. Flagged as a Suggestion.

---

### F1 (Medium) — approve_action missing case_activity_event
**Status: FIXED — VERIFIED**

`approve_action` now calls `_write_case_activity_event` at lines 644–652 with `old_status="pending_approval"` and `new_status="approved"`. The call is unconditional — it fires whether or not a case advance occurs, satisfying AC11 for the `pending_approval→approved` transition.

A dedicated regression test `test_f1_approve_action_writes_case_activity_event` (line 1014–1064) uses the in-process event bus subscription mechanism to verify that a `CaseActivityEvent` with `event_type="outreach_approved"`, `old_status="pending_approval"`, and `new_status="approved"` is published. This is thorough.

---

### F2 (Medium) — facility_id not validated against FacilityMatch
**Status: FIXED — VERIFIED**

`create_outreach_action` now queries `FacilityMatch` at lines 238–252 when `payload.facility_id is not None`. The query filters on `patient_case_id`, `facility_id`, and `selected_for_outreach.is_(True)`. If no matching row is found, HTTP 400 is returned with the detail "facility must be selected for outreach before drafting outreach actions."

Tenant isolation is achieved indirectly: the query filters on `patient_case_id` which is already known to belong to the authenticated org (validated by `_get_case_scoped` at line 224 before the FacilityMatch query is reached). This matches the interface contract comment at line 235: "Tenant scoping via patient_case_id (FacilityMatch has no organization_id column; isolation comes from the case belonging to this org, already verified above)."

Two regression tests cover this:
- `test_f2_facility_not_selected_returns_400` (line 1074) — confirms HTTP 400 when `selected_for_outreach=False`
- `test_f2_facility_selected_allows_creation` (line 1126) — confirms success when `selected_for_outreach=True`

---

### F4 (Low) — dead code _advance_case_if_needed
**Status: FIXED — VERIFIED**

A full-text search of `placementops/modules/outreach/` confirms zero occurrences of `_advance_case_if_needed`. The function has been removed entirely. No references remain in any file.

---

### F5 (Low) — _get_action_scoped missing closed-case check
**Status: FIXED — VERIFIED**

`_get_action_scoped` (lines 115–151) now executes a JOIN query against `PatientCase` and checks `case.current_status == "closed"` at line 146, returning HTTP 409 if true. All action-level mutation endpoints that call `_get_action_scoped` — `patch_outreach_action`, `submit_for_approval`, `approve_action`, `mark_sent`, `cancel_action` — inherit this check.

Regression tests:
- `test_f5_patch_action_on_closed_case_returns_409` (line 1180) — covers `patch_outreach_action`
- `test_f5_submit_for_approval_on_closed_case_returns_409` (line 1204) — covers `submit_for_approval`

Missing tests for `approve_action`, `mark_sent`, and `cancel_action` on closed cases, but the fix itself is structurally sound because all three call `_get_action_scoped` before any other logic.

---

## Acceptance Criteria

### AC1: Draft creation with allowlisted template variable substitution
**PASS**

`validate_template_variables` in `template_renderer.py:53–70` checks all keys against `ALLOWED_VARIABLES` before `render_template` is ever called. In `service.py`, `validate_template_variables(variables)` is called at line 279 before `render_template` at line 282. The schema `OutreachActionCreate` uses `extra="forbid"` so no unexpected fields slip through at the HTTP layer.

Tests: `test_ac1_create_draft_with_template_variables` (line 66), `test_ac1_create_draft_non_allowlisted_variable_returns_400` (line 96), `test_ac1_allowlist_check_before_render` (line 123), `test_ac1_allowed_variables_set` (line 136).

### AC2: Jinja2 SandboxedEnvironment prevents SSTI
**PASS**

`template_renderer.py:36–49` uses a custom `_PlacementSandbox(SandboxedEnvironment)` subclass that additionally blocks all attributes starting with `_`. `SecurityError`, `TemplateSyntaxError`, `UndefinedError`, and a bare `Exception` catch are all mapped to HTTP 400. `autoescape=True` and `StrictUndefined` are set.

Tests: `test_ac2_ssti_mro_traversal_raises_400` (line 153), `test_ac2_ssti_undeclared_name_raises_400` (line 161), `test_ac2_sandboxed_environment_class_used` (line 169), `test_ac2_ssti_class_attr_access_blocked` (line 190), `test_ac2_valid_template_renders_correctly` (line 197).

### AC3: Draft edit restricted to correct role and state
**PASS**

`patch_outreach_action` (`service.py:434`) guards that `action.approval_status == "draft"` before applying changes, returning 409 otherwise. `_get_action_scoped` also blocks closed-case mutations. Role enforcement (`placement_coordinator`, `admin` only) is applied at the router via `require_role(*_OUTREACH_WRITE_ROLES)` (`router.py:68`).

Tests: `test_ac3_patch_draft_as_coordinator_succeeds` (line 213), `test_ac3_patch_sent_action_returns_409` (line 233), `test_ac3_patch_approved_action_returns_409` (line 260), `test_ac3_patch_intake_staff_role_forbidden_via_router` (line 282), `test_ac3_patch_clinical_reviewer_role_forbidden_via_router` (line 308).

### AC4: Submit-for-approval advances OutreachAction and case
**PASS**

`submit_for_approval` (`service.py:489`) transitions action to `pending_approval` and advances the case from `_PRE_OUTREACH_STATUSES` to `outreach_pending_approval` if needed. Both an AuditEvent and a `_write_case_activity_event` call are present (lines 516–555).

Tests: `test_ac4_submit_for_approval_advances_action` (line 342), `test_ac4_submit_advances_case_to_outreach_pending_approval` (line 361), `test_ac4_submit_writes_audit_event` (line 386), `test_ac4_submit_non_draft_returns_409` (line 416).

### AC5: Approve advances OutreachAction and case on first approval
**PASS**

`approve_action` (`service.py:567`) sets `approval_status=approved`, `approved_by_user_id`, and `approved_at`. The "first approved" check queries for existing `approved` or `sent` actions excluding the current one (lines 617–626). Case advance is gated on `case.current_status == "outreach_pending_approval"` (line 631). AuditEvent and `_write_case_activity_event` are both written (lines 597–652).

Tests: `test_ac5_approve_sets_fields` (line 443), `test_ac5_first_approval_advances_case` (line 464), `test_ac5_second_approval_does_not_re_advance_case` (line 486), `test_ac5_approve_non_pending_returns_409` (line 513), `test_ac5_approve_writes_audit_event` (line 535).

### AC6: Mark-sent stubs email delivery without logging body content
**PASS**

`mark_sent` (`service.py:664`) sets `approval_status=sent`, `sent_by_user_id`, and `sent_at`. The `_write_audit_event` call at lines 696–710 contains only `action_id`, `approval_status`, `sent_at`, `sent_by_user_id`, and `delivery_status` — no `draft_body` or `draft_subject`. Case advance to `pending_facility_response` is conditioned on `is_first_sent` and `case.current_status == "outreach_in_progress"` (lines 718–740).

Tests: `test_ac6_mark_sent_sets_fields` (line 572), `test_ac6_audit_event_does_not_contain_body` (line 593), `test_ac6_mark_sent_advances_case_to_pending_facility_response` (line 633), `test_ac6_mark_sent_non_approved_returns_409` (line 652).

### AC7: Cancel permitted from pre-sent states only
**PASS**

`cancel_action` (`service.py:763`) returns 409 with the exact message "sent records are permanent communication records" when `action.approval_status == "sent"` (line 782). The `_CANCELABLE_STATES` frozenset (`draft`, `pending_approval`, `approved`, `failed`) guards against other non-cancelable states.

Tests: `test_ac7_cancel_pre_sent_states` (line 678, parametrized over all four cancelable states), `test_ac7_cancel_sent_returns_409_with_exact_message` (line 700), `test_ac7_cancel_writes_audit_event` (line 726).

### AC8: phone_manual and task channels bypass approval with atomic state advance
**PASS**

Bypass channels (`service.py:65`) are created at `approval_status="sent"` directly (line 302). The `session.flush()` at line 314 makes the row visible within the session before any case transitions. No `session.commit()` is issued before `_advance_case_through_outreach_to_pending` (line 337). The first `transition_case_status` call within that helper commits the OutreachAction + AuditEvent + first case transition atomically. No OutreachAction row at `pending_approval` or `approved` is ever created.

Tests: `test_ac8_bypass_channels_created_at_sent` (line 762), `test_ac8_bypass_channel_advances_case_to_pending_facility_response` (line 787), `test_ac8_no_intermediate_states_stored` (line 814).

### AC9: Outreach queue returns cross-case actions filterable by approval_status
**PASS**

`get_outreach_queue` (`service.py:833`) joins `OutreachAction` to `PatientCase` and filters on `PatientCase.organization_id`. The `approval_status_filter` parameter gates an additional `.where` clause. Pagination via `offset`/`limit` is implemented. The queue router endpoint has no `require_role` dependency, only `get_auth_context` (`router.py:291`), which returns 401 for unauthenticated requests.

Tests: `test_ac9_queue_returns_org_scoped_actions` (line 41), `test_ac9_queue_filter_by_pending_approval` (line 76), `test_ac9_queue_unauthenticated_returns_401` (line 106), `test_ac9_queue_cross_case` (line 114), `test_ac9_queue_pagination` (line 137).

### AC10: Template listing is read-only
**PASS**

`get_templates` (`service.py:883`) queries `OutreachTemplate` filtered by `organization_id` and `is_active`. Explicit POST, PATCH, and DELETE handlers on `/templates/outreach` (`router.py:343–379`) all raise HTTP 405.

Tests: `test_ac10_get_templates_returns_active_templates` (line 176), `test_ac10_templates_org_scoped` (line 217), `test_ac10_post_templates_returns_405` (line 252), `test_ac10_patch_templates_returns_405` (line 274), `test_ac10_delete_templates_returns_405` (line 294), `test_ac10_get_templates_via_router` (line 315).

### AC11: All outreach state changes produce AuditEvent and case_activity_event
**PASS**

All five transitions are covered:
- `draft→pending_approval`: AuditEvent at `service.py:516`, `_write_case_activity_event` at line 547
- `pending_approval→approved`: AuditEvent at `service.py:597`, `_write_case_activity_event` at line 644 (F1 fix)
- `approved→sent`: AuditEvent at `service.py:696`, `_write_case_activity_event` at line 743
- `any→canceled`: AuditEvent at `service.py:798`, `_write_case_activity_event` at line 814
- bypass creation (phone_manual/task at `sent`): AuditEvent at `service.py:317`, case transitions produce AuditEvents via `transition_case_status`

Tests: `test_ac11_complete_flow_audit_trail` (line 855), `test_ac11_cancel_from_each_state_writes_audit` (line 921), `test_f1_approve_action_writes_case_activity_event` (line 1014).

### AC12: Closed-case mutation rejected
**PASS**

`create_outreach_action` checks `case.current_status == "closed"` at `service.py:227`. `_get_action_scoped` checks the associated case status at `service.py:146` for all action-level endpoints. Both return HTTP 409.

Tests: `test_ac12_closed_case_create_returns_409` (line 957), `test_ac12_closed_case_returns_409_via_router` (line 980), `test_f5_patch_action_on_closed_case_returns_409` (line 1180), `test_f5_submit_for_approval_on_closed_case_returns_409` (line 1204).

---

## Constraints

**C1: Template variable substitution MUST use Jinja2 SandboxedEnvironment**
PASS — `template_renderer.py:46` uses `_PlacementSandbox(SandboxedEnvironment)`.

**C2: Email body content MUST NOT appear in AuditEvent new_value_json or any log output**
PASS — `_write_audit_event` in `mark_sent` (lines 696–710) includes only safe fields. `test_ac6_audit_event_does_not_contain_body` (line 593) explicitly asserts `draft_body` and `draft_subject` are absent from `new_value_json`. The `PHILogFilter` in `middleware.py:41–42` includes `draft_body` and `draft_subject` in `_PHI_FIELDS`.

**C3: Sending is a permanent record; approval_status=sent MUST NOT be transitioned**
PASS — `cancel_action` explicitly guards `sent` at `service.py:780`. No other service function transitions away from `sent`. The `OutreachAction.approval_status` column has no direct-write path bypassing the service layer.

**C4: phone_manual and task channel actions MUST be created at approval_status=sent in a single atomic write**
PASS — The OutreachAction is instantiated with `approval_status="sent"` at line 302, flushed at line 314, and committed by the first `transition_case_status` call. It never passes through `pending_approval` or `approved`.

**C5: The atomic case advance for phone_manual/task MUST use the shared state-machine transition handler**
PASS — `_advance_case_through_outreach_to_pending` uses `transition_case_status` exclusively. No direct writes to `PatientCase.current_status` exist in the outreach module.

**C6: All mutating endpoints MUST reject requests where case.current_status=closed with 409**
PASS — `create_outreach_action` checks directly; all action-level endpoints check via `_get_action_scoped`.

**C7: Template CRUD (POST/PATCH/DELETE on /templates/outreach) is forbidden**
PASS — Explicit 405 handlers in `router.py:343–379`.

**C8: organization_id scoping MUST be applied to all queries**
PASS — All service functions receive `auth_ctx.organization_id` and pass it to query filters or `_get_case_scoped`/`_get_action_scoped`.

**C9: Only placement_coordinator or admin roles may create, edit, submit, approve, send, or cancel outreach actions**
PASS — `require_role(*_OUTREACH_WRITE_ROLES)` applied to all mutating routes at `router.py:68, 108, 143, 179, 215, 252`.

---

## Interfaces

**I1: matching-module — query FacilityMatch.selected_for_outreach=True before creating**
PASS — Query at `service.py:238–252` with `FacilityMatch.selected_for_outreach.is_(True)`. Returns 400 if no match found.

**I2: core-infrastructure — ORM models, transition_case_status, AsyncSessionLocal, get_auth_context**
PASS — All imports confirmed: `transition_case_status` from `state_machine`, `AsyncSession` from core database, `get_auth_context` from `core.auth`.

**I3: auth-module — require_role Depends()**
PASS — `require_role` imported from `placementops.modules.auth.dependencies` at `router.py:39` and applied to all write routes.

**I4: outcomes-module — reads OutreachAction records (read contract)**
Not in scope for this module's implementation; the outreach module does not block this interface. OutreachAction records are readable by any module with DB access.

**I5: admin-surfaces — reads templates via GET only**
PASS — No write operations on `OutreachTemplate` exist in this module.

---

## Non-Goals

**NG1: This module does not own OutreachTemplate CRUD** — CONFIRMED. No POST/PATCH/DELETE service functions for templates exist.

**NG2: This module does not perform real email delivery in Phase 1** — CONFIRMED. `mark_sent` is a stub; no SMTP or email delivery code present.

**NG3: This module does not implement voice/AI call features** — CONFIRMED. Voice fields exist on the model for Phase 2 but no voice logic is implemented.

**NG4: This module does not record placement outcomes** — CONFIRMED.

**NG5: This module does not implement auto-retry on failed outreach** — CONFIRMED. `failed` state is recognized as cancelable but no retry logic exists.

**NG6: This module does not implement SMS or voice_ai channel logic in Phase 1** — CONFIRMED. Channels are accepted as values but no channel-specific logic beyond bypass detection is present.

---

## Failure Modes

**FM1: SSTI vulnerability — bare Environment instead of SandboxedEnvironment**
MITIGATED — `_PlacementSandbox(SandboxedEnvironment)` with dunder-blocking override used throughout. Test `test_ac2_sandboxed_environment_class_used` asserts the type at runtime.

**FM2: Email body logged in plaintext — AuditEvent serializer includes all OutreachAction fields**
MITIGATED — `_write_audit_event` calls in `mark_sent` and all other transitions are manually constructed with explicit key sets that exclude `draft_body` and `draft_subject`. `PHILogFilter` provides a logging-level backstop.

**FM3: Sent action incorrectly canceled — missing approval_status guard on cancel endpoint**
MITIGATED — Explicit `if action.approval_status == "sent"` guard at `service.py:780` returns 409 before the cancelable-states check. Test `test_ac7_cancel_sent_returns_409_with_exact_message` asserts exact message text.

**FM4: phone_manual non-atomic advance — intermediate states written in separate DB transactions**
MITIGATED — The OutreachAction is flushed (not committed) before the first `transition_case_status` call, which performs the first commit atomically. The OutreachAction row is never written at an intermediate state. Note: partial mitigation only for multi-step case transitions — see S1 below.

**FM5: Non-allowlisted template variable silently rendered — allowlist check applied after rendering**
MITIGATED — `validate_template_variables` is called at `service.py:279` before `render_template` at line 282.

**FM6: Cross-tenant template access — missing organization_id filter on GET /templates/outreach**
MITIGATED — `get_templates` filters on `OutreachTemplate.organization_id == str(organization_id)` at `service.py:896`. Test `test_ac10_templates_org_scoped` confirms cross-tenant isolation.

**FM7: Case advance missing — first-approved-action logic not checking case.current_status**
MITIGATED — `approve_action` at line 631 checks `case.current_status == "outreach_pending_approval"` before attempting the transition. `mark_sent` at line 731 checks `case.current_status == "outreach_in_progress"`.

---

## New Issues Found in Cycle 2

### Suggestion S1: Multi-step case transitions in bypass path are in separate DB transactions

File: `C:\Users\drcra\Documents\Coding Projects\Placement-ops-careflow\placementops\core\state_machine.py:214` — `await session.commit()` is unconditional inside `transition_case_status`.
File: `C:\Users\drcra\Documents\Coding Projects\Placement-ops-careflow\placementops\modules\outreach\service.py:391–425` — `_advance_case_through_outreach_to_pending` may call `transition_case_status` up to three times.

The OutreachAction row is committed atomically with the first case transition (as required by F3 and AC8). However, each subsequent transition in the chain is a separate commit. A crash between commits would leave the case at `outreach_in_progress` with the OutreachAction already at `sent`. This is a known trade-off of the shared `transition_case_status` design and is outside the outreach module's own scope to fix unilaterally. Worth capturing as a platform-level technical debt item for the state machine.

### Suggestion S2: Missing F5 regression tests for approve_action, mark_sent, cancel_action on closed cases

File: `C:\Users\drcra\Documents\Coding Projects\Placement-ops-careflow\placementops\modules\outreach\tests\test_outreach_flow.py:1180,1204` — tests exist only for `patch` and `submit` on closed cases. `approve_action`, `mark_sent`, and `cancel_action` are not covered by dedicated closed-case tests. The structural fix is correct (all three call `_get_action_scoped`), but the test gap is worth filling for completeness under AC12.

### Suggestion S3: OutreachActionResponse exposes draft_body for sent records

File: `C:\Users\drcra\Documents\Coding Projects\Placement-ops-careflow\placementops\modules\outreach\schemas.py:83` — `draft_body: str` is included unconditionally in `OutreachActionResponse`. This means the full email body is retrievable via the API for sent records. This is explicitly noted in the schema comment and is not a spec violation (the constraint only applies to AuditEvent log entries). It may warrant a future access-control decision about redacting `draft_body` in responses for `sent` actions.

---

## Recommendation: APPROVE

All five Cycle 1 findings (F1–F5) have been correctly implemented and are verified by code inspection and dedicated regression tests. All twelve acceptance criteria pass. All constraints, interfaces, and failure modes are satisfied or mitigated. The three items listed above are suggestions and do not block approval.
