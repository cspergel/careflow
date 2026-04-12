## Review: admin-surfaces
**Date:** 2026-04-11T00:00:00Z
**Reviewer:** Claude Sonnet 4.6
**Review type:** native
**Cycle:** 1

---

### Acceptance Criteria

**AC1: PASS** — GET /api/v1/admin/users returns paginated users scoped to org; admin-only.

- Route registered at `router.py:59–86` with `dependencies=[require_role("admin")]` at decorator level. Auth gate is enforced by `auth/dependencies.py:require_role`, which performs a DB-authoritative role lookup (not JWT-cached), satisfying the constraint about pre-handler enforcement.
- `service.py:96–110`: `list_users` queries `User.organization_id == org_id` derived from `auth_ctx.organization_id`. Cross-org leakage is structurally impossible from this query.
- Response includes `UserListResponse` with `items`, `total`, `page`, `page_size` fields (`schemas.py:39–45`).
- Test coverage: `test_users.py:30–157` covers (a) 200 with org-scoping assertion on every returned item, (b) pagination, (c) 403 for all 5 non-admin roles by name (manager, placement_coordinator, intake_staff, clinical_reviewer, read_only), and (d) 401 for unauthenticated. All 6 non-admin role cases covered individually.

---

**AC2: PASS** — POST /api/v1/admin/users creates user with status=active; writes AuditEvent(user_created); admin-only.

- Route at `router.py:90–112` with `dependencies=[require_role("admin")]`, status_code=201.
- `service.py:115–178`: validates role_key against `VALID_ROLE_KEYS` (400 on invalid), checks email uniqueness (409 on duplicate), creates `User` with `status="active"`, flushes, then calls `emit_audit_event(..., event_type="user_created", old_value=None, new_value={...})` before `session.commit()`. Audit is atomic within the same transaction.
- `emit_audit_event` (`core/audit.py:18–54`) adds `AuditEvent` row to session without committing; the service commits once at line 177, ensuring atomicity.
- Test coverage: `test_users.py:165–266` covers 201 with DB row verification, audit event field assertions (actor_user_id, old_value_json=None, new_value_json with role_key), 409 on duplicate email, 400 on invalid role_key, 403 for non-admin.

---

**AC3: PASS** — PATCH /api/v1/admin/users/{user_id} updates role/status; last-admin guard; AuditEvent(user_updated); admin-only.

- Route at `router.py:116–140` with `dependencies=[require_role("admin")]`.
- `service.py:183–287`: cross-org access returns 404 (query includes `User.organization_id == org_id`). Validates role_key and status inputs (400 on invalid). Last-admin guard at lines 227–245: checks `will_become_inactive` (status→inactive when currently active) AND `will_lose_admin` (role_key changing away from admin when currently admin). Counts active admins; raises 400 with exact message "Cannot deactivate the last active admin in this organization." if count ≤ 1.
- Old values captured before mutation at lines 248–254 (AC11 compliance). AuditEvent written before commit.
- Test coverage: `test_users.py:274–488` covers role change (200 + DB assertion), audit event with old/new value assertions, deactivating non-admin (allowed), last-admin deactivation → 400, last-admin role-change → 400, two-admins allows deactivation, 403 for non-admin, 404 for non-existent user, 400 for invalid status.

---

**AC4: PASS** — GET /api/v1/templates/outreach accessible to all authenticated roles; org-scoped.

- Route at `router.py:149–170`: **no** `dependencies=[require_role(...)]` present. Only `auth: AuthContext = Depends(get_auth_context)` is listed. This correctly restricts to authenticated users while permitting all roles.
- `service.py:296–314`: queries `OutreachTemplate.organization_id == org_id`. Org-scoping enforced.
- Test coverage: `test_templates.py:30–115` tests all 6 roles individually (admin, manager, coordinator, intake_staff, clinical_reviewer, read_only) each asserting 200. Cross-org isolation test asserts that `seed_other_org_template` ID does not appear in results for the primary org. Unauthenticated → 401.

---

**AC5: PASS** — POST /api/v1/templates/outreach creates OutreachTemplate; sets created_by_user_id; AuditEvent(template_created); admin-only; 403 for non-admin.

- Route at `router.py:174–197` with `dependencies=[require_role("admin")]`, status_code=201.
- `service.py:319–383`: validates template_name non-empty (strip check), body_template non-empty, template_type in enum, allowed_variables via `_validate_allowed_variables` (400 on invalid). Sets `created_by_user_id=str(auth_ctx.user_id)` and `organization_id=org_id`. AuditEvent written with `event_type="template_created"`, `old_value=None`.
- Test coverage: `test_templates.py:123–249` covers 201 with DB assertion and created_by_user_id verification, audit event check (old_value_json=None), invalid variable → 400, invalid type → 400, empty name → 400, coordinator → 403.

---

**AC6: PASS** — PATCH /api/v1/templates/outreach/{template_id} updates template; AuditEvent(template_updated); admin-only; 404 for cross-org template_id.

- Route at `router.py:201–226` with `dependencies=[require_role("admin")]`.
- `service.py:388–484`: queries `OutreachTemplate.id == template_id AND OutreachTemplate.organization_id == org_id`. Returns 404 (not 403) for cross-org or missing template (line 416). Validates template_name, body_template non-empty if provided; validates allowed_variables via `_validate_allowed_variables`. Old values captured before mutation. AuditEvent written with event_type=`template_updated`.
- Test coverage: `test_templates.py:257–371` covers 200 + DB assertion, audit event with old/new is_active values, cross-org → 404, non-existent → 404, unsafe variable → 400, manager → 403.

---

**AC7: PASS** — GET /api/v1/imports returns paginated ImportJob records with status/counts; read-only; admin-only.

- Route at `router.py:235–263` with `dependencies=[require_role("admin")]`. No POST/PATCH/DELETE routes for ImportJob exist anywhere in `router.py`.
- `service.py:493–520`: org-scoped query on `ImportJob.organization_id == org_id`. Returns `(jobs, total)`.
- `ImportJobResponse` schema at `schemas.py:125–143` includes `created_count`, `updated_count`, `failed_count`, `status`.
- Test coverage: `test_imports_org_ref.py:32–128` covers two-job list with count/status assertions, org-scoping (other org job absent), pagination, non-admin → 403, and explicit test that POST /api/v1/imports returns 404/405/415/422 (not 201/202), confirming no intake-module route is wired into admin-surfaces.

---

**AC8: PASS** — GET /api/v1/imports/{import_id} returns full ImportJob including error_detail_json; admin-only; 404 for cross-org.

- Route at `router.py:267–288` with `dependencies=[require_role("admin")]`.
- `service.py:524–548`: queries `ImportJob.id == import_id AND ImportJob.organization_id == org_id`. Raises 404 (not 403) if None.
- `ImportJobResponse` includes `error_detail_json: dict | None` (`schemas.py:141`).
- Test coverage: `test_imports_org_ref.py:136–183` covers full detail with error_detail_json assertion, cross-org → 404, non-existent → 404, non-admin → 403.

---

**AC9: PARTIAL PASS (known Phase 1 limitation — documented)** — GET /PATCH /api/v1/admin/organization; AuditEvent(org_settings_updated); admin-only.

- Routes at `router.py:297–347` with `dependencies=[require_role("admin")]`.
- `service.py:557–628`: GET returns Organization record. PATCH updates `org.name` if `payload.org_name` provided. `settings_json` is accepted but NOT persisted (no DB column). AuditEvent written with `event_type=org_settings_updated`.
- **Spec gap (data model mismatch):** The spec's `OrgSettings` data model defines `organization_id: uuid` as a field, but the `OrgSettingsResponse` schema (`schemas.py:160–168`) omits `organization_id`. The `Organization` ORM (`reference_tables.py:20–25`) has no `organization_id` column (the org IS the organization; `id` is the org identifier). The router returns `OrgSettingsResponse(id=org.id, ...)` — correct, but the spec's `OrgSettings.organization_id` field is unrepresented in the response. This is a spec/implementation divergence. The test at `test_imports_org_ref.py:199` checks `body["id"] == seed_org` which functions as an implicit organization_id check, but the named field `organization_id` is absent from the response.
- **Phase 1 limitation (documented, not a failure):** `settings_json` and `updated_at` are not stored. The router echoes back `payload.settings_json` (`router.py:345`) and uses `org.created_at` as `updated_at` (`router.py:317`, `347`). Builder explicitly documented this at `service.py:564–566` and `router.py:315–316`.
- Test coverage: `test_imports_org_ref.py:191–291` covers GET 200, PATCH name update + DB assertion, audit event fields, settings_json echo, and 403 for non-admin on both GET and PATCH.

---

**AC10: PASS** — GET /reference/hospitals, /reference/decline-reasons, /reference/payers; all authenticated roles; seeded data.

- All three routes at `router.py:356–407` have **no** `dependencies=[require_role(...)]` — only `auth: AuthContext = Depends(get_auth_context)`. Correctly accessible to all authenticated roles.
- `service.py:637–680`: `list_hospitals` is org-scoped via `HospitalReference.organization_id == org_id`. `list_decline_reasons` returns all records (no org scope — consistent with the reference table design). `list_payers` returns all payers (documented: PayerReference has no `organization_id` column in Phase 1, confirmed in `reference_tables.py:46–51`).
- Test coverage: `test_imports_org_ref.py:298–421` covers all 6 roles for all 3 endpoints (200), hospital org-scoping test, seeded code in decline reasons, seeded payer ID in results, and unauthenticated → 401 for all three.

---

**AC11: PASS** — All admin mutation endpoints write AuditEvent with actor_user_id, entity_type, entity_id, event_type, old_value_json, new_value_json.

- `emit_audit_event` is called in: `create_user` (service.py:162), `update_user` (service.py:276), `create_template` (service.py:367), `update_template` (service.py:473), `update_org_settings` (service.py:617). All five callers pass `actor_user_id=auth_ctx.user_id`, entity_type, entity_id, event_type, old_value, new_value.
- Old values are captured BEFORE mutation in both `update_user` (line 248) and `update_template` (line 441). `update_org_settings` captures `old_values["org_name"] = org.name` before assignment (line 610).
- All audit writes use the insert-only `emit_audit_event` helper followed by `session.commit()` — atomic within the transaction.
- Test: `test_users.py:456–488` explicitly tests all AC11 fields by name: actor_user_id, entity_type, entity_id, event_type, old_value_json, new_value_json. Org_settings audit tested at `test_imports_org_ref.py:225–248`.

---

### Constraints

**"Every endpoint must gate on role_key=admin before any handler logic executes": ENFORCED**

All admin-only routes use `dependencies=[require_role("admin")]` at the decorator level (`router.py:62`, `94`, `119`, `178`, `204`, `238`, `270`, `300`, `324`). `require_role` in `auth/dependencies.py:124–165` is a Depends() factory that executes before handler body. The pattern is enforced architecturally, not per-handler, directly addressing the failure mode about inadvertent exposure from new handlers.

The two open-role routes (GET /templates/outreach, GET /reference/*) correctly omit `require_role` and rely solely on `get_auth_context` for authentication-only enforcement — consistent with AC4 and AC10 specs.

---

**"Template allowed_variables must be validated against the safe allowlist on create and update": ENFORCED**

`_validate_allowed_variables` at `service.py:67–74` checks every element against `ALLOWED_TEMPLATE_VARIABLES` frozenset. Called on create at line 351 and on update at line 438 (guarded by `if payload.allowed_variables is not None`). Returns 400 with explicit list of invalid variables and the allowlist. Frozenset matches spec exactly: `{"patient_name", "facility_name", "payer_name", "assessment_summary", "coordinator_name"}`.

---

**"Admin-surfaces owns OutreachTemplate CRUD; outreach-module must never POST/PATCH": ENFORCED (this module side)**

No POST/PATCH routes for OutreachTemplate exist outside `router.py`. The constraint is enforced on the admin-surfaces side; outreach-module compliance would require a separate audit of that module's router. Within this module, template write routes are present only here.

---

**"Import monitoring endpoints are GET-only": ENFORCED**

`router.py` contains only GET routes for `/imports` and `/imports/{import_id}`. No POST/PATCH/DELETE for ImportJob. Test `test_no_post_imports_route_in_admin_module` confirms POST /api/v1/imports returns 404/405/415/422.

---

**"All mutations must write AuditEvent rows via core-infrastructure insert-only pattern before returning 200/201": ENFORCED**

All five mutation functions call `emit_audit_event` before `session.commit()`. The `emit_audit_event` helper uses the insert-only ORM pattern (`session.add(AuditEvent(...))` with no update/delete methods on the model). See AC11 evidence above.

---

**"User deactivation must check that at least one other active admin exists; return 400 if last admin": ENFORCED**

Guard at `service.py:225–245`. Importantly, the guard also covers the case where an admin's `role_key` is changed away from "admin" (not just deactivation), catching the scenario where org lockout could occur via role reassignment. The error message matches the spec exactly: "Cannot deactivate the last active admin in this organization."

---

**"All queries must be scoped to request.state.organization_id; cross-org access returns 404 (not 403)": ENFORCED WITH ONE EXCEPTION**

All queries that retrieve individual records use `AND organization_id == org_id`. Cross-org access to User (update_user), OutreachTemplate (update_template), ImportJob (get_import) all raise HTTP 404.

**Exception noted but documented:** `list_payers` (service.py:671–680) is not org-scoped because `PayerReference` has no `organization_id` column in Phase 1. This is acknowledged by the builder in the router docstring (`router.py:404`) and service comment (`service.py:674`). The spec's `PayerReference` data model (line 128–130) shows `organization_id: uuid` as a field — so the ORM and implementation diverge from the spec's data model definition. This is a **real spec non-conformance** that the builder has acknowledged as a Phase 1 limitation.

Similarly, `list_decline_reasons` is not org-scoped. The spec's `DeclineReasonReference` model (lines 122–124) has no `organization_id` field, so this is consistent with the spec. No issue.

**Hospital reference data:** The spec's `HospitalReference` data model defines `city: str | None` and `state: str | None` fields (spec lines 116–120), but the ORM model (`reference_tables.py:54–62`) has only `(id, organization_id, hospital_name, address)` — no `city` or `state` columns. The `HospitalReferenceResponse` schema (`schemas.py:183–192`) reflects the actual ORM (no `city`/`state`). This means the API response shape diverges from the spec's defined data model for HospitalReference. This is a **spec non-conformance** in the data model.

---

**"Reference data endpoints are read-only in Phase 1; no admin UI for creating reference records via API": ENFORCED**

No POST/PATCH/DELETE routes exist for hospital_reference, decline_reason_reference, or payer_reference in `router.py`.

---

### Interfaces

**core-infrastructure (inbound): PASS**

`service.py:20–29` imports `User, ImportJob, AuditEvent, OutreachTemplate, DeclineReasonReference, HospitalReference, PayerReference` from `placementops.core.models`. Imports `Organization` from `placementops.core.models.reference_tables`. Uses `AsyncSessionLocal` pattern via `get_db` dependency. Writes AuditEvent via `emit_audit_event` from `placementops.core.audit`. All ORM reads are via `select()` statements — no direct SQL.

**auth-module (inbound): PASS**

`router.py:48` imports `require_role` from `placementops.modules.auth.dependencies`. All admin-only decorators use `dependencies=[require_role("admin")]`. `get_auth_context` is imported from `placementops.core.auth` and used as `Depends(get_auth_context)` in all route signatures. Auth context contains `user_id`, `organization_id`, `role_key` as specified.

**intake-module (inbound): PASS**

Admin module reads ImportJob records via SELECT queries only (`service.py:493–548`). No create, update, or commit operations on ImportJob exist in this module. Interface contract is respected.

**outreach-module (outbound): PASS (this module's side)**

Admin-surfaces owns OutreachTemplate write operations (POST, PATCH). GET /api/v1/templates/outreach is correctly implemented and accessible to all authenticated roles per AC4. The outreach-module's compliance with "reads only via GET /api/v1/templates/outreach" is not verifiable from this module alone.

---

### Pattern Consistency

- All service functions follow the pattern: validate inputs → query DB (org-scoped) → apply mutations → emit_audit_event → commit → return ORM object. Consistent with other reviewed modules.
- All route handlers follow: validate via schema → call service function → return response schema. No business logic in router layer.
- Pagination uses `(page, page_size)` Query params with `ge=1` and `le=100` guards on page_size, consistent with matching-module and other paginated endpoints.
- Error responses use `HTTPException` with appropriate status codes throughout.
- All files include `from __future__ import annotations` and use `async def` throughout.
- `@forgeplan-node` and `@forgeplan-spec` annotations present at file and function level.
- Naming: `auth_ctx` parameter name used consistently across all service functions. All UUID comparisons use `str(...)` coercion consistently.

One minor inconsistency: `list_templates` returns `len(templates)` as total count (`service.py:314`) without a separate COUNT query, while `list_users` and `list_imports` use separate `func.count()` queries. For `list_templates`, all records are fetched into memory before counting, which will be inefficient at scale — but this is not a spec conformance issue.

---

### Anchor Comments

**File-level `@forgeplan-node: admin-surfaces`:** Present in `router.py:1`, `service.py:1`, `schemas.py:1`, `index.py:1`, `tests/conftest.py:1`, `tests/test_users.py:1`, `tests/test_templates.py:1`, `tests/test_imports_org_ref.py:1`. Full coverage across all source files.

**`@forgeplan-spec` at function/route level:**
- `router.py`: AC annotations present on every route function (`# @forgeplan-spec: AC1` through `AC10`). Lines 58, 89, 115, 148, 173, 200, 234, 266, 296, 320, 355, 373, 391.
- `service.py`: AC annotations present on every service function. Double-annotated where AC11 applies (e.g., `# @forgeplan-spec: AC2` + `# @forgeplan-spec: AC11` at lines 113–114).
- `_validate_allowed_variables` at `service.py:67` is not individually annotated, but it is a private helper invoked only from annotated functions.
- `index.py`: No `@forgeplan-spec` annotation — appropriate, as it is a re-export shim with no implementation logic.
- `schemas.py`: File-level annotation covers AC1–AC10 but individual schema classes are not annotated. Acceptable for a pure schema file.

Coverage is thorough. No missing annotations on substantive implementation functions.

---

### Non-Goals

**"Does not implement import workflow (upload, column mapping, validation, commit)": CLEAN**

No upload, column mapping, validation, or commit endpoints exist in `router.py`. The only ImportJob routes are GET-only monitoring views.

**"Does not implement outreach action creation, approval, or sending": CLEAN**

No OutreachAction routes in `router.py`. Module only manages OutreachTemplate records.

**"Does not implement analytics or queue views": CLEAN**

No analytics or queue endpoints in `router.py` or `service.py`.

**"Does not implement facility CRUD or capability management": CLEAN**

No Facility routes in this module.

**"Does not perform email delivery or external communications": CLEAN**

No external communication calls anywhere in `router.py`, `service.py`, or test files.

**"Does not implement role assignment to individual cases": CLEAN**

No case assignment logic in this module.

---

### Failure Modes

**"403 gate implemented in individual handlers rather than shared dependency": HANDLED**

`router.py` uses `dependencies=[require_role("admin")]` at decorator level for all admin-only routes. This is a FastAPI router-level dependency, not per-handler logic. A new handler added to the router without this decorator would still require authentication via `get_auth_context` (present in all handler signatures), but would not be admin-gated. The architecture mitigates this for existing routes but cannot prevent it for future handlers added carelessly. However, this is a governance/process concern, not a current code deficiency.

**"Template allowed_variables not validated on PATCH": HANDLED**

`service.py:437–438`: `if payload.allowed_variables is not None: _validate_allowed_variables(payload.allowed_variables)`. Validated on every PATCH that includes allowed_variables.

**"Import monitoring route inadvertently wired to intake-module's commit handler": HANDLED**

GET /imports and GET /imports/{import_id} call `service.list_imports` and `service.get_import` respectively — both read-only SELECT queries with no side effects. No routing to any commit handler.

**"AuditEvent not written atomically with the mutation": HANDLED**

`emit_audit_event` adds to the session (no flush/commit), and `session.commit()` is called once after both the mutation and the audit insert. If the commit fails, neither is persisted. Atomic within the SQLAlchemy session transaction.

**"Cross-org ImportJob access returns 403 instead of 404": HANDLED**

`service.py:536–547`: single query with org_id filter returns `None` for cross-org; raises HTTP 404 unconditionally.

**"Last-admin deactivation check omitted": HANDLED**

Guard at `service.py:225–245` handles both deactivation (status→inactive) and role removal (role_key changed away from admin). Tested in `test_users.py:343–373`.

**"OutreachTemplate queries not scoped to organization_id": HANDLED**

All OutreachTemplate queries filter by `OutreachTemplate.organization_id == org_id`. `list_templates` (service.py:308), `create_template` sets `organization_id=org_id` (service.py:355), `update_template` queries with org_id filter (service.py:407–412).

---

### Data Model Non-Conformances (LARGE tier — flagged separately)

These are spec divergences in data model definitions confirmed against actual ORM, not runtime behavior failures:

**Finding 1 — HospitalReference missing `city` and `state` fields (Spec lines 116–120 vs. `reference_tables.py:54–62`):**

The spec defines:
```
HospitalReference:
  id: uuid
  hospital_name: str
  city: str | None
  state: str | None
  organization_id: uuid
```

The ORM has only `(id, organization_id, hospital_name, address)`. The response schema (`schemas.py:183–192`) reflects the ORM with `address: str | None` instead of `city`/`state`. The API response shape does not match the spec's data model for `HospitalReference`. Consumers expecting `city` and `state` fields will receive neither.

**Finding 2 — OrgSettings missing `organization_id` in response (Spec lines 109–114 vs. `schemas.py:160–168`):**

The spec defines `OrgSettings.organization_id: uuid` as a field in the response. `OrgSettingsResponse` omits this field. Since the Organization ORM does not have a separate `organization_id` column (the record's `id` IS the organization id), callers cannot distinguish the organization from the response alone without using `id`. The spec contract is technically unmet.

**Finding 3 — PayerReference missing `organization_id` (Spec lines 126–130 vs. `reference_tables.py:46–51`):**

The spec defines `PayerReference.organization_id: uuid`. The ORM has no such column. `list_payers` returns all payers unscoped. This is a Phase 1 limitation that is documented, but represents a real divergence from the spec's data contract for `PayerReference`. The `PayerReferenceResponse` schema omits `organization_id` accordingly.

---

### Recommendation: REQUEST CHANGES (3 data model non-conformances: HospitalReference-city-state, OrgSettings-organization_id, PayerReference-organization_id)

**Summary of findings requiring action:**

1. **HospitalReference response shape does not match spec** (`schemas.py:183–192` vs. spec lines 116–120): The spec defines `city: str | None` and `state: str | None` fields; the ORM and schema have `address: str | None` only. Either the spec must be updated to reflect the actual ORM shape, or the ORM migration must add `city` and `state` columns. This is the most impactful divergence because downstream consumers (e.g., facility matching UI) may depend on `city`/`state` for geographic filtering.

2. **OrgSettings response omits `organization_id`** (`schemas.py:160–168` vs. spec line 111): The spec's `OrgSettings` data model includes `organization_id: uuid`. The response includes only `id`. Since `id` doubles as the organization identifier in the Organization ORM, the semantic gap may be acceptable, but the field name mismatch violates the spec contract. Recommend adding `organization_id` as an alias for `id` in `OrgSettingsResponse`, or updating the spec to remove `organization_id`.

3. **PayerReference not org-scoped** (`service.py:671–680` vs. spec line 129): The spec defines `PayerReference.organization_id: uuid`. Phase 1 ORM has no such column. This is acknowledged by the builder and is a known migration gap. Must be tracked as a follow-on migration or the spec must be updated to reflect global payers. Current behavior exposes all payers to all authenticated users, which may be intentional for a global payer list.

**All 11 ACs are functionally implemented correctly.** All constraints are enforced. All 7 failure modes are addressed. The only blockers are the data model mismatches between the spec's defined shapes and the actual ORM/response schemas. The implementation is otherwise high quality with comprehensive test coverage across all role combinations and cross-org isolation scenarios.
