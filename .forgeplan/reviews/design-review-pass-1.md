# Design Review — Pass 1
**Date:** 2026-04-10
**Tier:** LARGE
**Agents:** Adversary, Skeptic, Structuralist, Contractualist, Pathfinder
**Artifacts reviewed:** `.forgeplan/manifest.yaml`, `.forgeplan/wiki/index.md`

---

## Summary

| Agent | CRITICAL | IMPORTANT | MINOR |
|-------|----------|-----------|-------|
| Adversary | 4 | 8 | 4 |
| Skeptic | 3 | 9 | 6 |
| Structuralist | 2 | 4 | 4 |
| Contractualist | 3 | 7 | 4 |
| Pathfinder | 1 | 3 | 2 |
| **Total (raw)** | **13** | **31** | **20** |
| **After dedup** | **12** | **18** | **12** |

---

## CRITICAL Findings (12 unique)

### C-01 — State machine: no formal transition allowlist
**Agents:** Adversary, Skeptic
**Location:** manifest.yaml → nodes → multiple modules (intake-module, clinical-module, outreach-module, outcomes-module)
**Finding:** The 14-state machine has no enumeration of which role can trigger which transition. The `declined_retry_needed` state has no defined exit transition. Arbitrary state manipulation is a patient safety risk.
**Fix applied:** Added transition allowlist to core-infrastructure AC; added explicit role+transition constraints per node; declined_retry_needed exit transitions made explicit in outcomes-module.

### C-02 — SSTI injection risk in template variable substitution
**Agent:** Adversary
**Location:** manifest.yaml → nodes → outreach-module → acceptance_criteria
**Finding:** AC says "variable substitution fills patient_name, facility_name, insurance, clinical details" with no restriction. If Jinja2 is used with raw template bodies, user-supplied templates can inject server-side template expressions.
**Fix applied:** AC tightened to allowlisted safe variables only; safe renderer (Jinja2 sandbox or equivalent) required; no user-supplied template logic evaluated.

### C-03 — XLSX/CSV import: no file upload endpoint, no validation
**Agents:** Adversary, Pathfinder
**Location:** manifest.yaml → nodes → intake-module → acceptance_criteria
**Finding:** Import flow starts at "create import_job" but no AC defines how the file bytes reach the server. No file size limit, no content-type validation, no ZIP bomb protection.
**Fix applied:** Added multipart/form-data file upload AC to `POST /api/v1/imports`; 10MB max size enforced; XLSX/CSV content-type required; malformed/zip-bomb files rejected before processing.

### C-04 — AuditEvent immutability: DB-level enforcement missing
**Agent:** Adversary
**Location:** manifest.yaml → shared_models → AuditEvent
**Finding:** AuditEvent description says "immutable" and "never updated or deleted" but there is no AC requiring a Postgres trigger, RLS policy, or other DB-level guard.
**Fix applied:** Added AC to core-infrastructure requiring a Postgres trigger (or RLS policy) blocking UPDATE and DELETE on audit_events table; ORM-level restrictions insufficient alone.

### C-05 — 13+ operational tables missing from shared_models
**Agents:** Skeptic, Structuralist
**Location:** manifest.yaml → shared_models
**Finding:** The build plan specifies 20+ tables. Only 7 appear in shared_models. Tables consumed across multiple node boundaries (OutreachTemplate, FacilityCapabilities, FacilityInsuranceRule, FacilityContact, ImportJob, PlacementOutcome) are missing, making interface contracts ambiguous.
**Fix applied:** Added 6 new shared models: OutreachTemplate, FacilityCapabilities, FacilityInsuranceRule, FacilityContact, ImportJob, PlacementOutcome.

### C-06 — outreach_pending_approval → outreach_in_progress: contradictory trigger
**Agent:** Skeptic
**Location:** manifest.yaml → nodes → outreach-module → acceptance_criteria
**Finding:** Current AC says "case advances to outreach_in_progress when first outreach approved" which contradicts the approval → send two-step. Build plan implies transition on first approved (not first sent). Ambiguity means the state machine is unpredictable.
**Fix applied:** Canonical rule defined: case advances to outreach_in_progress when the FIRST outreach_action for the case is approved (not sent). Case advances to pending_facility_response when first outreach_action is marked sent.

### C-07 — User model: flat role_key vs user_roles join table unresolved
**Agent:** Structuralist
**Location:** manifest.yaml → shared_models → User
**Finding:** Build plan defines a normalized user_roles join table but the User shared model has a flat role_key field. Phase 1 uses denormalized role_key for simplicity but auth-module ACs reference "user_roles tables populated" — contradiction.
**Fix applied:** User model clarified: role_key is denormalized on user profile (single active role per user for Phase 1). auth-module seeds a user_roles lookup table but effective role is enforced from role_key on user profile. user_roles table kept for forward-compat.

### C-08 — ClinicalAssessment ↔ facility_capabilities field misalignment
**Agent:** Contractualist
**Location:** manifest.yaml → shared_models → ClinicalAssessment; nodes → facilities-module → acceptance_criteria
**Finding (4 sub-issues):**
  a. dialysis_type is free-text in ClinicalAssessment but facility capabilities use discrete booleans (accepts_hd, in_house_hemodialysis, accepts_peritoneal_dialysis). Matching cannot work.
  b. ClinicalAssessment has wound_care_needs but facility has accepts_wound_vac — field names don't match.
  c. oxygen_required (boolean) in assessment has no corresponding facility capability.
  d. memory_care_needed missing from ClinicalAssessment though facility has accepts_memory_care.
**Fix applied:** dialysis_type → enum: "hd | peritoneal | none"; wound_care_needs → wound_vac_needs (renamed to match facility); memory_care_needed boolean added to ClinicalAssessment; accepts_oxygen_therapy added to facility_capabilities.

### C-09 — OutreachAction: description says "5-state" but enum has 6 states; failed state has no recovery
**Agent:** Contractualist
**Location:** manifest.yaml → shared_models → OutreachAction
**Finding:** Description says "5-state approval machine: draft → pending_approval → approved → sent" but enum includes `canceled` and `failed` — that's 6 states. `failed` state has no defined recovery path (coordinator cannot cancel it or retry it).
**Fix applied:** Description updated to "6-state"; `failed` recovery path defined: coordinator can transition failed → canceled (no auto-retry in Phase 1); outreach-module AC updated accordingly.

### C-10 — matching-module missing from auth-module.connects_to
**Agent:** Contractualist
**Location:** manifest.yaml → nodes → auth-module → connects_to
**Finding:** matching-module calls auth middleware (JWT validation, role check) but auth-module.connects_to does not list matching-module. Asymmetric graph is a governance error.
**Fix applied:** matching-module added to auth-module.connects_to.

### C-11 — No file upload endpoint for spreadsheet import (merged with C-03)
**Agent:** Pathfinder
*Merged into C-03 above.*

### C-12 — FacilityMatch: no selected_for_outreach flag; no "Select For Outreach" endpoint
**Agents:** Contractualist, Pathfinder
**Location:** manifest.yaml → shared_models → FacilityMatch; nodes → matching-module, outreach-module
**Finding:** The UI has a "Select For Outreach" action on the Facility Match tab but no shared model field or API endpoint defines this selection. Without a selection flag, the handoff from matching to outreach is undefined.
**Fix applied:** selected_for_outreach boolean added to FacilityMatch; PATCH /api/v1/cases/{id}/matches/{match_id}/select AC added to matching-module.

---

## IMPORTANT Findings (18 unique, carried forward as warnings)

### I-01 — Multi-tenancy: middleware alone, no Supabase RLS ACs
**Agent:** Adversary | **Partially fixed:** RLS AC added to core-infrastructure.

### I-02 — read_only role: completely undefined in permission matrix
**Agents:** Adversary, Skeptic | **Fixed:** read_only defined in auth-module AC (view-only all data, no writes).

### I-03 — Geography score: null fallback undefined (patient_zip null or facility lat/lng null)
**Agent:** Adversary | **Fixed:** geography fallback AC added to matching-module (null → score 0.0, no exclusion).

### I-04 — Scoring weights: qualitative ("very high", "medium") not quantitative
**Agent:** Skeptic | **Fixed:** Numeric weights added to matching-module (payer_fit: 35%, clinical_fit: 30%, level_of_care: 20%, geography: 10%, preference: 5%).

### I-05 — case_activity_events not in shared_models
**Agent:** Skeptic | **Partially fixed:** CaseActivityEvent noted in core-infrastructure AC; not promoted to full shared model (single node publishes, multiple nodes subscribe — treated as event bus contract, documented in AC).

### I-06 — Manager "read access to all" contradicts "close cases" capability
**Agent:** Skeptic | **Fixed:** auth-module AC corrected: manager can read all data AND close cases (PATCH status → closed).

### I-07 — Template endpoint ownership split: outreach-module and admin-surfaces both claim CRUD
**Agent:** Contractualist | **Fixed:** admin-surfaces owns template CRUD (POST/PATCH); outreach-module reads templates only (GET /api/v1/templates/outreach). Duplicate POST/PATCH removed from outreach-module.

### I-08 — Import endpoint ownership split: intake-module and admin-surfaces both claim GET /imports
**Agent:** Contractualist | **Fixed:** intake-module owns import workflow (upload, map, validate, commit, status check); admin-surfaces has read-only view (GET /api/v1/imports for monitoring).

### I-09 — FacilityMatch: is_selected flag missing (was C-12)
*Merged into C-12 above.*

### I-10 — Declined outcome: outcomes-module must explicitly set declined_retry_needed status
**Agent:** Skeptic | **Fixed:** Explicit AC added to outcomes-module: declined outcome advances case to declined_retry_needed state.

### I-11 — Outreach `failed` state: no recovery endpoint
**Agent:** Pathfinder | **Fixed (merged with C-09):** POST /api/v1/outreach-actions/{id}/cancel accepts failed state as input; coordinator logs outcome manually.

### I-12 — Decline-retry: no frontend UX defined
**Agent:** Pathfinder | **Fixed:** frontend-app-shell AC updated: Operations Queue shows declined_retry_needed cases with "Route Retry" action; coordinator UI for selecting retry destination.

### I-13 — Rate limiting / auth throttling: not mentioned anywhere
**Agent:** Adversary | **Fixed:** auth-module AC adds rate limiting requirement for login endpoint.

### I-14 — Email stub: privacy risk if draft bodies logged to console
**Agent:** Adversary | **Warning only:** Stub implementation AC notes that email content must not be logged in plaintext; mock delivery records sent status only.

### I-15 — analytics-module SLA: 2s for 500 cases may not scale to 5000+
**Agent:** Skeptic | **Warning only:** Response time target updated to <2s for 1000 cases in standard range; larger volumes require pagination.

### I-16 — Backward transitions in clinical module: vague ("clinical status worsens")
**Agent:** Skeptic | **Fixed:** clinical-module AC clarified: backward transition from under_clinical_review → needs_clinical_review permitted for clinical_reviewer and admin; requires transition_reason text.

### I-17 — PATCH /cases/{id}: no field-level permission enforcement
**Agent:** Adversary | **Fixed:** intake-module AC notes: intake_staff may update intake fields only; placement_coordinator may update priority and assignment fields; clinical fields protected.

### I-18 — admin-surfaces kitchen-sink concern (users, templates, imports, org, reference data)
**Agent:** Structuralist | **Warning only (architecture decision):** Acceptable for Phase 1 operational scope. Noted as ADR candidate if node grows beyond 15 files during build.

---

## MINOR Findings (12, logged, no manifest changes required)

M-01 (Adversary): `active_status` on Facility could use archived enum instead of boolean
M-02 (Adversary): AuditEvent missing session_id for non-interactive access tracking
M-03 (Adversary): No mention of HTTPS/TLS enforcement in deployment ACs
M-04 (Adversary): case_assignments table missing created_at index for performance
M-05 (Skeptic): PatientCase missing case_number (human-readable reference)
M-06 (Skeptic): PatientCase missing assigned_coordinator_user_id (denormalized for queue performance)
M-07 (Skeptic): outreach_actions missing follow_up_due_date field
M-08 (Skeptic): facility_matches missing generated_by enum (rules_engine is only option now but Phase 2 may add AI)
M-09 (Skeptic): No mention of Alembic downgrade scripts in AC
M-10 (Structuralist): core-infrastructure AC list is overlong (10 items, some could move to per-module ACs)
M-11 (Structuralist): frontend-app-shell file_scope "frontend/**" is ambiguous (could mean Next.js root or subdirectory)
M-12 (Contractualist): FacilityMatch.generated_by default is "rules_engine" but should be an enum for Phase 2 voice AI compatibility

---

## Status

**CRITICALs resolved:** 12/12 (all addressed in manifest revision)
**IMPORTANTs resolved:** 13/18 fixed in manifest; 5 logged as warnings
**MINORs:** 12 logged; no manifest changes
**Outcome:** Manifest updated. Proceeding to Pass 2 re-dispatch.
