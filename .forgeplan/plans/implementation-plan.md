# PlacementOps — Implementation Plan

**Tier:** LARGE
**Generated:** 2026-04-10 (v2 — post plan-review-pass-1 fixes)
**Status:** Ready for Build Phase
**Design Review:** PASSED (4 passes, 0 open CRITICALs)
**Plan Review Pass 1:** 11 CRITICALs fixed; see `.forgeplan/reviews/plan-review-pass-1.md`

---

## 1. Project Summary

PlacementOps is a HIPAA-regulated, post-acute care placement operating system that replaces
spreadsheets and manual phone trees for offshore intake staff, clinical reviewers, placement
coordinators, and managers. The end-to-end workflow is:

> Hospital census intake → structured clinical review → weighted facility matching →
> staff-approved outreach → outcome tracking

The system enforces strict multi-tenancy (organization_id isolation at application middleware
and Supabase RLS), a 14-state case machine with formal transition allowlist, and immutable
audit trail for every case status change and outreach event.

### Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 (backend), TypeScript (frontend) |
| API framework | FastAPI (async) |
| ORM | SQLAlchemy 2.0 async + asyncpg driver |
| Migrations | Alembic (async bridge via run_sync) |
| Database | Supabase PostgreSQL |
| Auth | Supabase Auth + PyJWT[cryptography] |
| Background jobs | FastAPI BackgroundTasks |
| Frontend | Next.js 14 App Router |
| UI library | shadcn/ui + Tailwind v4 (tw-animate-css) |
| Table | TanStack Table v8 |
| URL state | nuqs |
| Forms | react-hook-form v7 + Zod |
| API client | @hey-api/openapi-ts (typed, generated from OpenAPI spec) |
| Deployment | Docker |
| Tests | pytest + pytest-asyncio (backend), Jest/RTL + Playwright (frontend) |

---

## 2. Node Build Order

The dependency graph mandates this sequence. Nodes within the same phase may be built in
parallel by separate agents.

```
Phase 1 (Foundation):
  [1] core-infrastructure    (no deps — builds first)
  [2] auth-module            (depends on: core-infrastructure)

Phase 2 (Data layer):
  [3a] facilities-module     (depends on: core-infrastructure, auth-module)
  [3b] intake-module         (depends on: core-infrastructure, auth-module)
  [4]  clinical-module       (depends on: core-infrastructure, auth-module, intake-module)

Phase 3 (Intelligence):
  [5] matching-module        (depends on: core-infrastructure, auth-module, clinical-module, facilities-module)
  [6] outreach-module        (depends on: core-infrastructure, auth-module, matching-module)
  [7] outcomes-module        (depends on: core-infrastructure, auth-module, outreach-module)

Phase 4 (Surfaces):
  [8a] admin-surfaces        (depends on: core-infrastructure, auth-module, intake-module, outreach-module)
  [8b] analytics-module      (depends on: core-infrastructure, auth-module, outcomes-module)
  [9]  frontend-app-shell    (depends on: auth-module, intake-module, facilities-module, clinical-module,
                               matching-module, outreach-module, outcomes-module, admin-surfaces,
                               analytics-module — built last)
```

---

## 3. Node Details

### Node 1: core-infrastructure

**File scope:** `placementops/core/**`

**Build dependencies:** None — this is the first node.

**Expected files/modules:**
- `placementops/core/database.py` — AsyncSessionLocal, engine (NullPool + statement_cache_size=0 for port 6543; direct engine for Alembic port 5432), Base
- `placementops/core/models/` package — All 20+ SQLAlchemy ORM model classes with TenantMixin; includes CaseStatusHistory
- `placementops/core/auth.py` — JWT middleware (HS256 + ES256/JWKS), AuthContext dataclass, get_auth_context Depends()
- `placementops/core/state_machine.py` — transition_case_status(), state_machine_transitions allowlist dict; writes CaseStatusHistory row on every transition
- `placementops/core/events.py` — publish_case_activity_event(), case_activity_events in-process bus
- `placementops/core/middleware.py` — closed-case guard (see implementation note below); PHI-safe structured logging configuration
- `alembic/` — migrations directory with all table migrations + AuditEvent trigger migration + RLS policy migrations
- `alembic/seed.py` — 6 roles, decline_reason_reference, payer_reference, hospital_reference
- `tests/core/` — test_auth_middleware.py, test_tenant_isolation.py, test_transitions.py, test_audit_immutability.py, test_audit_events.py, test_closed_case.py, test_activity_events.py, test_env_validation.py, test_no_phi_in_logs.py

**Major responsibilities:**
- Define all SQLAlchemy ORM models (20+ tables incl. CaseStatusHistory) with organization_id on every PHI table
- JWT middleware: HS256 via SUPABASE_JWT_SECRET; ES256 via SUPABASE_JWKS_URL (`PyJWKClient(url, lifespan=300)`); read org_id from `app_metadata` NOT `user_metadata`
- Enforce state machine transition allowlist and role gates via `transition_case_status()`; write CaseStatusHistory row per transition
- AuditEvent immutability: Postgres BEFORE UPDATE OR DELETE trigger + ORM insert-only
- Alembic migrations: two URLs — port 5432 (direct) for migrations, port 6543 (Supavisor NullPool) for app
- Supabase RLS policies on all PHI tables (applied via Alembic migration or Supabase CLI)

**Key implementation notes:**

**NullPool + Supavisor (CRITICAL):**
```python
from sqlalchemy.pool import NullPool
engine = create_async_engine(
    DATABASE_URL,
    poolclass=NullPool,
    connect_args={"statement_cache_size": 0},
)
```
Without this, asyncpg's prepared statement cache conflicts with transaction-mode pooling.

**PyJWT (CRITICAL):** Use `PyJWT[cryptography]` — NOT python-jose (abandoned). `import jwt`.

**org_id extraction (CRITICAL):**
```python
org_id = payload["app_metadata"]["organization_id"]  # NEVER payload["user_metadata"]
```

**JWKS cache:**
```python
from jwt import PyJWKClient
jwks_client = PyJWKClient(SUPABASE_JWKS_URL, lifespan=300)  # 5-min TTL
# On JWKS fetch failure at startup (if SUPABASE_JWKS_URL is set): fail startup (fail-closed)
# On JWKS fetch failure during refresh: continue with cached keyset, log warning
# HS256 fallback via SUPABASE_JWT_SECRET must always be available
```

**RLS policies (must be in migration or Supabase CLI):**
```sql
ALTER TABLE patient_cases ENABLE ROW LEVEL SECURITY;
CREATE POLICY patient_cases_org_isolation ON patient_cases
  USING (organization_id = (auth.jwt() -> 'app_metadata' ->> 'organization_id')::uuid);
```
Apply RLS policy to ALL PHI tables: patient_cases, clinical_assessments, facility_matches,
outreach_actions, placement_outcomes, import_jobs, case_status_history, case_assignments,
audit_events. Verify with: `SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname='public'`

**AuditEvent trigger:**
```sql
CREATE OR REPLACE FUNCTION audit_events_immutable() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'audit_events rows are immutable'; END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER audit_events_immutable_trigger
  BEFORE UPDATE OR DELETE ON audit_events
  FOR EACH ROW EXECUTE FUNCTION audit_events_immutable();
```

**CaseStatusHistory ORM model (new — required for SLA analytics):**
```python
class CaseStatusHistory(Base, TenantMixin):
    __tablename__ = "case_status_history"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    patient_case_id: Mapped[UUID] = mapped_column(ForeignKey("patient_cases.id"), nullable=False)
    from_status: Mapped[str] = mapped_column(nullable=True)  # null for initial create
    to_status: Mapped[str] = mapped_column(nullable=False)
    actor_user_id: Mapped[UUID] = mapped_column(nullable=False)
    transition_reason: Mapped[str | None]
    entered_at: Mapped[datetime] = mapped_column(nullable=False, default=func.now())
```
`transition_case_status()` must INSERT a CaseStatusHistory row on every successful transition.
SLA analytics compute aging from `case_status_history.entered_at` via JOIN — no denormalized
`status_entered_at` field on PatientCase is needed.

**Closed-case guard implementation:**
Implement as a FastAPI `Depends()` (not middleware) — injected into every write endpoint.
For endpoints with `case_id` in path: extract directly.
For endpoints with child entity IDs (outreach_action_id, assessment_id, outcome_id): resolve
the parent case_id from the entity's `patient_case_id` FK, then check `case.current_status`.
Return HTTP 409 if `current_status == "closed"`. The guard must run before any handler logic.

**PHI-in-logs enforcement:**
Configure Python logging with a JSON formatter that excludes request body fields. Add a
`test_no_phi_in_logs.py` test that triggers error paths and asserts fields like `patient_name`,
`dob`, `mrn`, `draft_body`, `clinical_summary` do not appear in captured log output.
FastAPI's exception handlers must not serialize request bodies.

**Startup environment validation (in FastAPI lifespan event):**
Validate at startup: DATABASE_URL contains port 6543; DATABASE_DIRECT_URL contains port 5432;
SUPABASE_JWT_SECRET is non-empty; SUPABASE_URL is a valid HTTPS URL. Fail startup if any
check fails (do not start the server with invalid config).

**SUPABASE_SERVICE_ROLE_KEY usage restriction:**
Only admin-surfaces module may use SUPABASE_SERVICE_ROLE_KEY (for Supabase Auth admin API
calls). All other modules must use the anon key. Add a startup check that warns if
SERVICE_ROLE_KEY is loaded outside admin-surfaces context. Consider module-scoped config.

**`expire_on_commit=False`** is required on AsyncSessionLocal to prevent MissingGreenlet errors.

**CORS:**
```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Verification steps:**
1. `alembic upgrade head` against blank Postgres → `alembic check` shows no pending migrations
2. `SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname='public'` — all PHI tables show `rowsecurity=true`
3. `pytest tests/core/test_auth_middleware.py` — all auth scenarios pass (valid HS256, expired, missing, valid ES256)
4. `pytest tests/core/test_transitions.py` — allowlist guard and role gate tests pass; CaseStatusHistory row created per transition
5. `pytest tests/core/test_audit_immutability.py` — UPDATE/DELETE on audit_events raises DBAPIError
6. `pytest tests/core/test_tenant_isolation.py` — cross-org access returns 403; RLS returns 0 rows for wrong org

---

### Node 2: auth-module

**File scope:** `placementops/modules/auth/**`

**Build dependencies:** core-infrastructure

**Expected files/modules:**
- `placementops/modules/auth/router.py` — FastAPI router: POST /api/v1/auth/login, POST /api/v1/auth/logout, GET /api/v1/auth/me
- `placementops/modules/auth/schemas.py` — LoginRequest, LoginResponse, UserProfileResponse
- `placementops/modules/auth/service.py` — Supabase Auth client calls, user profile assembly, RBAC helpers
- `placementops/modules/auth/rate_limiter.py` — Login rate limiter (10 attempts/minute per IP)
- `tests/auth/` — test_login.py, test_rbac.py, test_rate_limiting.py

**Major responsibilities:**
- POST /api/v1/auth/login — calls Supabase Auth, returns JWT + user profile (id, email, role_key, organization_id)
- GET /api/v1/auth/me — returns current user profile from AuthContext
- POST /api/v1/auth/logout — invalidates Supabase session
- 6-role RBAC: admin, intake_staff, clinical_reviewer, placement_coordinator, manager, read_only
- Rate limiting on login: **10 attempts/minute per IP** → HTTP 429 on the 11th attempt
- read_only: view-only access to all data, no write operations permitted

**Key implementation notes:**
- Use `supabase-py` client for Supabase Auth calls; never call Supabase Auth directly from individual module endpoints.
- role_key is denormalized on user profile (`user.role_key`); user_roles lookup table exists for forward-compat.
- Login response must include `organization_id` from `app_metadata` for frontend routing.
- Rate limiter: in-memory sliding window for Phase 1 (requires single-worker deployment).
  If multi-worker: upgrade to Redis. Document this constraint.

**Verification steps:**
1. `pytest tests/auth/test_login.py` — valid credentials return JWT, invalid return 401
2. `pytest tests/auth/test_rbac.py` — read_only user cannot POST to any write endpoint
3. `pytest tests/auth/test_rate_limiting.py` — **11th** login attempt in 1 minute returns 429

---

### Node 3a: facilities-module

**File scope:** `placementops/modules/facilities/**`

**Build dependencies:** core-infrastructure, auth-module

**Expected files/modules:**
- `placementops/modules/facilities/router.py`
- `placementops/modules/facilities/schemas.py`
- `placementops/modules/facilities/service.py`
- `tests/facilities/` — test_facility_crud.py, test_capability_upsert.py, test_role_gates.py

**Major responsibilities:**
- POST/GET/PATCH /api/v1/facilities — facility CRUD (admin/placement_coordinator write; all roles read)
- PUT /api/v1/facilities/{id}/capabilities — upsert FacilityCapabilities (admin only)
- POST/PATCH /api/v1/facilities/{id}/insurance-rules — manage FacilityInsuranceRule entries
- POST /api/v1/facilities/{id}/contacts — manage FacilityContact entries
- Role gates: intake_staff = read-only; clinical_reviewer = read-only; writes require placement_coordinator or admin

**Key implementation notes:**

**FacilityInsuranceRule field:**
`accepted_status` is a **string enum (accepted | conditional | not_accepted)** — NOT a boolean flag.
This three-value enum is required because `conditional` acceptance scores 0.5 in payer_fit
(not 0 or 1), and `not_accepted` is a hard exclusion.

**Hard-exclusion field mapping (canonical — 13 total):**
The field names here are the exact ORM column names. Use these everywhere.

| FacilityCapabilities field | ClinicalAssessment field | Logic |
|---|---|---|
| `accepts_hd` | `dialysis_type == "hd"` | hard exclusion |
| `accepts_peritoneal_dialysis` | `dialysis_type == "peritoneal"` | hard exclusion |
| `in_house_hemodialysis` | `dialysis_type == "hd" AND in_house_hd_required` | **compound** — both `accepts_hd` AND `in_house_hemodialysis` must be True |
| `accepts_wound_vac` | `wound_vac_needs` | hard exclusion |
| `accepts_memory_care` | `memory_care_needed` | hard exclusion |
| `accepts_oxygen_therapy` | `oxygen_required` | hard exclusion |
| `accepts_trach` | `trach` | hard exclusion |
| `accepts_vent` | `vent` | hard exclusion |
| `accepts_bariatric` | `bariatric_needs` | hard exclusion |
| `accepts_iv_antibiotics` | `iv_antibiotics` | hard exclusion |
| `accepts_tpn` | `tpn` | hard exclusion |
| `accepts_behavioral_complexity` | `behavioral_complexity_flag` | hard exclusion |
| `accepts_isolation_cases` | `isolation_precautions` | hard exclusion |

**Note on `in_house_hemodialysis`:** When `ClinicalAssessment.in_house_hd_required=True`, the
facility must have BOTH `accepts_hd=True` AND `in_house_hemodialysis=True`. If either is false,
the facility is hard-excluded. This is a compound check, not a simple field comparison.

**Verification steps:**
1. `pytest tests/facilities/test_role_gates.py` — intake_staff PATCH to facility returns 403
2. `pytest tests/facilities/test_capability_upsert.py` — PUT idempotent (create then update same row)
3. `pytest tests/facilities/test_insurance_rules.py` — `accepted_status="not_accepted"` stored correctly

---

### Node 3b: intake-module

**File scope:** `placementops/modules/intake/**`

**Build dependencies:** core-infrastructure, auth-module

**Expected files/modules:**
- `placementops/modules/intake/router.py`
- `placementops/modules/intake/schemas.py`
- `placementops/modules/intake/service.py`
- `placementops/modules/intake/import_service.py` — BackgroundTasks pattern
- `placementops/modules/intake/file_utils.py`
- `tests/intake/` — test_case_crud.py, test_import.py, test_duplicate_detection.py, test_import_tenant_isolation.py

**Major responsibilities:**
- POST /api/v1/cases — create case (intake_staff); organization_id set from auth.organization_id (never from request body)
- GET/PATCH /api/v1/cases/{id} — read/update case; field-level permission enforcement per role
- POST /api/v1/imports — multipart file upload → ImportJob creation → BackgroundTask for processing
- GET /api/v1/imports/{id} — poll import job status
- POST /api/v1/cases/{id}/status-transition — generic status transition endpoint (delegates to transition_case_status)
- Duplicate detection: warn if `patient_name + date_of_birth + hospital_id` match existing open case

**Key implementation notes:**

**organization_id on new records (CRITICAL rule applies to ALL nodes):**
`organization_id` must be set server-side from `auth.organization_id`. It must NEVER be
accepted from request body input. Pydantic create schemas must NOT include `organization_id`.

**BackgroundTasks pattern (CRITICAL):**
```python
async def process_import(file_bytes: bytes, import_job_id: UUID, org_id: UUID):
    # MUST use a fresh session — request session is already closed
    async with AsyncSessionLocal() as session:
        async with session.begin():
            try:
                # process all rows in single transaction
                # ...
                job.status = "completed"
                job.created_count = created
                job.failed_count = failed
                job.error_detail_json = errors  # per-row errors
            except Exception as e:
                # roll back partial work
                job.status = "failed"
                job.error_detail_json = {"fatal": str(e)}
                raise
```
File bytes must be read BEFORE returning the 202 response (before request closes).
All row processing in a single transaction — partial commits are not permitted.
On fatal error: set `ImportJob.status="failed"` and rollback. Individual row errors
are accumulated (not thrown); job completes with created_count, failed_count, error_detail_json.

**File upload:** enforce 10MB max; validate MIME type server-side using file magic bytes
(check first bytes for ZIP signature `PK\x03\x04` for XLSX, not just Content-Type header).

**Field-level PATCH:** intake_staff may update intake fields only; placement_coordinator may
update priority and assignment fields; clinical fields are read-only from this endpoint.

**Case number:** human-readable, format `PC-{year}-{sequential_int:05d}` on create.

**Cross-tenant import isolation:** When upload creates PatientCase rows, every row must have
`organization_id` from `auth.organization_id`, never from the uploaded file content.

**Verification steps:**
1. `pytest tests/intake/test_import.py` — upload valid XLSX, poll until `completed`, assert cases created
2. `pytest tests/intake/test_import.py::test_upload_too_large` — 11MB file returns 413
3. `pytest tests/intake/test_import.py::test_partial_failure` — row error stops transaction; job status=failed
4. `pytest tests/intake/test_duplicate_detection.py` — duplicate `patient_name+dob+hospital_id` → 200 with `duplicate_warning: true`
5. `pytest tests/intake/test_import_tenant_isolation.py` — import as org_a; GET /cases as org_b returns 0 rows

---

### Node 4: clinical-module

**File scope:** `placementops/modules/clinical/**`

**Build dependencies:** core-infrastructure, auth-module, intake-module

**Expected files/modules:**
- `placementops/modules/clinical/router.py`
- `placementops/modules/clinical/schemas.py`
- `placementops/modules/clinical/service.py`
- `tests/clinical/` — test_assessment_versioning.py, test_finalization.py, test_backward_transition.py

**Major responsibilities:**
- POST /api/v1/cases/{id}/assessments — create ClinicalAssessment (clinical_reviewer)
- GET /api/v1/cases/{id}/assessments — list all versions (append-only; latest is canonical)
- POST /api/v1/cases/{id}/assessments/{a_id}/finalize — finalize; triggers `ready_for_matching`
- Backward transition: `under_clinical_review` → `needs_clinical_review` (requires `transition_reason`)

**Key implementation notes:**

**ClinicalAssessment boolean field names (exact ORM names from manifest):**
```
dialysis_type: Literal["hd", "peritoneal", "none"]
wound_vac_needs: bool
memory_care_needed: bool
oxygen_required: bool
behavioral_complexity_flag: bool
isolation_precautions: bool
in_house_hd_required: bool
trach: bool          # NOT trach_care_needed
vent: bool           # NOT vent_dependent
iv_antibiotics: bool # NOT iv_antibiotics_needed
tpn: bool            # NOT tpn_needed
bariatric_needs: bool
```
Use these exact names — the matching engine's hard-exclusion lookups depend on them.

- ClinicalAssessment is append-only: never UPDATE existing rows. Always INSERT new version.
- Finalization calls `transition_case_status(case_id, "under_clinical_review", "ready_for_matching", ...)`.
- Backward transition calls `transition_case_status(case_id, "under_clinical_review", "needs_clinical_review", ..., transition_reason=...)`.

**Verification steps:**
1. `pytest tests/clinical/test_assessment_versioning.py` — multiple POSTs create multiple rows; GET returns all in order
2. `pytest tests/clinical/test_finalization.py` — finalize advances case status to ready_for_matching
3. `pytest tests/clinical/test_backward_transition.py` — backward transition requires transition_reason; missing → 422

---

### Node 5: matching-module

**File scope:** `placementops/modules/matching/**`

**Build dependencies:** core-infrastructure, auth-module, clinical-module, facilities-module

**Expected files/modules:**
- `placementops/modules/matching/router.py`
- `placementops/modules/matching/schemas.py`
- `placementops/modules/matching/engine.py` — 4-stage retrieve→exclude→score→rank pipeline
- `placementops/modules/matching/scorer.py` — component score functions
- `placementops/modules/matching/geo.py` — haversine + zipcodes offline geocoding
- `tests/matching/` — test_matching_engine.py, test_hard_exclusions.py, test_scoring.py, test_multi_select.py

**Major responsibilities:**
- POST /api/v1/cases/{id}/match — run matching engine; create FacilityMatch rows; advance case
- GET /api/v1/cases/{id}/matches — retrieve ranked matches with all component scores
- PATCH /api/v1/cases/{id}/matches/{match_id}/select — toggle `selected_for_outreach` (multi-select allowed)
- 4-stage pipeline: retrieve active facilities → apply hard exclusions → score → rank by `overall_score` desc
- Scoring weights: payer_fit 35%, clinical_fit 30%, level_of_care 20%, geography 10%, preference 5%

**Key implementation notes:**

**FacilityMatch field names (exact, from manifest):**
Store: `payer_fit_score`, `clinical_fit_score`, `level_of_care_fit_score`, `geography_score`,
`preference_score`, `overall_score` (NOT `total_score`).

**Offline geocoding:**
```python
from haversine import haversine, Unit
from zipcodes import matching as zip_lookup

def get_coords(zip_code: str) -> tuple[float, float] | None:
    results = zip_lookup(zip_code)
    if not results:
        return None
    return float(results[0]["lat"]), float(results[0]["long"])

def geography_score(patient_zip: str, facility_lat: float | None, facility_lng: float | None) -> float:
    """Facility lat/lng from Facility model is authoritative (spec constraint).
    Only patient zip needs lookup via zipcodes library."""
    patient_coords = get_coords(patient_zip) if patient_zip else None
    if not patient_coords or facility_lat is None or facility_lng is None:
        return 0.0  # no exclusion on null geography
    dist = haversine(patient_coords, (facility_lat, facility_lng), unit=Unit.MILES)
    if dist <= 10: return 1.0
    if dist <= 25: return 0.7
    if dist <= 50: return 0.4
    return 0.1
```

**CRITICAL LEGAL — decision support disclaimer:**
All scoring output is decision support only. Store verbatim in `explanation_text` at write time:
`"This ranking is decision support only and does not constitute a clinical recommendation."`
DO NOT regenerate from scores. Frontend must display this text prominently on the Matching tab.

**Hard exclusions — 13 field mappings (AUTHORITATIVE TABLE — use facilities-module canonical table above).**

The compound `in_house_hd_required` check:
```python
if assessment.dialysis_type == "hd" and assessment.in_house_hd_required:
    if not (caps.accepts_hd and caps.in_house_hemodialysis):
        add_blocker(...)
elif assessment.dialysis_type == "hd":
    if not caps.accepts_hd:
        add_blocker(...)
```

**Re-run matching:** Old FacilityMatch rows are RETAINED (for audit history). New rows are
inserted with the current `generated_at` timestamp. The coordinator's `selected_for_outreach`
selections are NOT carried forward to the new set — they are reset. Frontend must warn before re-run.

**Zero results:** If all facilities are hard-excluded, still advance case to
`facility_options_generated`. Return all blocked facilities with their `blockers_json`. Frontend
displays: "No eligible facilities found. Review excluded facilities below."

**Verification steps:**
1. `pytest tests/matching/test_hard_exclusions.py` — facility missing required capability is excluded
2. `pytest tests/matching/test_scoring.py` — weights sum to 1.0; scores bounded 0.0–1.0; field is `overall_score`
3. `pytest tests/matching/test_multi_select.py` — selecting two facilities sets both `selected_for_outreach=True`
4. `pytest tests/matching/test_matching_engine.py::test_zero_results` — all facilities excluded → 200 with `facility_options_generated` status

---

### Node 6: outreach-module

**File scope:** `placementops/modules/outreach/**`

**Build dependencies:** core-infrastructure, auth-module, matching-module

**Expected files/modules:**
- `placementops/modules/outreach/router.py`
- `placementops/modules/outreach/schemas.py`
- `placementops/modules/outreach/service.py`
- `placementops/modules/outreach/template_engine.py` — Jinja2 SandboxedEnvironment
- `tests/outreach/` — test_approval_machine.py, test_ssti_prevention.py, test_phone_manual.py, test_auto_cancel.py

**Major responsibilities:**
- POST /api/v1/cases/{id}/outreach-actions — create OutreachAction (draft)
- POST /api/v1/outreach-actions/{id}/submit — draft → pending_approval
- POST /api/v1/outreach-actions/{id}/approve — pending_approval → approved (placement_coordinator or admin ONLY)
- POST /api/v1/outreach-actions/{id}/send — approved → sent
- POST /api/v1/outreach-actions/{id}/cancel — cancel from draft, pending_approval, approved, or failed
- GET /api/v1/templates/outreach — read-only list of templates (admin-surfaces owns write; outreach-module reads via ORM)
- First OutreachAction approved → case advances to `outreach_in_progress`
- First OutreachAction sent → case advances to `pending_facility_response`
- On case acceptance/placement: auto-cancel all draft/pending_approval/approved OutreachActions; `sent` preserved

**Key implementation notes:**

**Outreach template write rejection — 405 (not 403):**
POST/PATCH/DELETE to /api/v1/templates/outreach from outreach-module router must return
**HTTP 405 Method Not Allowed** (not 403). Admin-surfaces is the canonical owner of template writes.
The GET endpoint in outreach-module router exists for the frontend's use; the outreach-module
code itself reads templates via ORM (`placementops.core.models.OutreachTemplate`).

**Approval role: placement_coordinator or admin ONLY** (not manager):
```python
require_role(auth, ["placement_coordinator", "admin"])
```

**Jinja2 SSTI prevention:**
```python
from jinja2.sandbox import SandboxedEnvironment
env = SandboxedEnvironment()
ALLOWED_VARS = {"patient_name", "facility_name", "payer_name", "assessment_summary", "coordinator_name"}
# Validate template body at render time AND at admin-surfaces create/update time
# Reject body_template containing {%...%} blocks or {{...}} referencing names outside ALLOWED_VARS
template = env.from_string(template_body)
rendered = template.render(**{k: v for k, v in context.items() if k in ALLOWED_VARS})
```

**phone_manual/task atomic advance:** When `send_type == "phone_manual"`, approve and send
steps must occur atomically in a single transaction: `pending_approval → approved → sent`.
This prevents the case getting stuck at `outreach_pending_approval`.

**Failed state recovery:** `failed → canceled` only (no auto-retry in Phase 1).

**OutreachAction.facility_id required on create** — must match a `selected_for_outreach=True`
FacilityMatch for this case; return 422 if not.

**Verification steps:**
1. `pytest tests/outreach/test_ssti_prevention.py` — template with `{{ config }}` is rejected with 422
2. `pytest tests/outreach/test_approval_machine.py` — invalid transitions (e.g., draft → sent) return 400
3. `pytest tests/outreach/test_phone_manual.py` — phone_manual advances case to pending_facility_response atomically
4. `pytest tests/outreach/test_auto_cancel.py` — accepting case cancels draft/approved actions; sent actions remain

---

### Node 7: outcomes-module

**File scope:** `placementops/modules/outcomes/**`

**Build dependencies:** core-infrastructure, auth-module, outreach-module

**Expected files/modules:**
- `placementops/modules/outcomes/router.py`
- `placementops/modules/outcomes/schemas.py`
- `placementops/modules/outcomes/service.py`
- `tests/outcomes/` — test_outcome_types.py, test_declined_facility_id.py, test_state_transitions.py

**Major responsibilities:**
- POST /api/v1/cases/{id}/outcomes — record PlacementOutcome (placement_coordinator or admin ONLY)
- Outcome types (user-creatable): `accepted`, `declined`, `family_declined`, `withdrawn`, `placed`
  (`pending_review` is a valid schema value but not user-creatable via this endpoint)
- `declined`: facility_id REQUIRED; decline_reason_code REQUIRED; case → `declined_retry_needed`
- `family_declined`/`withdrawn`: facility_id permitted null; case → `closed` (manager must confirm)
- `accepted`: case → `accepted`; triggers auto-cancel sweep of draft/pending_approval/approved outreach
- `placed`: case → `placed`
- Every outcome writes AuditEvent
- Validates: sent outreach exists for `facility_id` (via ORM query on OutreachAction) before accepting `declined`/`accepted`

**Key implementation notes:**

**`pending_review` outcome_type:** This enum value exists in the manifest schema for
forward-compatibility. It must be accepted in the database enum but must NOT be user-creatable
via this endpoint (reject with 422 if submitted). Document this in the schema.

**`family_declined`/`withdrawn` two-step closure:** Recording these outcomes advances the case
to `closed` only after manager confirmation (a second PATCH step). The outcome record is created
with `outcome_type=family_declined`; case enters a "pending closure" sub-state; manager then
calls the status-transition endpoint to advance to `closed` with `closure_reason`.

**Declined facility_id validation:** Query OutreachAction where `patient_case_id=case_id`
AND `facility_id=outcome.facility_id` AND `status="sent"`. If zero rows found, return 422.

**Retry routing (from declined_retry_needed):** Coordinator calls `POST /api/v1/cases/{id}/status-transition`
to advance to `ready_for_matching` or `outreach_pending_approval`. This is the SAME endpoint
as intake-module's status-transition endpoint (implemented in intake-module, delegates to
`transition_case_status()`). No new endpoint needed here.

**Verification steps:**
1. `pytest tests/outcomes/test_declined_facility_id.py` — declined without facility_id returns 422
2. `pytest tests/outcomes/test_outcome_types.py` — each type advances case to correct status
3. `pytest tests/outcomes/test_state_transitions.py` — outcome on closed case returns 409
4. `pytest tests/outcomes/test_outcome_types.py::test_pending_review_rejected` — pending_review POST returns 422

---

### Node 8a: admin-surfaces

**File scope:** `placementops/modules/admin/**`

**Build dependencies:** core-infrastructure, auth-module, intake-module, outreach-module

**Expected files/modules:**
- `placementops/modules/admin/router.py`
- `placementops/modules/admin/schemas.py`
- `placementops/modules/admin/service.py`
- `tests/admin/` — test_template_crud.py, test_user_management.py, test_import_monitoring.py

**Major responsibilities:**
- POST/PATCH /api/v1/templates/outreach — template CRUD (admin only; canonical write owner)
- GET /api/v1/imports — read-only import job monitoring (admin only)
- POST/PATCH /api/v1/admin/users — user management (admin only); uses SUPABASE_SERVICE_ROLE_KEY
- PATCH /api/v1/admin/reference-data — seed and update reference data tables
- GET/PATCH /api/v1/admin/organization — org settings
- DELETE → HTTP 405 for ALL PHI table endpoints (uniform system-wide pattern)

**Key implementation notes:**

**Template validation at create/update time (not just at render time):**
Validate `body_template` at creation and update: reject body_template containing `{%` blocks
or `{{` expressions referencing names outside `[patient_name, facility_name, payer_name, assessment_summary, coordinator_name]`.
This is the first line of defense; outreach-module's SandboxedEnvironment is the second.

**DELETE → 405 applies to:** templates, users, import_jobs, and all other PHI entity endpoints.
Implement this consistently. Test: `DELETE /api/v1/templates/outreach/{id}` → 405.

**SUPABASE_SERVICE_ROLE_KEY:** Only this module may use it. Use for Supabase Auth admin API
(invite user, set role). All other modules use the anon key.

**Verification steps:**
1. `pytest tests/admin/test_template_crud.py` — CRUD works; outreach-module GET returns created template
2. `pytest tests/admin/test_template_crud.py::test_delete_returns_405` — DELETE returns 405
3. `pytest tests/admin/test_template_crud.py::test_ssti_validation` — template with `{{ config }}` rejected on create

---

### Node 8b: analytics-module

**File scope:** `placementops/modules/analytics/**`

**Build dependencies:** core-infrastructure, auth-module, outcomes-module

**Expected files/modules:**
- `placementops/modules/analytics/router.py`
- `placementops/modules/analytics/schemas.py`
- `placementops/modules/analytics/queries.py` — optimized async read queries
- `tests/analytics/` — test_sla_flags.py, test_queue_views.py, test_dashboard_kpis.py

**Major responsibilities:**
- GET /api/v1/queues/operations — operations queue with SLA aging flags; accessible to **placement_coordinator, clinical_reviewer, manager, and admin** (NOT intake_staff or read_only)
- GET /api/v1/queues/manager-summary — aging distribution by status (case_count, sla_breach_count, avg_hours_in_status per status), list of all SLA-breached cases, total_active_cases count; accessible to manager and admin only
- GET /api/v1/analytics/dashboard — KPIs: total active cases, avg time in each state, placement rate, decline rate; date-range filterable (default last 30 days)
- GET /api/v1/analytics/outreach-performance — outreach performance: accept/decline rates by facility and by decline_reason_code; date-range filterable
- SLA aging: computed as `NOW() - case_status_history.entered_at` for current status via DISTINCT ON query; flag if > threshold constants
- Response time: < 2s for 1000 cases; all list endpoints paginate with page + page_size + total_count

**Key implementation notes:**

**Operations queue role access (P1-C-07 fix):**
`GET /api/v1/queues/operations` is accessible to placement_coordinator, clinical_reviewer,
manager, and admin. This is the default landing page for coordinator and clinical_reviewer
after login. Restrict only intake_staff and read_only from this endpoint (or give read_only
read access with no actions). Do NOT restrict placement_coordinator.

**SLA computation requires `case_status_history`:**
```sql
-- SLA aging query — DISTINCT ON ensures exactly one (most recent) row per case,
-- required because a case can re-enter the same status (e.g. declined_retry_needed twice)
SELECT DISTINCT ON (pc.id)
    pc.id,
    pc.current_status,
    csh.entered_at AS status_entered_at,
    EXTRACT(EPOCH FROM (NOW() - csh.entered_at)) / 3600 AS hours_in_status
FROM patient_cases pc
JOIN case_status_history csh
    ON csh.patient_case_id = pc.id
    AND csh.to_status = pc.current_status
ORDER BY pc.id, csh.entered_at DESC
```
This query REQUIRES the `case_status_history` table from core-infrastructure.

**Indexing for <2s response time:**
```sql
CREATE INDEX CONCURRENTLY idx_patient_cases_org_status
    ON patient_cases (organization_id, current_status, updated_at);
CREATE INDEX CONCURRENTLY idx_case_status_history_case_status
    ON case_status_history (patient_case_id, to_status, entered_at DESC);
CREATE INDEX CONCURRENTLY idx_placement_outcomes_case_type
    ON placement_outcomes (patient_case_id, outcome_type);
```

**Do NOT use `SELECT ... FOR SHARE`** in analytics queries — analytics is read-only;
standard `SELECT` with READ COMMITTED isolation is correct. `FOR SHARE` would add
unnecessary lock contention on hot rows.

**Verification steps:**
1. `pytest tests/analytics/test_sla_flags.py` — case older than SLA threshold shows `sla_breached: true`
2. `pytest tests/analytics/test_queue_views.py` — coordinator GET /queues/operations returns 200 (not 403)
3. `pytest tests/analytics/test_queue_views.py::test_declined_retry_cases` — declined_retry_needed cases appear with "Route Retry" flag

---

### Node 9: frontend-app-shell

**File scope:** `frontend/**`

**Build dependencies:** auth-module, intake-module, facilities-module, clinical-module, matching-module, outreach-module, outcomes-module, admin-surfaces, analytics-module (built last)

**Expected files/modules:**
- `frontend/app/` — Next.js 14 App Router pages
- `frontend/app/(auth)/login/page.tsx`
- `frontend/app/(app)/cases/page.tsx` — TanStack Table + nuqs URL state
- `frontend/app/(app)/cases/[id]/page.tsx` — case detail (**6 tabs: Overview, Clinical Review, Facility Matches, Outreach, Timeline, Audit**)
- `frontend/app/(app)/queue/page.tsx` — operations queue (coordinator/reviewer/manager landing)
- `frontend/app/(app)/facilities/page.tsx`
- `frontend/app/(app)/analytics/page.tsx` — dashboard KPIs
- `frontend/app/(app)/admin/` — templates, users, reference data
- `frontend/components/` — shadcn/ui wrappers, shared layout
- `frontend/lib/api/` — @hey-api/openapi-ts generated typed client
- `frontend/lib/auth/` — Supabase SSR: `getUser()` only, NEVER `getSession()`
- `frontend/lib/hooks/` — custom data-fetching and form hooks
- `frontend/openapi.json` — exported from FastAPI `/openapi.json`

**Case detail tab names (exact — from spec):**
```
Overview | Clinical Review | Facility Matches | Outreach | Timeline | Audit
```
(NOT "Intake, Clinical, Matching, Outreach, Outcomes, Activity")
CaseTabId enum values: `overview | clinical | matches | outreach | timeline | audit`

**Major responsibilities:**
- Login → Supabase Auth → JWT in SSR cookie; role-based landing page
  - placement_coordinator, clinical_reviewer → `/queue`
  - manager, admin → `/queue` or `/analytics`
  - intake_staff → `/cases`
- Cases list: TanStack Table with server-side pagination; nuqs URL state (status, page, sort)
- Case detail: 6-tab layout using Sheet for drawers; role-aware tab visibility and action buttons
- Facility Matches tab: ranked results with `overall_score`, blocker chips for excluded facilities;
  **decision support disclaimer** prominently above results:
  `"This ranking is decision support only and does not constitute a clinical recommendation."`
- Outreach tab: approval workflow; approve button visible only to placement_coordinator/admin
- Two-step family_declined/withdrawn closure: manager sees cases in queue awaiting closure confirmation;
  "Confirm Closure" form requires `closure_reason`; calls status-transition endpoint
- Re-score warning: confirmation modal before re-running matching engine; warns coordinator
  that existing facility selections will be cleared; displays `ReMatchWarning` component
- Empty states: "No eligible facilities" (zero match results); "No templates available" (outreach)
- Declined retry: "Route Retry" action button on operations queue for `declined_retry_needed` cases;
  destination selector: "Back to Matching" (`ready_for_matching`) or "Create New Outreach" (`outreach_pending_approval`)

**Key implementation notes:**

**`getUser()` only (CRITICAL):**
```typescript
// CORRECT
const { data: { user } } = await supabase.auth.getUser()
// WRONG — do not use, cannot be trusted server-side
// const { data: { session } } = await supabase.auth.getSession()
```

**Typed API client:**
```bash
npx @hey-api/openapi-ts \
  --input http://localhost:8000/openapi.json \
  --output frontend/lib/api \
  --client @hey-api/client-fetch
```
Regenerate after every backend API change. Commit to source control.
All API calls must go through this client — no hand-written `fetch()` to backend endpoints.

**TanStack Table + nuqs:**
```typescript
const [page, setPage] = useQueryState('page', parseAsInteger.withDefault(1))
const [status, setStatus] = useQueryState('status')
const table = useReactTable({
    data, columns,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getSortingRowModel: getSortingRowModel(),
})
```

**Tailwind v4:** use `tw-animate-css` (not `tailwindcss-animate`).
**Drawers:** use `Sheet` component (slides from right, preserves case list context).

**First-run bootstrap (new organization):**
If no organizations exist, the app must show an onboarding screen or documentation link
explaining: (1) create org via Supabase dashboard SQL or admin seed script;
(2) provision first admin via `supabase.auth.admin.createUser()` in admin seed;
(3) set `app_metadata.organization_id` and `role_key` via Supabase Auth admin API.
This is a one-time manual process; document in README.

**Verification steps:**
1. `npm run build` — zero TypeScript errors
2. Playwright: login → coordinator lands on `/queue`; intake_staff lands on `/cases`
3. Playwright: case detail 6-tab navigation; "Facility Matches" tab visible after matching; approve button visible only for coordinator/admin on Outreach tab
4. Playwright: decision support disclaimer visible on Facility Matches tab without scrolling
5. Playwright: re-score confirmation modal appears before generating new matches
6. `npm run test` — all Jest/RTL unit tests pass

---

## 4. Research to Apply

Every builder MUST apply these findings. These are not optional optimizations — they prevent
known failures in the chosen tech stack.

### PyJWT vs python-jose
Use `PyJWT[cryptography]`. The `python-jose` library is abandoned and has unfixed CVEs.
`import jwt`. Install: `pip install "PyJWT[cryptography]"`.

### NullPool + Supavisor
```python
from sqlalchemy.pool import NullPool
engine = create_async_engine(
    DATABASE_URL,
    poolclass=NullPool,
    connect_args={"statement_cache_size": 0},
)
```

### nH Predict Lawsuit Warning
PlacementOps matching scores MUST be labeled as decision support only. Store verbatim in
`explanation_text`. Frontend must display prominently. Never use scoring to override clinician judgment.

### Jinja2 Sandbox SSTI Prevention
```python
from jinja2.sandbox import SandboxedEnvironment
env = SandboxedEnvironment()
ALLOWED_VARS = {"patient_name", "facility_name", "payer_name", "assessment_summary", "coordinator_name"}
template = env.from_string(template_body)
rendered = template.render(**{k: v for k, v in context.items() if k in ALLOWED_VARS})
```
Validate at both create time (admin-surfaces) and render time (outreach-module).

### TanStack Table + nuqs
```typescript
const [page, setPage] = useQueryState('page', parseAsInteger.withDefault(1))
const table = useReactTable({
    data, columns,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
})
```

### haversine + zipcodes Offline Geocoding
```python
from haversine import haversine, Unit
from zipcodes import matching as zip_lookup
```
Both work offline — correct for HIPAA. Null zip → score 0.0, no exclusion.

### BackgroundTasks Session Isolation
Background task must accept `file_bytes: bytes` (pre-read), create its own `AsyncSession`,
wrap all row processing in a single transaction, and handle failures with rollback.

### @hey-api/openapi-ts Typed Client
```bash
npx @hey-api/openapi-ts --input http://localhost:8000/openapi.json --output frontend/lib/api --client @hey-api/client-fetch
```
Commit generated client. Regenerate on every backend API change.

---

## 5. Shared Models

All 13 primary shared models are defined in core-infrastructure. **No other node may redefine.**

| Model | Owner (writes) | Consumers (reads) |
|---|---|---|
| PatientCase | intake-module | clinical, matching, outreach, outcomes, analytics, admin, frontend |
| Facility | facilities-module | matching, outreach, outcomes, analytics, frontend |
| FacilityCapabilities | facilities-module | matching |
| FacilityInsuranceRule | facilities-module | matching |
| FacilityContact | facilities-module | outreach |
| User | auth-module | all nodes (via AuthContext) |
| OutreachAction | outreach-module | outcomes, analytics, frontend |
| OutreachTemplate | admin-surfaces | outreach-module (read only via ORM) |
| ClinicalAssessment | clinical-module | matching |
| FacilityMatch | matching-module | outreach-module, frontend |
| ImportJob | intake-module | admin-surfaces (read only) |
| PlacementOutcome | outcomes-module | analytics, frontend |
| AuditEvent | all nodes (insert only) | admin-surfaces (read only) |

**Additional supporting tables** (also in core-infrastructure, import from `placementops.core.models`):
`CaseStatusHistory` (required for SLA analytics), `CaseAssignment`, `CaseActivityEvent`,
`IntakeFieldIssue`, `FacilityPreference` (owner: facilities-module; consumer: matching-module),
`Organization`, `UserRole`, `DeclineReasonReference`, `PayerReference`, `HospitalReference`

All ORM models import from `placementops.core.models` — never redefine locally.

---

## 6. Critical Constraints

All nodes. Violations are CRITICAL findings during sweep.

| Constraint | Enforcement |
|---|---|
| AuditEvent immutability | Postgres BEFORE UPDATE OR DELETE trigger + ORM insert-only |
| Multi-tenancy | `organization_id` in EVERY query; Supabase RLS defense-in-depth |
| org_id source | JWT `app_metadata.organization_id` — NEVER `user_metadata` |
| org_id on new records | Set from `auth.organization_id` server-side; NEVER from request body |
| Closed case mutation | Shared Depends() guard returns 409 before handler executes |
| State machine | Only `transition_case_status()` changes `current_status` |
| Role gates | All write endpoints check `auth.role_key` against allowed roles |
| No PHI in logs | PHI fields (patient_name, dob, mrn, draft bodies) must not appear in any log |
| Scoring disclaimer | All scoring output includes verbatim "decision support only" disclaimer |
| DELETE → 405 | All PHI table DELETE endpoints return 405 Method Not Allowed |
| NullPool | App pool must use NullPool + statement_cache_size=0 |
| PyJWT | Never import python-jose; use `import jwt` from PyJWT[cryptography] |
| CORS | CORS_ALLOWED_ORIGINS env var; never `allow_origins=["*"]` |
| SUPABASE_SERVICE_ROLE_KEY | Used only in admin-surfaces; no other module may reference it |

---

## 7. Critical Integration Points

### 1. core-infrastructure → ALL: get_auth_context + organization_id enforcement

```python
from placementops.core.auth import get_auth_context, AuthContext

@router.get("/api/v1/cases/{case_id}")
async def get_case(
    case_id: UUID,
    auth: AuthContext = Depends(get_auth_context),
    session: AsyncSession = Depends(get_async_session),
):
    case = await session.get(PatientCase, case_id)
    if case.organization_id != auth.organization_id:
        raise HTTPException(403)
```
All queries filter by `auth.organization_id`. New records set `organization_id = auth.organization_id`.

### 2. core-infrastructure → ALL: transition_case_status

```python
from placementops.core.state_machine import transition_case_status

await transition_case_status(
    session=session,
    case_id=case_id,
    from_status="under_clinical_review",
    to_status="ready_for_matching",
    actor_role=auth.role_key,
    actor_user_id=auth.user_id,
    transition_reason=None,
)
```
ONLY way to change `current_status`. Writes CaseStatusHistory and AuditEvent automatically.

### 3. matching-module → outreach-module: selected_for_outreach validation

`POST /api/v1/cases/{id}/outreach-actions`: validate that `facility_id` in request body has
a `FacilityMatch` row with `selected_for_outreach=True` for this case. If not → 422.

### 4. admin-surfaces → outreach-module: OutreachTemplate boundary

Outreach-module reads `OutreachTemplate` via ORM only. POST/PATCH/DELETE to template endpoint
from outreach-module router returns **405**. Admin-surfaces is the sole writer.

### 5. frontend-app-shell → ALL: @hey-api/openapi-ts typed client

All API calls via generated client only. No hand-written `fetch()` to backend endpoints.
Regenerate client from FastAPI `/openapi.json` after every backend API change.

---

## 8. Environment Variables

```bash
# Database (two URLs required)
DATABASE_URL=postgresql+asyncpg://user:pass@db.supabase.co:6543/postgres
DATABASE_DIRECT_URL=postgresql+asyncpg://user:pass@db.supabase.co:5432/postgres

# Supabase Auth
SUPABASE_URL=https://project.supabase.co
SUPABASE_ANON_KEY=eyJhbGc...
SUPABASE_SERVICE_ROLE_KEY=eyJhbGc...  # admin-surfaces ONLY — never expose to other modules
SUPABASE_JWT_SECRET=your-jwt-secret   # HS256 fallback — required always
SUPABASE_JWKS_URL=https://project.supabase.co/auth/v1/keys  # optional ES256

# App
ENVIRONMENT=development
CORS_ALLOWED_ORIGINS=http://localhost:3000

# Frontend
NEXT_PUBLIC_SUPABASE_URL=https://project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJhbGc...
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

---

## 9. Docker Compose (Development)

```yaml
services:
  api:
    build: .
    ports: ["8000:8000"]
    env_file: .env
    environment:
      DATABASE_URL: ${DATABASE_URL}
      DATABASE_DIRECT_URL: ${DATABASE_DIRECT_URL}
      SUPABASE_URL: ${SUPABASE_URL}
      SUPABASE_ANON_KEY: ${SUPABASE_ANON_KEY}
      SUPABASE_SERVICE_ROLE_KEY: ${SUPABASE_SERVICE_ROLE_KEY}
      SUPABASE_JWT_SECRET: ${SUPABASE_JWT_SECRET}
      SUPABASE_JWKS_URL: ${SUPABASE_JWKS_URL}
      CORS_ALLOWED_ORIGINS: http://localhost:3000
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
      interval: 10s
      timeout: 5s
      retries: 5

  frontend:
    build: ./frontend
    ports: ["3000:3000"]
    env_file: frontend/.env.local
    environment:
      NEXT_PUBLIC_SUPABASE_URL: ${NEXT_PUBLIC_SUPABASE_URL}
      NEXT_PUBLIC_SUPABASE_ANON_KEY: ${NEXT_PUBLIC_SUPABASE_ANON_KEY}
      NEXT_PUBLIC_API_BASE_URL: http://api:8000
    depends_on:
      api:
        condition: service_healthy
```

---

*Plan v2 — all 11 CRITICAL and 11 IMPORTANT findings from plan-review-pass-1 fixed.*
*Next: plan-review-pass-2 verification by reduced agent panel.*
