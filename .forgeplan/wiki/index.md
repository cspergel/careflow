# PlacementOps — Project Knowledge Base

**Tier:** LARGE
**Discovered:** 2026-04-10 (re-discovered with full document read)
**Stack:** Python (FastAPI + SQLAlchemy) + TypeScript (Next.js) / Supabase / Docker

## What It Is

A post-acute placement operating system that turns daily hospital census data and clinician review into fast, trackable, facility-matched discharge workflows.

**Replaces:** spreadsheets emailed from offshore intake staff, manual facility phone trees, sticky-note tracking, institutional knowledge locked in individual heads.

## Users & Roles

| Role | Default Landing | Key Permissions |
|------|----------------|-----------------|
| intake_staff | Intake Workbench | Create cases, mark intake complete |
| clinical_reviewer | Operations Queue (clinical) | Create/finalize assessments |
| placement_coordinator | Operations Queue (outreach) | Generate matches, create/approve outreach, log outcomes |
| manager | Dashboard | View all; close cases; analytics |
| admin | Admin Settings | Everything |

## Node Map (Phase 1)

Build order by dependency:

1. `core-infrastructure` — migrations (20+ tables), auth middleware, tenant isolation, audit bus
2. `auth-module` — Supabase Auth, RBAC (5 roles + read_only)
2. `facilities-module` — facility directory, capability matrix, insurance rules, contacts, preferences
3. `intake-module` — case CRUD, XLSX/CSV import, state machine (intake stages)
4. `clinical-module` — 20+ field assessments, reviewer workflow, assessment versioning
5. `matching-module` — weighted scoring engine, hard exclusions, ranked facility_matches
6. `outreach-module` — draft → approve → send workflow, phone_manual/task channels, template CRUD
7. `outcomes-module` — declines (with reason codes), placements, retry routing, closure
8. `analytics-module` — SLA aging flags, KPI dashboard, queue summary, outreach performance
8. `admin-surfaces` — user mgmt, template CRUD, import monitoring, org settings, reference data
9. `frontend-app-shell` — Next.js, 10 screens, 6-tab case detail, dense operational UX (built last)

## State Machine (14 states)

```
new → intake_in_progress → intake_complete → needs_clinical_review
→ under_clinical_review → ready_for_matching → facility_options_generated
→ outreach_pending_approval → outreach_in_progress → pending_facility_response
→ accepted → placed
→ declined_retry_needed (loops back to ready_for_matching or outreach_pending_approval)
Any active state → closed
```

## 10 Frontend Screens

1. Dashboard (manager default)
2. Intake Workbench (intake_staff default)
3. Spreadsheet Import
4. Operations Queue
5. Patient Case Detail (6 tabs: Overview, Clinical Review, Facility Matches, Outreach, Timeline, Audit)
6. Facility Directory
7. Facility Detail (4 tabs: Overview, Capabilities, Insurance, Contacts)
8. Outreach Dashboard
9. Analytics Dashboard
10. Admin Settings (4 tabs: Users, Templates, Import Jobs, Org Settings)

## SLA / Aging Rules

| State | Yellow Flag | Red Flag |
|-------|------------|---------|
| needs_clinical_review | >4 hours | — |
| under_clinical_review | >8 hours | — |
| outreach_pending_approval | >2 hours | — |
| pending_facility_response | >24 hours | >48 hours |
| declined_retry_needed | — | >8 hours |

## API Structure

50+ endpoints under `/api/v1`. Key groups:
- `/auth/*` — login, logout, me
- `/cases/*` — CRUD, status transitions, assign, intake-complete
- `/imports/*` — create, map-columns, validate, commit, status
- `/assessments/*` — clinical review
- `/facilities/*` + `/insurance-rules/*` — facility management
- `/cases/{id}/matches/generate` + `/matches` — matching engine
- `/outreach-actions/*` — draft/approve/send workflow
- `/cases/{id}/outcomes` + `/timeline` — outcomes and activity
- `/queues/*` — intake, operations, outreach, manager-summary
- `/templates/outreach` — template management
- `/admin/*` — user, org, reference data
- `/analytics/*` — dashboard, outreach-performance

## Phase 2 (Not In Scope Now)

Voice AI module: Twilio SIP + LiveKit Agents + OpenAI Realtime. Data model is already voice-ready:
- `outreach_actions.channel` enum includes `voice_ai`
- `outreach_actions` has `call_transcript_url`, `call_duration_seconds`, `call_outcome_summary`
- `facility_contacts` has `phone_extension`, `best_call_window`, `phone_contact_name`
- `outreach_templates.template_type` supports `voice_ai_script`
