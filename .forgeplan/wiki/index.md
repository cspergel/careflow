# PlacementOps — Project Knowledge Base

**Tier:** LARGE
**Discovered:** 2026-04-10
**Stack:** Python (FastAPI) + TypeScript (Next.js) / Supabase / Docker

## Architecture Overview

PlacementOps is a post-acute placement operating system. The backend is a Python modular monolith (FastAPI) with 10 modules. The frontend is a Next.js app (11th node: frontend-app-shell).

### Node Map
- `core-infrastructure` → shared foundation, migrations, auth middleware, audit
- `auth-module` → Supabase Auth integration, RBAC (5 roles)
- `intake-module` → patient case CRUD, XLSX/CSV import, state machine intake
- `clinical-module` → 20+ field clinical assessments, reviewer workflow
- `facilities-module` → facility directory, capabilities, insurance rules, preferences
- `matching-module` → weighted scoring engine, ranked facility matches
- `outreach-module` → email draft approval workflow (stubbed delivery)
- `outcomes-module` → placement outcomes, decline reasons, retry routing
- `analytics-module` → manager KPI dashboards
- `admin-surfaces` → admin CRUD for users, templates, import jobs, org settings
- `frontend-app-shell` → 16-screen Next.js app

### State Machine (13 states)
new → intake_in_progress → intake_complete → needs_clinical_review → under_clinical_review → ready_for_matching → facility_options_generated → outreach_pending_approval → outreach_in_progress → pending_facility_response → accepted → placed (+ declined_retry_needed, closed)
