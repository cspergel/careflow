# Node: frontend-app-shell

## Operational Summary
- **Status:** reviewed
- **Node type:** frontend
- **Tracked files:** 58
- **Test files:** 3
- **Dependencies:** 9 | **Connections:** 9
- **Key entrypoints:** frontend/middleware.ts, frontend/src/lib/supabase/server.ts, frontend/src/app/layout.tsx, frontend/src/app/login/page.tsx, frontend/src/app/dashboard/page.tsx
- **Recent issues:** review/reviewer: intake_complete | review/reviewer: facility_options_generated | review/reviewer: accepted

## Decisions (from @forgeplan-decision markers)
- **D-frontend-4-tailwind-v4**: Tailwind v4 with tw-animate-css plugin. Why: spec requires tw-animate-css NOT tailwindcss-animate; Tailwind v4 config is minimal, CSS variables in globals.css. [frontend/tailwind.config.ts:2]
- **D-frontend-1-openapi-ts-config**: Used @hey-api/openapi-ts v0.43.x config format (input/output flat style). Why: spec pins ^0.43.0; this version uses input/output at root level. [frontend/openapi-ts.config.ts:3]
- **D-frontend-2-middleware-token-refresh**: Middleware only refreshes token, access control in server components. Why: CVE-2025-29927 demonstrated middleware-only auth can be bypassed; real auth gating happens in each server component. [frontend/middleware.ts:15]
- **D-frontend-3-api-client-placeholder**: Placeholder client exported from index.ts. Why: actual generation requires FastAPI server; placeholder provides type-safe interface for current-phase development. [frontend/src/client/index.ts:7]
- **D-frontend-5-nuqs-v1-api**: Using nuqs v1 API (useQueryStates, parseAsString, etc). Why: spec pins nuqs@^1.17.0; v1 and v2 have different import paths. [frontend/src/components/CaseTable.tsx:25]
- **D-frontend-6-rsi-dynamic-import**: react-spreadsheet-import loaded with next/dynamic + ssr:false. Why: library uses Chakra UI internally and browser-only APIs; SSR would fail. [frontend/src/app/intake/import/page.tsx:22]

## Past Findings
| Pass | Agent | Finding | Resolution |
|------|-------|---------|------------|
| review | reviewer | intake_complete | needs_clinical_review |
| review | reviewer | facility_options_generated | outreach_pending_approval |
| review | reviewer | accepted | declined_retry_needed |

## Cross-References
- Depends on: auth-module
- Depends on: intake-module
- Depends on: clinical-module
- Depends on: facilities-module
- Depends on: matching-module
- Depends on: outreach-module
- Depends on: outcomes-module
- Depends on: analytics-module
- Depends on: admin-surfaces
- Connected to: auth-module
- Connected to: intake-module
- Connected to: clinical-module
- Connected to: facilities-module
- Connected to: matching-module
- Connected to: outreach-module
- Connected to: outcomes-module
- Connected to: analytics-module
- Connected to: admin-surfaces
