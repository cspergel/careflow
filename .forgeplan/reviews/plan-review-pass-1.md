# Plan Review — Pass 1
**Date:** 2026-04-10
**Tier:** LARGE
**Agents:** Adversary, Skeptic, Structuralist, Contractualist, Pathfinder
**Artifacts reviewed:** `.forgeplan/plans/implementation-plan.md` (v1)

---

## Summary

| Agent | CRITICAL | IMPORTANT | MINOR |
|-------|----------|-----------|-------|
| Adversary | 5 | 8 | 4 |
| Skeptic | 3 | 7 | 5 |
| Structuralist | 3 | 6 | 3 |
| Contractualist | 4 | 8 | 6 |
| Pathfinder | 2 | 5 | 3 |
| **Total (raw)** | **17** | **34** | **21** |
| **After dedup** | **11** | **15** | **8** |

---

## Deduplicated CRITICAL Findings (11 unique)

| ID | Finding | Agents |
|----|---------|--------|
| P1-C-01 | Rate limit 5/min in plan contradicts 10/min in spec and manifest | ADV-01, S-04, Str-S-04, C-I2 |
| P1-C-02 | Hard-exclusion field names wrong in mapping table: `trach_care_needed` → `trach`; `accepts_behavioral` → `accepts_behavioral_complexity`; `accepts_isolation` → `accepts_isolation_cases` | S-01, C2, C3, ADV-11 |
| P1-C-03 | FacilityMatch field `total_score` in plan does not match `overall_score` in manifest/spec | S-02 |
| P1-C-04 | File scope mismatch: plan uses `placementops/NAME/**`; manifest and specs use `placementops/modules/NAME/**` for all 8 feature modules | Str-S-01, S-06, C4 |
| P1-C-05 | `case_status_history` (and `CaseStatusHistory` ORM model) not defined anywhere in plan, manifest shared_models, or core-infrastructure spec — yet referenced in analytics SLA computation and multiple module ACs | S-03, PF-01 |
| P1-C-06 | RLS policy creation instructions absent from Node 1 build steps — only AuditEvent trigger SQL is given verbatim; builder could skip RLS entirely | ADV-02 |
| P1-C-07 | Operations queue (`GET /api/v1/queues/operations`) returns 403 to placement_coordinator and clinical_reviewer, but `/queue` is their default landing page — dead end for core workflow | PF-02 |
| P1-C-08 | Analytics-module dependency overstated as "all Phase 2+3 nodes"; manifest and spec say `depends_on: [core-infrastructure, auth-module, outcomes-module]` | Str-S-02 |
| P1-C-09 | Admin-surfaces dependency missing outreach-module; manifest and spec include it | Str-S-03 |
| P1-C-10 | PHI-in-logs enforcement mechanism entirely unspecified; FastAPI default error handlers will log request bodies containing PHI | ADV-04 |
| P1-C-11 | `SUPABASE_SERVICE_ROLE_KEY` passed to all modules via shared container environment; no usage gate specified to prevent non-admin code from bypassing RLS | ADV-03 |

---

## Key IMPORTANT Findings (15 unique, top items)

| ID | Finding |
|----|---------|
| P1-I-01 | `FacilityInsuranceRule.accepted_flag boolean` → `accepted_status (enum: accepted|conditional|not_accepted)` |
| P1-I-02 | Clinical-module field listing uses long names (`trach_care_needed`, `vent_dependent`, `iv_antibiotics_needed`, `tpn_needed`) — manifest uses short names (`trach`, `vent`, `iv_antibiotics`, `tpn`) |
| P1-I-03 | Case detail tab names wrong: plan says "Intake, Clinical, Matching, Outreach, Outcomes, Activity"; spec/manifest say "Overview, Clinical Review, Facility Matches, Outreach, Timeline, Audit" |
| P1-I-04 | Matching re-run plan says "clears existing FacilityMatch rows"; spec says old rows are retained, new rows are inserted |
| P1-I-05 | `pending_review` outcome type in manifest PlacementOutcome enum not mentioned in plan's outcomes section |
| P1-I-06 | `FacilityPreference` model missing from shared models table |
| P1-I-07 | JWKS cache TTL not specified; `PyJWKClient(url, lifespan=300)` with fallback behavior needed |
| P1-I-08 | Duplicate detection: plan says `admitted_from`; manifest and spec say `hospital_id` |
| P1-I-09 | Docker Compose api service missing `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWKS_URL` env vars |
| P1-I-10 | `in_house_hd_required` is a compound check (requires BOTH `accepts_hd=true` AND `in_house_hemodialysis=true`) — plan presents it as simple mapping |
| P1-I-11 | Template CRUD rejection: plan says 403; outreach-module spec says 405 |
| P1-I-12 | Auth-module spec outreach interface says "manager and admin" for approval; spec and plan say "placement_coordinator or admin" |
| P1-I-13 | `BackgroundTasks` partial failure (import) — no transaction rollback guidance |
| P1-I-14 | Operations queue 0-result / manager closure confirmation UI not specified in frontend section |
| P1-I-15 | Missing first-run organization bootstrap steps (create org row, provision first admin) |

---

## Status

**CRITICALs:** 11 unique — all must be fixed before proceeding to build
**IMPORTANTs:** 15 — fixing top 11 in plan; 4 deferred to spec-time clarifications
**Outcome:** Fixing plan now → re-dispatch for Pass 2 verification.
