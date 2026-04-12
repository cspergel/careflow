## Review: core-infrastructure
**Date:** 2026-04-11T00:00:00Z
**Reviewer:** Claude Sonnet 4.6
**Review type:** native
**Cycle:** 1

---

### Acceptance Criteria

- **AC1: PASS** — `alembic/versions/0001_initial_tables.py` creates 19 tables via `op.create_table()`: `organizations`, `user_roles`, `payer_reference`, `decline_reason_reference`, `hospital_reference`, `users`, `patient_cases`, `facilities`, `facility_capabilities`, `facility_insurance_rules`, `facility_contacts`, `outreach_templates`, `outreach_actions`, `clinical_assessments`, `facility_matches`, `import_jobs`, `placement_outcomes`, `audit_events`, `case_status_history`. All columns, types, FK constraints, and indexes match ORM model definitions. Composite indexes `ix_patient_cases_org_status` and `ix_patient_cases_active` are created. All 14 ORM model classes exist in `placementops/core/models/`. `alembic/env.py` imports all models to populate `Base.metadata` and uses `DATABASE_DIRECT_URL` exclusively.

- **AC2: PASS** — `main.py:52-60` registers `GET /api/v1/health` returning `{"status": "ok", "service": "placementops-api"}` with HTTP 200. `database.py:33-45` creates the async engine with `NullPool` and `expire_on_commit=False`. App starts via the `lifespan` context manager.

- **AC3: PARTIAL FAIL** — `auth.py` correctly handles both HS256 (lines 104-134) and ES256 (lines 74-103) token paths. Expired tokens raise 401 (lines 92-96, 123-127). Missing Authorization header raises 401 (middleware.py line 191-196). However, **AC3d is not tested**: the spec's test field explicitly requires `(d) if SUPABASE_JWKS_URL set, send request with valid ES256 JWT and assert AuthContext populated`. No test exists in `tests/core/test_auth_middleware.py` that exercises the ES256 code path (grep across all test files confirms zero matches for `ES256`, `jwks`, or `JWKS`). The implementation code is present but the ES256 path is untested.

- **AC4: PASS** — `auth.py:207-220` implements `require_org_match()` which raises HTTP 403 when `auth.organization_id != resource_org`. `test_tenant_isolation.py` tests the 403 path and verifies no org B data is leaked in the response body (lines 29-53, 68-112).

- **AC5: PASS** — `alembic/versions/0002_rls_policies.py` enables RLS and `FORCE ROW LEVEL SECURITY` on all 8 PHI tables (lines 52-54). SELECT, INSERT, and UPDATE policies all use `auth.jwt() -> 'app_metadata' ->> 'organization_id'` (lines 57-93). UPDATE policies include both `USING` and `WITH CHECK` clauses. Every UPDATE-capable table (all except `audit_events` and `placement_outcomes`) has a corresponding SELECT policy — the constraint about SELECT + UPDATE pair is satisfied. RLS uses `app_metadata` not `user_metadata` throughout.

- **AC6: PASS** — `state_machine.py:99-226` implements `transition_case_status()`. Step 2 (lines 142-155) checks the allowlist and raises HTTP 400 with `allowed_transitions` list. Step 3 (lines 157-168) checks `actor_role` against `permitted_roles` and raises HTTP 403. Step 5 (lines 176-185) inserts a `CaseStatusHistory` row. Tests in `test_transitions.py` cover all three sub-scenarios: invalid transition → 400 (line 21-40), wrong role → 403 (line 43-63), valid transition → success with committed state change (line 66-82). `test_valid_transition_writes_case_status_history` at line 85 confirms the history row.

- **AC7: PASS** — `alembic/versions/0002_rls_policies.py:34-48` creates `audit_events_immutable` PL/pgSQL trigger function and attaches it `BEFORE UPDATE OR DELETE ON audit_events FOR EACH ROW`. The `AuditEvent` ORM class (`models/audit_event.py`) has no `update()` or `delete()` class methods. Tests in `test_audit_immutability.py` check `not hasattr(AuditEvent, 'update')` and `not hasattr(AuditEvent, 'delete')` (lines 22-33). Postgres-level tests for the trigger are marked `@pytest.mark.postgres_required` and are correctly deferred.

- **AC8: PARTIAL FAIL** — AC8 requires AuditEvent rows for (a) case status changes, (b) outreach_action approval/send, and (c) user management actions. (a) is fully implemented: `state_machine.py:188-198` inserts `AuditEvent(event_type="status_changed")` on every transition, and `test_audit_events.py` verifies it. **(b) and (c) are not implemented**: no code in `placementops/core/` inserts an AuditEvent for `outreach_approved` or any user management action (`user_created`, `user_updated`, `user_deactivated`). `test_audit_events.py:75-91` tests `outreach_approved` only as a manually inserted AuditEvent (a direct `session.add(AuditEvent(...))` call) — it does not test that any business-logic function emits such an event. No `user_created` test or implementation exists anywhere in the node's file scope.

- **AC9: PASS** — `events.py:63-85` implements `publish_case_activity_event()`. `CaseActivityEvent` dataclass (lines 25-40) includes all required fields: `actor_user_id`, `event_type`, `old_status`, `new_status`, `occurred_at` (with `timezone.utc` default). `state_machine.py:213-224` publishes the event after commit. `test_activity_events.py:49-78` asserts all five required fields are present.

- **AC10: PARTIAL FAIL** — `alembic/versions/0003_seed_data.py` calls `seed_all(op)` which seeds 6 roles, decline reasons, payers, and a demo org/hospital. **The `_seed_payers()` function at `alembic/seed.py:102-118` is NOT idempotent**: it inserts 5 payer rows using raw `INSERT INTO ... VALUES (...)` with no `ON CONFLICT DO NOTHING` clause. The comment at line 5 says "Idempotent: uses INSERT ... ON CONFLICT DO NOTHING where possible" but `_seed_payers` omits it. Running `alembic upgrade head` twice against the same database will fail with a duplicate key error on `payer_reference`. The 6 roles (line 30-78), decline reasons (line 81-99), and demo org/hospital (lines 121-137) are all idempotent. Only `_seed_payers` is defective.

- **AC11: PASS** — `middleware.py:91-127` implements `check_case_not_closed()` as a FastAPI `Depends()` factory. The dependency queries the PatientCase and raises HTTP 409 before the handler executes (lines 120-125). `test_closed_case.py:80-91` verifies via `handler_call_count` counter that the handler body is never entered when the guard fires. Both PATCH and POST child-entity scenarios are tested.

- **AC12: PASS** — `auth.py:153-154` reads `app_metadata = payload.get("app_metadata") or {}` and `org_id_str = app_metadata.get("organization_id")`. There is no reference to `user_metadata` anywhere in `auth.py`. `test_org_metadata_source.py` tests three scenarios: org in user_metadata only → 401 (line 17-26), org in app_metadata → 200 (line 29-38), user_metadata present but no app_metadata org → 401 (line 41-51).

---

### Constraints

- **"Use PyJWT[cryptography] for JWT validation — NOT python-jose"**: ENFORCED — `requirements.txt:12` specifies `PyJWT[cryptography]==2.10.1`. `python-jose` is absent from `requirements.txt`. `auth.py` imports `jwt` (PyJWT).

- **"JWT middleware must handle both HS256 and ES256"**: ENFORCED — `auth.py:72-134` branches on `alg` header field. HS256 uses `SUPABASE_JWT_SECRET`; ES256 uses `PyJWKClient`. However, the ES256 test path is absent (see AC3 finding).

- **"organization_id MUST be extracted from app_metadata in the JWT claims, never from user_metadata"**: ENFORCED — `auth.py:153-154` reads exclusively from `app_metadata`. No reference to `user_metadata` in the file.

- **"AsyncSessionLocal must be created with expire_on_commit=False"**: ENFORCED — `database.py:41-45` sets `expire_on_commit=False` with an explanatory comment.

- **"Application pool must use NullPool and statement_cache_size=0"**: ENFORCED — `database.py:35` sets `poolclass=NullPool`; lines 27-31 set `statement_cache_size=0` and `prepared_statement_cache_size=0` when the driver is PostgreSQL.

- **"Alembic migrations must use DATABASE_DIRECT_URL (port 5432)"**: ENFORCED — `alembic/env.py:56` reads `os.environ["DATABASE_DIRECT_URL"]` and uses it for all migration connections. `DATABASE_URL` (port 6543) is never referenced in `env.py`.

- **"AuditEvent ORM model must expose no update() or delete() methods"**: ENFORCED — `models/audit_event.py` has no `update()` or `delete()` methods at the class or instance level. Only `session.add()` is the documented write path.

- **"RLS UPDATE policies must have a corresponding SELECT policy; both must use auth.jwt() -> 'app_metadata'"**: ENFORCED — `0002_rls_policies.py` creates SELECT policies for all 8 PHI tables (line 57-65) and UPDATE policies for 6 of them (excluding `audit_events` and `placement_outcomes`, line 79). All policy expressions reference `app_metadata`.

- **"transition_case_status handler is the single authoritative gatekeeper"**: ENFORCED at this node — all status mutations route through `state_machine.transition_case_status()`. However, because downstream feature modules have not been built yet, there is no evidence that other modules bypass it. This constraint can only be fully verified when feature modules are implemented.

- **"Closed-case guard must execute before handler logic"**: ENFORCED — `check_case_not_closed()` is a FastAPI `Depends()` that runs before the route handler body. `test_closed_case.py:80-91` proves via counter that the handler body is never reached.

---

### Interfaces

- **auth-module (outbound)**: PASS — `AuthContext` dataclass exported from `auth.py`. `get_auth_context` Depends() callable exported. `User` ORM model and `AsyncSessionLocal` exported from `models/__init__.py` and `database.py` respectively.

- **intake-module (outbound)**: PASS — `PatientCase`, `ImportJob` ORM models exported. `transition_case_status` exported from `state_machine.py`. `publish_case_activity_event` exported from `events.py`. `AsyncSessionLocal` and `get_auth_context` exported.

- **clinical-module (outbound)**: PASS — `ClinicalAssessment`, `PatientCase` exported. `transition_case_status`, `publish_case_activity_event`, `AsyncSessionLocal`, `get_auth_context` all available.

- **facilities-module (outbound)**: PASS — `Facility`, `FacilityCapabilities`, `FacilityInsuranceRule`, `FacilityContact` all exported from `models/__init__.py`. `AsyncSessionLocal`, `get_auth_context` available.

- **matching-module (outbound)**: PASS — `FacilityMatch`, `ClinicalAssessment`, `Facility`, `FacilityCapabilities`, `FacilityInsuranceRule` all exported. `transition_case_status`, `AsyncSessionLocal`, `get_auth_context` available.

- **outreach-module (outbound)**: PASS — `OutreachAction`, `OutreachTemplate`, `FacilityContact` exported. `transition_case_status`, `AsyncSessionLocal`, `get_auth_context` available.

- **outcomes-module (outbound)**: PASS — `PlacementOutcome`, `PatientCase` exported. `transition_case_status`, `AsyncSessionLocal`, `get_auth_context` available.

- **analytics-module (outbound)**: PASS — All ORM models are available via `from placementops.core.models import *` / explicit imports. `AsyncSessionLocal` available for read-only queries.

- **admin-surfaces (outbound)**: PASS — `User`, `ImportJob`, `AuditEvent`, and all reference table ORM models (`Organization`, `UserRole`, `DeclineReasonReference`, `PayerReference`, `HospitalReference`) exported. `AsyncSessionLocal`, `get_auth_context` available.

---

### Pattern Consistency

This is the first node delivered; there are no prior completed nodes to compare against for cross-node pattern consistency. Within the node:

- All source files begin with `# @forgeplan-node: core-infrastructure` and use `# @forgeplan-spec: ACN` annotations on relevant functions.
- ORM models follow a consistent pattern: `String(36)` for UUID PKs with `default=lambda: str(uuid4())`, `server_default=func.now()` for timestamps, `index=True` on FK columns used in WHERE clauses.
- `Mapped[str]` is used consistently for UUID columns (stored as strings) rather than native `UUID` types — this is intentional for SQLite test compatibility.
- Async patterns are consistent: `async_sessionmaker`, `AsyncSession`, `await session.execute(...)`.
- HTTP exception patterns are consistent: `HTTPException(status_code=..., detail=...)`.

---

### Anchor Comments

**Source files with `# @forgeplan-node: core-infrastructure`:**
- `placementops/core/__init__.py`: PRESENT (line 1)
- `placementops/core/auth.py`: PRESENT (line 1)
- `placementops/core/database.py`: PRESENT (line 1)
- `placementops/core/events.py`: PRESENT (line 1)
- `placementops/core/middleware.py`: PRESENT (line 1)
- `placementops/core/state_machine.py`: PRESENT (line 1)
- `placementops/core/models/__init__.py`: PRESENT (line 1)
- `placementops/core/models/audit_event.py`: PRESENT (line 1)
- `placementops/core/models/case_status_history.py`: PRESENT (line 1)
- `placementops/core/models/clinical_assessment.py`: PRESENT (line 1)
- `placementops/core/models/facility.py`: PRESENT (line 1)
- `placementops/core/models/facility_capabilities.py`: PRESENT (line 1)
- `placementops/core/models/facility_contact.py`: PRESENT (line 1)
- `placementops/core/models/facility_insurance_rule.py`: PRESENT (line 1)
- `placementops/core/models/facility_match.py`: PRESENT (line 1)
- `placementops/core/models/import_job.py`: PRESENT (line 1)
- `placementops/core/models/outreach_action.py`: PRESENT (line 1)
- `placementops/core/models/outreach_template.py`: PRESENT (line 1)
- `placementops/core/models/patient_case.py`: PRESENT (line 1)
- `placementops/core/models/placement_outcome.py`: PRESENT (line 1)
- `placementops/core/models/reference_tables.py`: PRESENT (line 1)
- `placementops/core/models/user.py`: PRESENT (line 1)
- `main.py`: PRESENT (line 1)
- `alembic/env.py`: PRESENT (line 1)
- `alembic/seed.py`: PRESENT (line 1)
- `alembic/versions/0001_initial_tables.py`: PRESENT (line 1)
- `alembic/versions/0002_rls_policies.py`: PRESENT (line 1)
- `alembic/versions/0003_seed_data.py`: PRESENT (line 1)
- All `tests/core/` Python files: PRESENT (verified in all read files)

**`# @forgeplan-spec:` coverage on major functions:**
- `_decode_token()` in `auth.py`: PRESENT (lines 13, 75, 105)
- `_extract_auth_context()` in `auth.py`: PRESENT (line 152 for AC12)
- `require_org_match()` in `auth.py`: PRESENT (line 214)
- `AsyncSessionLocal` and `get_auth_context` in `database.py`: PRESENT (lines 21, 40)
- `publish_case_activity_event()` in `events.py`: PRESENT (lines 10, 71)
- `check_case_not_closed()` in `middleware.py`: PRESENT (lines 10, 112)
- `transition_case_status()` in `state_machine.py`: PRESENT (lines 12-14, 126, 188, 213)
- `AuditEvent` model: PRESENT (lines 10-11)

Coverage is thorough. No missing anchor comments found.

---

### Non-Goals

- **"Does not implement any business-logic endpoints beyond GET /api/v1/health"**: CLEAN — `main.py` registers only the health endpoint. No feature endpoints are included.
- **"Does not send emails, SMS, or any external communications"**: CLEAN — no email/SMS libraries or calls found in any file within the node scope.
- **"Does not implement the matching scoring algorithm"**: CLEAN — `state_machine.py` handles only status transitions; no scoring logic is present.
- **"Does not implement the frontend or any UI components"**: CLEAN — no HTML, React, or frontend code found.

---

### Failure Modes

- **"org_id extracted from user_metadata instead of app_metadata"**: HANDLED — `auth.py:153-154` reads only `app_metadata`. `_extract_auth_context()` raises 401 if `app_metadata.organization_id` is absent, regardless of what `user_metadata` contains. Tests in `test_org_metadata_source.py` verify this hard boundary.

- **"ES256/JWKS validation not implemented"**: HANDLED in implementation — `auth.py:74-103` implements the ES256 path via `PyJWKClient`. However, this code path has **zero test coverage** (no ES256 test token is minted anywhere in `tests/core/`). The failure mode is addressed at the code level but is unverified by the test suite.

- **"NullPool not configured"**: HANDLED — `database.py:35` sets `poolclass=NullPool`. `statement_cache_size=0` and `prepared_statement_cache_size=0` are set in `connect_args` for PostgreSQL connections (lines 27-31).

- **"AuditEvent trigger not created in migration"**: HANDLED — `0002_rls_policies.py:34-48` creates both the trigger function and the trigger. The trigger covers `BEFORE UPDATE OR DELETE ON audit_events FOR EACH ROW`.

- **"RLS SELECT policy missing on a table that has UPDATE policy"**: HANDLED — Every table that has an UPDATE policy in `0002_rls_policies.py` also has a SELECT policy (the loop creates SELECT first, then INSERT, then UPDATE conditionally). The pairing is correct.

- **"transition_case_status handler not invoked by a module"**: PARTIALLY HANDLED — The handler exists and is the only status-mutation path in this node. Downstream module enforcement cannot be verified until those modules exist.

- **"expire_on_commit=True (default)"**: HANDLED — `database.py:44` explicitly sets `expire_on_commit=False` with a comment explaining why.

- **"Alembic using transaction-mode pool URL"**: HANDLED — `alembic/env.py:56` uses `os.environ["DATABASE_DIRECT_URL"]` (hard requirement — raises `KeyError` if absent). The transaction-mode `DATABASE_URL` is never referenced in migration code.

---

### Summary of Failures

| # | AC/Constraint | File | Issue |
|---|---------------|------|-------|
| 1 | AC3 (partial) | `tests/core/test_auth_middleware.py` | AC3d missing: no test exercises the ES256 code path. The spec's test field explicitly requires this as sub-scenario (d). |
| 2 | AC8 (partial) | `placementops/core/` (entire scope) | AuditEvent writes for `outreach_action` approval/send and user management actions are not implemented. `state_machine.py` only writes `status_changed` events. No function in scope emits `outreach_approved` or `user_created` audit rows. |
| 3 | AC10 (partial) | `alembic/seed.py:102-118` | `_seed_payers()` lacks `ON CONFLICT DO NOTHING`, breaking idempotency. Running `alembic upgrade head` twice fails with a duplicate key violation on `payer_reference`. |

---

### Recommendation: REQUEST CHANGES (3 failures: AC3-ES256-test-missing, AC8-outreach/user-audit-missing, AC10-payer-seed-not-idempotent)

**Required fixes before APPROVE:**

1. **AC3d — Add ES256 test** (`tests/core/test_auth_middleware.py`): Add a test that mints an ES256 JWT using a locally generated EC key pair, configures a mock JWKS endpoint (or uses `PyJWKClient` with a local key), and asserts `AuthContext` is correctly populated. This is explicitly required by the spec's test field.

2. **AC8 — Implement outreach and user management audit writes** (`placementops/core/`): The spec requires AuditEvent rows for every outreach_action approval/send and every user management action. Currently, no code in this node emits those events. Either:
   - Add audit-write helpers (e.g., `write_outreach_audit_event()`, `write_user_audit_event()`) that downstream modules can call, OR
   - Define these as explicit callsites in state_machine.py or a new audit helper module.
   Note: the spec says this criterion belongs to core-infrastructure (the node providing the audit mechanism and shared utilities). The outreach-module and admin-surfaces may invoke the writes, but the write capability must originate here.

3. **AC10 — Fix `_seed_payers()` idempotency** (`alembic/seed.py:113`): Change the INSERT statement inside `_seed_payers()` to include `ON CONFLICT (payer_name) DO NOTHING` (or add a unique constraint on `payer_name` and use `ON CONFLICT`). Currently the payer_reference table has no unique constraint on payer_name — if a unique constraint is needed, add it in a migration first.
