# Plan Review — Pass 4 (Final Clean Verification)
**Date:** 2026-04-10
**Tier:** LARGE
**Agents:** Adversary, Contractualist
**Artifacts reviewed:** `.forgeplan/plans/implementation-plan.md` (v3); all specs; manifest

---

## Summary

| Agent | CRITICAL | IMPORTANT | MINOR |
|-------|----------|-----------|-------|
| Adversary | 0 | 3 | 3 |
| Contractualist | 0 | 2 | 2 |
| **After dedup** | **0** | **4** | **5** |

---

## Pass 3 Fix Verification

| Fix | Status |
|-----|--------|
| P3-C-01: auth-module AC7/AC8 updated to specific endpoints + queues/operations | VERIFIED |
| P3-I-01: auth-module line 98 read_only analytics claim removed | VERIFIED |
| P3-I-02: endpoint path outreach-performance in plan | VERIFIED |
| P3-M-01: geography_score uses facility_lat/facility_lng | VERIFIED |

All Pass 3 fixes confirmed correctly applied. No regressions.

---

## IMPORTANT Findings Fixed in This Pass

**P4-I-01** — auth-module AC11 test did not verify read_only is denied analytics GET endpoints
Fix applied:
- `auth-module.yaml` AC11 description: updated to clarify analytics/admin GETs also return 403
- `auth-module.yaml` AC11 test: added `assert 403 on GET /api/v1/queues/operations; assert 403 on GET /api/v1/analytics/dashboard`

**P4-I-02** — manifest RBAC wording for read_only ambiguous (parenthetical "no analytics" unclear about GET)
Fix applied:
- `manifest.yaml` line 446: reworded to `read_only=GET only on cases/facilities/clinical+403 on ALL analytics endpoints (including GET)+403 on all admin endpoints+all POST/PATCH/DELETE return 403`

**P4-I-03** — SLA query missing DISTINCT ON — cases re-entering the same status would produce duplicate rows and incorrect aging
Fix applied:
- `implementation-plan.md` Node 8b SLA query: changed to `SELECT DISTINCT ON (pc.id)` with `ORDER BY pc.id, csh.entered_at DESC`; added explanatory comment about re-entry scenario

**P4-I-04** — CaseStatusHistory missing from core-infrastructure shared_dependencies; analytics interface contract with core-infra omitted it
Fix applied:
- `core-infrastructure.yaml` shared_dependencies: added CaseStatusHistory
- `analytics-module.yaml` interface contract for core-infrastructure: added CaseStatusHistory to the list of ORM models read; added note about JOIN on (patient_case_id, to_status)

---

## MINOR Findings Fixed in This Pass

**P4-M-01** — Dead `distance_miles(zip1, zip2)` function in plan misleads implementer into ZIP-to-ZIP distance logic
Fix applied: removed the 4-line dead function from `implementation-plan.md` Node 6

**P4-M-02** — `GET /api/v1/queues/manager-summary` missing from plan Node 8b major responsibilities
Fix applied: added manager-summary to Node 8b major responsibilities with description of aging distribution, sla_breach_cases list, total_active_cases count

**P4-M-03** — auth-module AC6 test used blanket `/api/v1/analytics` (not a real endpoint; would get 404 not 403)
Fix applied: `auth-module.yaml` AC6 test: replaced `assert 403 on GET /api/v1/analytics` with `assert 403 on GET /api/v1/analytics/dashboard; assert 403 on GET /api/v1/queues/operations`

**P4-M-04** — auth-module line 101 said "read_only may view admin surfaces via GET only" — contradicts admin-surfaces spec requiring admin role for all endpoints
Fix applied: `auth-module.yaml` line 101: updated to "admin-surfaces imports to restrict all endpoints to admin role only; all other roles including read_only receive 403"

**P4-M-05** — frontend-app-shell.yaml /dashboard screen listed read_only as having access; backend will return 403
Fix applied: `frontend-app-shell.yaml` line 46: changed from "manager/admin/read_only" to "manager and admin only"

---

## Clean Verification Results

| Area | Result |
|------|--------|
| Operations queue role access (6 locations) | PASS |
| Endpoint path consistency (outreach-performance) | PASS |
| Geography step function (lat/lng, not ZIP) | PASS |
| CaseStatusHistory consistency (5 locations) | PASS |
| Hard-exclusion field mappings (13, no duplicates) | PASS |
| Admin-surfaces dependency on outreach-module | PASS |

---

## Status

**CRITICALs:** 0 remaining
**IMPORTANTs:** 0 remaining
**Outcome:** Plan review PASSED. Proceeding to Step 4: deep-build.
