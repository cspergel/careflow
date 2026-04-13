# Architectural Decisions

## D-core-4-select-for-update
**Nodes:** core-infrastructure
**Choice:** SELECT FOR UPDATE on PatientCase before transition
**Why:** prevents lost updates under concurrent transitions (two coordinators racing to close the same case)
**Files:** [placementops/core/state_machine.py:15]
**Status:** Active

## D-core-1-nullpool-supavisor
**Nodes:** core-infrastructure
**Choice:** NullPool with statement_cache_size=0 and prepared_statement_cache_size=0
**Why:** Supavisor transaction mode (port 6543) cannot maintain prepared statements across transactions; NullPool hands connection management to Supavisor entirely
**Files:** [placementops/core/database.py:8]
**Status:** Active

## D-core-2-jwt-alg-detection
**Nodes:** core-infrastructure
**Choice:** Determine algorithm from JWT header alg field
**Why:** Supabase project may use either HS256 (pre-Oct-2025) or ES256 (post-Oct-2025); checking the header allows a single middleware to support both without config changes
**Files:** [placementops/core/auth.py:12]
**Status:** Active

## D-core-5-phi-log-filter
**Nodes:** core-infrastructure
**Choice:** Log filter that redacts known PHI field names (patient_name, dob, mrn, etc.) from structured log records
**Why:** HIPAA requires that PHI not appear in application logs; filter approach covers all log sites without requiring per-callsite scrubbing
**Files:** [placementops/core/middleware.py:11]
**Status:** Active

## D-auth-3-rate-limiter-module-state
**Nodes:** auth-module
**Choice:** In-process defaultdict(deque) per spec
**Why:** spec explicitly describes in-memory sliding window; distributed state is a non-goal for Phase 1
**Files:** [placementops/modules/auth/rate_limiter.py:12]
**Status:** Active

## D-auth-4-rbac-role-permissions-dict
**Nodes:** auth-module
**Choice:** RolePermissions exported as plain dict keyed by role_key
**Why:** importable, no ORM dependency; actual enforcement via require_role Depends
**Files:** [placementops/modules/auth/service.py:14]
**Status:** Active

## D-auth-2-supabase-logout
**Nodes:** auth-module
**Choice:** Direct httpx POST to /auth/v1/logout
**Why:** supabase-py set_session() requires both access+refresh tokens; we only have the access token at logout time; direct REST call is simpler and more reliable
**Files:** [placementops/modules/auth/service.py:115]
**Status:** Active

## D-auth-1-db-role-lookup
**Nodes:** auth-module
**Choice:** require_role fetches User row from DB on every call
**Why:** JWT role_key in app_metadata can be stale after a role change; DB row is always authoritative per AC12
**Files:** [placementops/modules/auth/dependencies.py:30]
**Status:** Active

## D-intake-1-local-models
**Nodes:** intake-module
**Choice:** IntakeFieldIssue and CaseAssignment defined in intake module (not core)
**Why:** these models do not exist in core/models and are intake-specific; defining locally avoids modifying core file_scope while keeping the data models available
**Files:** [placementops/modules/intake/models.py:11]
**Status:** Active

## D-intake-2-file-bytes-in-memory
**Nodes:** intake-module
**Choice:** file_bytes passed in-memory to BackgroundTask, not persisted to DB
**Why:** ImportJob has no file_bytes column; spec pattern shows bytes passed as task argument; avoids adding large binary to ImportJob table
**Files:** [placementops/modules/intake/service.py:16]
**Status:** Active

## D-intake-3-required-intake-fields
**Nodes:** intake-module
**Choice:** Required fields for mark-intake-complete: patient_name, hospital_id, hospital_unit, room_number, admission_date, primary_diagnosis_text, insurance_primary
**Why:** minimum fields needed for clinical review; inferred from intake domain since spec does not enumerate them
**Files:** [placementops/modules/intake/service.py:17]
**Status:** Active

## D-intake-4-resolved-flag-true
**Nodes:** intake-module
**Choice:** resolved_flag=True means issue is resolved
**Why:** "resolved" semantics; set to True when field re-submitted with valid value per AC15
**Files:** [placementops/modules/intake/service.py:18]
**Status:** Active

## D-intake-5-fresh-session-background
**Nodes:** intake-module
**Choice:** Opens fresh AsyncSessionLocal in background task
**Why:** request session is closed before background task runs; reusing it causes DetachedInstanceError on every write
**Files:** [placementops/modules/intake/service.py:1020]
**Status:** Active

## D-facilities-1-preference-local-model
**Nodes:** facilities-module
**Choice:** FacilityPreference defined in facilities module not core
**Why:** model absent from core/models/__init__.py and no other module depends on it; avoids circular imports and keeps facilities concerns self-contained
**Files:** [placementops/modules/facilities/models.py:12]
**Status:** Active

## D-facilities-2-org-filter
**Nodes:** facilities-module
**Choice:** All list/get queries filter by organization_id
**Why:** defense-in-depth alongside RLS; prevents data leakage when RLS is disabled in dev/test environments
**Files:** [placementops/modules/facilities/service.py:24]
**Status:** Active

## D-facilities-3-upsert-pattern
**Nodes:** facilities-module
**Choice:** SELECT then INSERT/UPDATE for upsert
**Why:** SQLite in tests does not support PostgreSQL ON CONFLICT syntax; merge() does SELECT+INSERT which works across both backends
**Files:** [placementops/modules/facilities/service.py:378]
**Status:** Active

## D-matching-1-haversine-step-function
**Nodes:** matching-module
**Choice:** Haversine step function (≤10mi=1.0, ≤25mi=0.7, ≤50mi=0.4, >50mi=0.1)
**Why:** spec mandates discrete bins for predictable, auditable geography scoring rather than continuous decay
**Files:** [placementops/modules/matching/engine.py:32]
**Status:** Active

## D-matching-2-lru-cache-zip-lookup
**Nodes:** matching-module
**Choice:** @functools.lru_cache on zip_to_latlon to avoid redundant zipcodes I/O within one scoring run
**Why:** a single match generation iterates N facilities per case; ZIP lookup is per-case not per-facility so caching avoids N identical lookups
**Files:** [placementops/modules/matching/engine.py:33]
**Status:** Active

## D-outreach-1-sandboxed-env
**Nodes:** outreach-module
**Choice:** jinja2.sandbox.SandboxedEnvironment for all template rendering
**Why:** bare Environment allows __class__.__mro__ traversal and other SSTI vectors; SandboxedEnvironment is the only safe choice for user-influenced template content
**Files:** [placementops/modules/outreach/template_renderer.py:16]
**Status:** Active

## D-outreach-2-system-role-advance
**Nodes:** outreach-module
**Choice:** Use actor_role="system" for outreach_pending_approval→outreach_in_progress and outreach_in_progress→pending_facility_response
**Why:** state machine only allows role "system" for these transitions; outreach service orchestrates internally, not via a human actor
**Files:** [placementops/modules/outreach/service.py:33]
**Status:** Active

## D-outreach-4-bypass-atomicity
**Nodes:** outreach-module
**Choice:** Defer commit until first transition_case_status call
**Why:** removing the early commit at this point means the OutreachAction and audit row are flushed (visible within the session) but not yet committed; the first transition_case_status call will commit them together with the first case-status change, achieving the atomicity required by F3
**Files:** [placementops/modules/outreach/service.py:342]
**Status:** Active

## D-outreach-3-405-explicit-handlers
**Nodes:** outreach-module
**Choice:** Explicit POST/PATCH/DELETE handlers on /templates/outreach return 405
**Why:** FastAPI does not automatically return 405 for unregistered methods; explicit handlers with raise HTTPException(405) are required to satisfy AC10's method-not-allowed constraint
**Files:** [placementops/modules/outreach/router.py:30]
**Status:** Active

## D-outcomes-1-pre-flush-atomicity
**Nodes:** outcomes-module
**Choice:** Flush all pending writes before calling transition_case_status which commits
**Why:** transition_case_status owns the commit; flushing ensures outcome row + auto-cancel updates land in the same atomic commit as the status advance
**Files:** [placementops/modules/outcomes/service.py:30]
**Status:** Active

## D-outcomes-2-timeline-from-csh
**Nodes:** outcomes-module
**Choice:** Read timeline from CaseStatusHistory table
**Why:** in-process event bus (CaseActivityEvent) is ephemeral; CaseStatusHistory is the only durable timeline store written by transition_case_status
**Files:** [placementops/modules/outcomes/service.py:31]
**Status:** Active

## D-outcomes-3-family-withdrawn-no-transition
**Nodes:** outcomes-module
**Choice:** family_declined/withdrawn do not call transition_case_status
**Why:** spec requires manager confirmation via separate status-transition; auto-advancing to closed removes required managerial oversight
**Files:** [placementops/modules/outcomes/service.py:32]
**Status:** Active

## D-outcomes-4-outcome-audit-separate
**Nodes:** outcomes-module
**Choice:** Write AuditEvent with entity_type=placement_outcome for every outcome type
**Why:** AC14 mandates audit for all 5 types; transition_case_status only writes for types that advance status; family_declined/withdrawn have no status change audit unless we write it here
**Files:** [placementops/modules/outcomes/service.py:33]
**Status:** Active

## D-analytics-1-sla-subquery
**Nodes:** analytics-module
**Choice:** SLA hours_in_status uses MAX(entered_at) subquery
**Why:** a case may re-enter the same status (e.g., declined_retry_needed twice); MAX gives the most recent transition into the current status, which is what the spec requires
**Files:** [placementops/modules/analytics/sla.py:10]
**Status:** Active

## D-analytics-2-stage-metrics-window
**Nodes:** analytics-module
**Choice:** Stage cycle time via self-join on case_status_history aliased as h1/h2
**Why:** SQLAlchemy async doesn't support window functions cleanly for this pattern; self-join on (h2.patient_case_id=h1.patient_case_id AND h2.from_status=h1.to_status) gives exact stage durations per the spec's "transition timestamps" requirement.
**Files:** [placementops/modules/analytics/service.py:16]
**Status:** Active

## D-analytics-3-placement-outcome-join
**Nodes:** analytics-module
**Choice:** Outcomes org-scoped via JOIN through PatientCase
**Why:** PlacementOutcome has no organization_id column; must join through patient_cases to enforce tenant isolation on all outcome queries.
**Files:** [placementops/modules/analytics/service.py:17]
**Status:** Active

## D-analytics-4-stage-metrics-python-arithmetic
**Nodes:** analytics-module
**Choice:** Stage cycle hours computed in Python after fetching (h1.entered_at, h2.entered_at) pairs
**Why:** func.extract("epoch", timedelta) is PostgreSQL-only; Python datetime arithmetic works on both SQLite (tests) and PostgreSQL (production).
**Files:** [placementops/modules/analytics/service.py:484]
**Status:** Active

## D-admin-1-allowed-variables-allowlist
**Nodes:** admin-surfaces
**Choice:** Hard-coded allowlist in service constant
**Why:** template allowed_variables must be validated server-side to prevent unsafe variable injection into outreach templates; a central constant is the single source of truth
**Files:** [placementops/modules/admin/service.py:38]
**Status:** Active

## D-frontend-4-tailwind-v4
**Nodes:** frontend-app-shell
**Choice:** Tailwind v4 with tw-animate-css plugin
**Why:** spec requires tw-animate-css NOT tailwindcss-animate; Tailwind v4 config is minimal, CSS variables in globals.css
**Files:** [frontend/tailwind.config.ts:2]
**Status:** Active

## D-frontend-1-openapi-ts-config
**Nodes:** frontend-app-shell
**Choice:** Used @hey-api/openapi-ts v0.43.x config format (input/output flat style)
**Why:** spec pins ^0.43.0; this version uses input/output at root level
**Files:** [frontend/openapi-ts.config.ts:3]
**Status:** Active

## D-frontend-2-middleware-token-refresh
**Nodes:** frontend-app-shell
**Choice:** Middleware only refreshes token, access control in server components
**Why:** CVE-2025-29927 demonstrated middleware-only auth can be bypassed; real auth gating happens in each server component
**Files:** [frontend/middleware.ts:15]
**Status:** Active

## D-frontend-3-api-client-placeholder
**Nodes:** frontend-app-shell
**Choice:** Placeholder client exported from index.ts
**Why:** actual generation requires FastAPI server; placeholder provides type-safe interface for current-phase development
**Files:** [frontend/src/client/index.ts:7]
**Status:** Active

## D-frontend-5-nuqs-v1-api
**Nodes:** frontend-app-shell
**Choice:** Using nuqs v1 API (useQueryStates, parseAsString, etc)
**Why:** spec pins nuqs@^1.17.0; v1 and v2 have different import paths
**Files:** [frontend/src/components/CaseTable.tsx:25]
**Status:** Active

## D-frontend-6-rsi-dynamic-import
**Nodes:** frontend-app-shell
**Choice:** react-spreadsheet-import loaded with next/dynamic + ssr:false
**Why:** library uses Chakra UI internally and browser-only APIs; SSR would fail
**Files:** [frontend/src/app/intake/import/page.tsx:22]
**Status:** Active
