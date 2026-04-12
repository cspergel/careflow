# Plan Review — Pass 2 (Verification)
**Date:** 2026-04-10
**Tier:** LARGE
**Agents:** Adversary, Skeptic, Contractualist
**Artifacts reviewed:** `.forgeplan/plans/implementation-plan.md` (v2 — post-Pass-1 fixes)

---

## Summary

| Agent | CRITICAL | IMPORTANT | MINOR |
|-------|----------|-----------|-------|
| Adversary | 0 | 3 | 3 |
| Skeptic | 1 | 3 | 0 |
| Contractualist | 1 | 3 | 1 |
| **Total (raw)** | **2** | **9** | **4** |
| **After dedup** | **1** | **7** | **3** |

**All 11 Pass 1 CRITICAL findings verified resolved in the plan.**

---

## Pass 1 Fix Verification

| Fix | Status |
|-----|--------|
| P1-C-01: Rate limit 10/min | VERIFIED |
| P1-C-02: Field names (trach, accepts_behavioral_complexity, accepts_isolation_cases) | VERIFIED |
| P1-C-03: overall_score (not total_score) | VERIFIED |
| P1-C-04: File scope modules/ prefix | VERIFIED |
| P1-C-05: CaseStatusHistory model defined | VERIFIED |
| P1-C-06: RLS creation instructions added | VERIFIED |
| P1-C-07: Operations queue role access (4 roles) | VERIFIED in plan; spec not yet updated (see P2-C-01) |
| P1-C-08: Analytics dependency corrected | VERIFIED |
| P1-C-09: Admin-surfaces includes outreach-module dep | VERIFIED |
| P1-C-10: PHI-in-logs enforcement added | VERIFIED |
| P1-C-11: SUPABASE_SERVICE_ROLE_KEY usage restriction | VERIFIED |

---

## Remaining CRITICAL (1 — in specs, not the plan)

**P2-C-01** — Operations queue role gate: analytics-module spec restricts to manager/admin only; plan correctly expands to placement_coordinator + clinical_reviewer + manager + admin, but spec not updated.
Fix: Update `analytics-module.yaml` — change role gate on GET /api/v1/queues/operations to [placement_coordinator, clinical_reviewer, manager, admin]; update AC1 test accordingly.

---

## IMPORTANT Findings (7 — in specs or plan, all fixable)

| ID | Finding | Location |
|----|---------|----------|
| P2-I-01 | auth-module spec interface says "manager and admin" for outreach approval; should be "placement_coordinator and admin" | auth-module.yaml line 92 |
| P2-I-02 | matching-module spec AC4 says "12" field mappings; should be "13" | matching-module.yaml AC4 description |
| P2-I-03 | Plan hard-exclusion table has 14 rows (duplicate in_house_hemodialysis); should be 13 | implementation-plan.md |
| P2-I-04 | Plan line 165: "update PatientCase.status_entered_at" — field not in manifest; redundant with CaseStatusHistory.entered_at join | implementation-plan.md |
| P2-I-05 | analytics-module spec SlaFlag references status_entered_at on PatientCase; plan uses JOIN to case_status_history | analytics-module.yaml |
| P2-I-06 | Geography scoring: plan uses step function; matching-module spec AC9 describes linear formula | matching-module.yaml AC9 |
| P2-I-07 (ADV) | auth-module spec outreach interface approval role: same as P2-I-01 | auth-module.yaml |

---

## MINOR Findings (3 — deferred or low risk)

- P2-ADV-04: Rate limiter single-worker constraint needs startup assertion (not enforced, only documented)
- P2-ADV-05: CaseStatusHistory SLA query needs DISTINCT ON to avoid stale rows on status re-entry
- P2-ADV-06: CSRF pattern for SSR cookie auth not specified (Bearer header vs cookie — clarify in frontend section)

---

## Status

**CRITICALs in plan:** 0 (all resolved in v2)
**CRITICALs in specs:** 1 (P2-C-01 — fixing analytics-module spec now)
**IMPORTANTs:** 7 — fixing all spec-level items; plan fix for P2-I-03 and P2-I-04
**Outcome:** Fixing specs and plan → Pass 3 clean verification expected.
