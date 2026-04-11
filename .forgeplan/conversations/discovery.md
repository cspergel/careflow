# Discovery Conversation — PlacementOps
**Date:** 2026-04-10
**Mode:** Document Import (full re-discovery)
**Sources:**
  - `Planning Docs/PlacementOps_Master_Build_Plan.md` (primary — 13 parts: product def, users/roles, tech architecture, DB schema, state machine, API contract, frontend architecture, matching engine, outreach model, voice AI module, build sequence, success criteria, compliance)
  - `Planning Docs/PlacementOps_vs_CareFlow_Synthesis.md` (synthesis — PlacementOps as master platform, CareFlow AI absorbed as Phase 2 voice module)
**Tier:** LARGE

## Resolved Ambiguities

| Ambiguity | Resolution |
|-----------|-----------|
| Email delivery provider | Stubbed for Phase 1. Email marked sent but not delivered. Provider wired in Phase 2. |
| Background jobs | FastAPI BackgroundTasks. No external broker for Phase 1. |
| Deployment target | Docker only. Host TBD. |
| Admin module structure | Consolidated `admin-surfaces` module. Includes reference data endpoints. |
| JWT handling | Next.js forwards Supabase JWT Bearer directly to FastAPI middleware. |
| Multi-tenancy | organization_id enforced at Supabase RLS + FastAPI middleware (defense in depth for PHI). |
| Operations Queue | Cross-module frontend view backed by /queues/operations endpoint in analytics-module. |
| Import formats | XLSX + CSV both supported via openpyxl/csv. |
| Decline retry routing | Manual coordinator choice via status-transition endpoint. |
| Scoring algorithm | Weighted rules engine with hard exclusions: payer (very high), clinical capability match (mandatory/hard exclusion), level_of_care_fit (very high), geography/distance (medium-high), preferred facility bonus (medium). |
| phone_manual/task channels | No approval required. Coordinator creates, logs result. Immediately enters sent state. |
| Frontend screen count | 10 screens (not 16): Dashboard, Intake Workbench, Spreadsheet Import, Operations Queue, Patient Case Detail, Facility Directory, Facility Detail, Outreach Dashboard, Analytics Dashboard, Admin Settings. |
| Case Detail tabs | 6 tabs: Overview, Clinical Review, Facility Matches, Outreach, Timeline, Audit. |

## Key Improvements Over Initial Discovery

- Correct API endpoint paths from Part 6 of build plan (not invented paths)
- phone_manual and task channels captured as Phase 1 without approval flow
- SLA/aging rules captured in analytics-module acceptance criteria
- Matching engine scoring weights and hard exclusion logic fully specified
- Frontend screen inventory corrected to 10 screens with tab structure
- Voice AI data model fields included in shared models (forward-compatible schema)
- Compliance constraints (PHI, HIPAA, audit trail) reflected in acceptance criteria
- Reference data endpoints (hospitals, decline-reasons, payers) mapped to admin-surfaces
