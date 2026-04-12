# Design Review — Pass 3
**Date:** 2026-04-10
**Tier:** LARGE
**Agents:** Adversary, Skeptic, Contractualist, Pathfinder (4 agents; Structuralist fixes were graph additions verified locally)
**Artifacts reviewed:** `.forgeplan/manifest.yaml` (post-Pass-2 fixes)

---

## Summary

| Agent | CRITICAL | IMPORTANT | MINOR |
|-------|----------|-----------|-------|
| Adversary | 0 | 2 | 3 |
| Skeptic | 0 | 2 | 4 |
| Contractualist | 0 | 0 | 3 |
| Pathfinder | 0 | 1 | 2 |
| **Total (dedup)** | **0** | **5** | **8** |

**All 5 Pass 2 IMPORTANT findings verified resolved.**

---

## IMPORTANT Findings — Fixed in This Pass

| ID | Finding | Fix Applied |
|----|---------|-------------|
| I-A3-01 | Outcomes endpoint missing role gate | Added "placement_coordinator or admin only; 403 for all other roles" |
| I-A3-02 | Only decline outcomes wrote AuditEvent | Changed to: all outcomes write AuditEvent |
| I-S3-01 | Declined outcome facility_id optional, breaks analytics | facility_id now required for declined outcomes; family_declined/withdrawn permit null |
| I-S3-02 | Re-scoring silently discards coordinator facility selections | Frontend warning AC added; behavior documented (no carry-forward) |
| P3-01 | OutreachAction cannot be canceled from approved/sent states | Cancel now permitted from approved; sent records permanent; auto-cancel draft/pending/approved on case acceptance/placement |

---

## Additional fixes from MINOR findings

- family_declined and withdrawn outcome_types: AC now specifies they advance to closed (manager must confirm per state machine); decline_reason seed data updated to include rescission codes
- Orphaned outreach on case acceptance: auto-cancel of draft/pending_approval/approved actions on case→accepted/placed; sent actions remain as permanent records

---

## Remaining MINOR warnings (not blocking, addressed at spec time)

- M-S3-03: Can new outreach be created while case is in pending_facility_response? (clarify at spec)
- M-A3-04: DELETE endpoints → 405 for all PHI tables (add to core-infra spec)
- M-A3-05: ImportJob file storage key missing from model (add at spec time)
- M-16-C: level_of_care_fit naming inconsistency in matching AC (fix at spec time)
- M-17-C: in_house_hd_required field consumed inconsistently (fix at spec time)

---

## Status

**CRITICALs:** 0 (third consecutive pass with 0 CRITICAL findings)
**IMPORTANTs:** 5 fixed; 0 remaining
**Outcome:** Proceeding to Pass 4 for final verification.
