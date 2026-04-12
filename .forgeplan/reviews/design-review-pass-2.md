# Design Review — Pass 2
**Date:** 2026-04-10
**Tier:** LARGE
**Agents:** Adversary, Skeptic, Structuralist, Contractualist, Pathfinder
**Artifacts reviewed:** `.forgeplan/manifest.yaml` (revision 1, post-Pass-1 fixes)

---

## Summary

| Agent | CRITICAL | IMPORTANT | MINOR |
|-------|----------|-----------|-------|
| Adversary | 0 | 2 | 3 |
| Skeptic | 0 | 5 | 4 |
| Structuralist | 0 | 3 | 4 |
| Contractualist | 0 | 2 | 3 |
| Pathfinder | 0 | 2 | 2 |
| **Total (raw)** | **0** | **14** | **16** |
| **After dedup** | **0** | **10** | **10** |

**All 12 Pass 1 CRITICALs confirmed resolved.**

---

## Pass 1 CRITICAL Verification

| CRITICAL | Status |
|----------|--------|
| C-01 State machine allowlist | RESOLVED — formal allowlist in manifest; core-infra AC enforces |
| C-02 SSTI injection | RESOLVED — allowlisted variables, sandbox renderer required |
| C-03 File upload missing | RESOLVED — multipart AC, 10MB limit, content-type validation |
| C-04 AuditEvent immutability | RESOLVED — Postgres trigger AC + ORM insert-only |
| C-05 Missing shared models | RESOLVED — 6 new models added (13 total) |
| C-06 outreach_pending_approval contradiction | RESOLVED — canonical rule: first approved→outreach_in_progress |
| C-07 User role_key vs user_roles | RESOLVED — denormalized Phase 1 rationale documented |
| C-08 ClinicalAssessment↔FacilityCapabilities | RESOLVED — field names aligned, enums fixed |
| C-09 OutreachAction 6-state fix | RESOLVED — description updated; failed→canceled recovery defined |
| C-10 auth-module.connects_to asymmetry | RESOLVED — matching-module added |
| C-11 (merged with C-03) | RESOLVED |
| C-12 selected_for_outreach | RESOLVED — field added to FacilityMatch; select endpoint defined |

---

## IMPORTANT Findings Fixed in This Pass (10)

| ID | Finding | Fix Applied |
|----|---------|-------------|
| I-A2-01 | Closed case mutation protection missing | AC added to core-infrastructure |
| I-A2-02 | facilities-module write role restrictions missing | Explicit role gates added to all write ACs |
| I-S2-01 | Multi-facility selection ambiguity | Clarified: multiple selections allowed (parallel outreach) |
| I-S2-02 | FacilityMatch missing level_of_care_fit_score | Field added to FacilityMatch shared model |
| I-S2-04 | No accepted→declined_retry_needed transition | Added to state_machine_transitions |
| I-S2-05 | phone_manual/task bypasses "first approved" trigger | AC updated: atomically fires approve+send transitions |
| I-19-C | Hard exclusions missing bariatric/iv_antibiotics/tpn/isolation | Full capability→exclusion mapping enumerated in AC |
| I-20-C | behavioral_complexity_flag missing from ClinicalAssessment | behavioral_complexity_flag boolean added |
| I-19-P | Failed import job: no recovery UX | Frontend AC updated with error summary + "Start New Import" |
| I-20-P | Select For Outreach: no guided handoff to outreach tab | Frontend AC updated with contextual prompt and pre-fill |

---

## Remaining IMPORTANT Findings (logged as warnings, no manifest changes)

**I-W-01 — Structuralist: connects_to lists are partially redundant with inverse depends_on**
Per-module connects_to lists mirror the inverse depends_on graph for auth-module and core-infrastructure. Architecturally redundant but acceptable — explicit documentation of all connections is preferable for a LARGE HIPAA-regulated system. Logged as warning; convention clarified in wiki.

**I-W-02 — Structuralist: auth-module connects_to entire system**
auth-module provides JWT middleware to all service modules. Having 9 entries in connects_to accurately reflects that every module consumes auth. This is inherent to the architecture, not a design flaw. Warning only.

---

## Status

**CRITICALs:** 0 (down from 12 in Pass 1)
**IMPORTANTs:** 10 fixed; 2 accepted as warnings
**Outcome:** Proceeding to Pass 3 for verification of new fixes.
