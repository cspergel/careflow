# Build Log: frontend-app-shell

**Node:** frontend-app-shell
**Started:** 2026-04-11
**Builder:** claude-sonnet-4-6

## Pre-Build Spec Challenge

### Assumptions Documented

1. **nuqs version:** Spec requests nuqs@^1.17.0 but research shows v2.x is current (v2.8.9). The spec explicitly pins ^1.17.0 so I will use that. nuqs v1 and v2 have different import paths. Using the spec-specified version.

2. **@hey-api/openapi-ts version:** Spec requests ^0.43.0 but research mentions 0.95.0. I will use ^0.43.0 per spec. This is an older API surface — the config format for 0.43.x differs from 0.95.x.

3. **Tailwind v4 config:** With Tailwind v4, configuration moves largely to CSS. I will create a `postcss.config.ts` using `@tailwindcss/postcss` and a minimal `tailwind.config.ts` for tw-animate-css. shadcn/ui with Tailwind v4 uses CSS custom properties in `globals.css`.

4. **shadcn/ui components:** Since shadcn/ui components are copy-pasted, I will implement the minimal needed UI primitives directly in `frontend/src/components/ui/` without running `npx shadcn init` (which requires interactive TTY). These will be functionally correct implementations of the required components.

5. **Tests:** Using Jest + React Testing Library per the spec note. Creating `frontend/src/__tests__/` for unit tests. The jest config will be in `frontend/jest.config.ts`.

6. **API client placeholder:** `frontend/src/client/index.ts` exports a `createClient` function as a typed placeholder since actual generation requires FastAPI to be running.

7. **The 14 case statuses:** The spec lists 14 statuses. The manifest lists `intake_complete` and `ready_for_clinical_review` as two distinct statuses — but the spec's CaseStatus union uses `ready_for_clinical_review` (not `intake_complete`). I will use exactly the 14 statuses listed in the spec's CaseStatus union.

8. **Queue tab filters:** spec says "intake, clinical, matching, outreach, response, declined-retry" which maps to status groupings (not individual statuses). I will map these to status arrays.

9. **Phone_manual/task bypass:** These channel types bypass draft→pending_approval→approved flow. The DraftEditor will conditionally hide the approval step when channel is `phone_manual` or `task`.

10. **Facility detail tabs (4 tabs):** Spec mentions 4 tabs for `/facilities/[facility_id]` but doesn't name them. I will use: Overview, Capabilities, Insurance, Contacts — matching the Facility data model.

## Decision Markers

- D-frontend-1: Used `@hey-api/openapi-ts@^0.43.0` config format (input/output style)
- D-frontend-2: Implemented shadcn/ui components inline rather than via CLI to support non-interactive environment
- D-frontend-3: Used nuqs v1.x API (parseAsString, useQueryStates from 'nuqs') per spec pin
- D-frontend-4: CSS globals for Tailwind v4 — all CSS variables defined in globals.css, tailwind.config.ts minimal
- D-frontend-5: React Testing Library + Jest for unit tests; test files in src/**/__tests__/

## Build Progress

- [x] package.json
- [x] tsconfig.json
- [x] next.config.ts
- [x] tailwind.config.ts
- [x] postcss.config.mjs
- [x] openapi-ts.config.ts
- [x] middleware.ts
- [x] src/app/layout.tsx
- [x] src/app/globals.css
- [x] src/lib/supabase/server.ts
- [x] src/lib/supabase/client.ts
- [x] src/lib/utils.ts
- [x] src/client/index.ts (placeholder)
- [x] src/components/ui/* (shadcn primitives)
- [x] src/components/StatusBadge.tsx
- [x] src/components/CaseTable.tsx
- [x] src/components/FacilityCard.tsx
- [x] src/components/ActivityTimeline.tsx
- [x] src/components/DraftEditor.tsx
- [x] src/components/FilterBar.tsx
- [x] src/components/Sidebar.tsx
- [x] src/components/ClinicalAssessmentForm.tsx
- [x] src/app/login/page.tsx
- [x] src/app/dashboard/page.tsx
- [x] src/app/intake/page.tsx
- [x] src/app/intake/import/page.tsx
- [x] src/app/queue/page.tsx
- [x] src/app/cases/[case_id]/page.tsx
- [x] src/app/facilities/page.tsx
- [x] src/app/facilities/[facility_id]/page.tsx
- [x] src/app/outreach/page.tsx
- [x] src/app/analytics/page.tsx
- [x] src/app/admin/page.tsx
- [x] Tests
- [x] .env.example (append)
- [x] state.json update
- [2026-04-11T20:45:01.400Z] Created: `frontend/package.json`
- [2026-04-11T20:45:05.042Z] Created: `frontend/tsconfig.json`
- [2026-04-11T20:45:08.615Z] Created: `frontend/next.config.ts`
- [2026-04-11T20:45:17.738Z] Created: `frontend/tailwind.config.ts`
- [2026-04-11T20:45:20.319Z] Created: `frontend/postcss.config.mjs`
- [2026-04-11T20:45:25.596Z] Created: `frontend/openapi-ts.config.ts`
- [2026-04-11T20:45:29.527Z] Created: `frontend/jest.config.ts`
- [2026-04-11T20:45:32.550Z] Created: `frontend/jest.setup.ts`
- [2026-04-11T20:45:42.269Z] Created: `frontend/middleware.ts`
- [2026-04-11T20:45:47.054Z] Created: `frontend/src/lib/supabase/server.ts`
- [2026-04-11T20:45:50.680Z] Created: `frontend/src/lib/supabase/client.ts`
- [2026-04-11T20:45:57.953Z] Created: `frontend/src/lib/utils.ts`
- [2026-04-11T20:46:08.426Z] Created: `frontend/src/client/index.ts`
- [2026-04-11T20:46:14.486Z] Created: `frontend/src/components/ui/badge.tsx`
- [2026-04-11T20:46:20.941Z] Created: `frontend/src/components/ui/button.tsx`
- [2026-04-11T20:46:33.807Z] Created: `frontend/src/components/ui/sheet.tsx`
- [2026-04-11T20:46:40.128Z] Created: `frontend/src/components/ui/tabs.tsx`
- [2026-04-11T20:46:44.761Z] Created: `frontend/src/components/ui/input.tsx`
- [2026-04-11T20:46:48.390Z] Created: `frontend/src/components/ui/label.tsx`
- [2026-04-11T20:47:02.089Z] Created: `frontend/src/components/ui/select.tsx`
- [2026-04-11T20:47:06.076Z] Created: `frontend/src/components/ui/textarea.tsx`
- [2026-04-11T20:47:11.018Z] Created: `frontend/src/components/ui/checkbox.tsx`
- [2026-04-11T20:47:17.524Z] Created: `frontend/src/components/ui/card.tsx`
- [2026-04-11T20:47:21.563Z] Created: `frontend/src/components/ui/separator.tsx`
- [2026-04-11T20:47:32.883Z] Created: `frontend/src/components/ui/form.tsx`
- [2026-04-11T20:47:46.273Z] Created: `frontend/src/components/ui/toast.tsx`
- [2026-04-11T20:48:03.380Z] Created: `frontend/src/components/StatusBadge.tsx`
- [2026-04-11T20:48:27.672Z] Created: `frontend/src/components/CaseTable.tsx`
- [2026-04-11T20:48:51.857Z] Created: `frontend/src/components/FacilityCard.tsx`
- [2026-04-11T20:49:07.783Z] Created: `frontend/src/components/ActivityTimeline.tsx`
- [2026-04-11T20:51:39.431Z] Created: `frontend/src/components/DraftEditor.tsx`
- [2026-04-11T20:51:54.084Z] Created: `frontend/src/components/FilterBar.tsx`
- [2026-04-11T20:52:10.554Z] Created: `frontend/src/components/Sidebar.tsx`
- [2026-04-11T20:52:56.151Z] Created: `frontend/src/components/ClinicalAssessmentForm.tsx`
- [2026-04-11T20:53:07.737Z] Created: `frontend/src/app/globals.css`
- [2026-04-11T20:53:17.844Z] Created: `frontend/src/app/layout.tsx`
- [2026-04-11T20:53:30.352Z] Created: `frontend/src/app/login/page.tsx`
- [2026-04-11T20:53:43.247Z] Created: `frontend/src/app/dashboard/page.tsx`
- [2026-04-11T20:54:20.008Z] Created: `frontend/src/app/intake/page.tsx`
- [2026-04-11T20:55:01.567Z] Created: `frontend/src/app/intake/import/page.tsx`
- [2026-04-11T20:55:39.335Z] Created: `frontend/src/app/queue/page.tsx`
- [2026-04-11T20:56:32.411Z] Created: `frontend/src/app/cases/[case_id]/page.tsx`
- [2026-04-11T20:56:46.979Z] Created: `frontend/src/app/facilities/page.tsx`
- [2026-04-11T20:57:19.613Z] Created: `frontend/src/app/facilities/[facility_id]/page.tsx`
- [2026-04-11T20:57:33.960Z] Created: `frontend/src/app/outreach/page.tsx`
- [2026-04-11T20:57:50.014Z] Created: `frontend/src/app/analytics/page.tsx`
- [2026-04-11T20:58:20.354Z] Created: `frontend/src/app/admin/page.tsx`
- [2026-04-11T20:58:27.045Z] Created: `frontend/src/app/page.tsx`
- [2026-04-11T20:58:41.727Z] Created: `frontend/src/components/__tests__/StatusBadge.test.tsx`
- [2026-04-11T20:58:51.522Z] Created: `frontend/src/components/__tests__/CaseTable.test.tsx`
- [2026-04-11T20:59:08.163Z] Created: `frontend/src/components/__tests__/ClinicalAssessmentForm.test.tsx`
- [2026-04-11T20:59:13.263Z] Created: `frontend/jest.config.ts`
- [2026-04-11T20:59:26.119Z] Edited: `.env.example`
- [2026-04-11T21:00:17.127Z] Created: `frontend/jest.config.ts`
- [2026-04-11T21:00:37.499Z] Created: `frontend/tsconfig.json`
- [2026-04-11T21:00:40.809Z] Created: `frontend/src/app/layout.tsx`
- [2026-04-11T21:00:43.869Z] Created: `frontend/src/app/page.tsx`
- [2026-04-11T21:00:46.804Z] Created: `frontend/src/components/Sidebar.tsx`
- [2026-04-11T21:00:50.247Z] Created: `frontend/src/components/DraftEditor.tsx`
- [2026-04-11T21:00:53.497Z] Created: `frontend/src/app/login/page.tsx`
- [2026-04-11T21:00:56.918Z] Created: `frontend/src/app/intake/page.tsx`
- [2026-04-11T21:01:00.904Z] Created: `frontend/src/app/intake/import/page.tsx`
- [2026-04-11T21:01:04.621Z] Created: `frontend/src/app/queue/page.tsx`
- [2026-04-11T21:01:08.373Z] Created: `frontend/src/app/cases/[case_id]/page.tsx`
- [2026-04-11T21:01:11.729Z] Created: `frontend/src/app/facilities/page.tsx`
- [2026-04-11T21:01:15.577Z] Created: `frontend/src/app/facilities/[facility_id]/page.tsx`
- [2026-04-11T21:01:19.138Z] Created: `frontend/src/app/outreach/page.tsx`
- [2026-04-11T21:01:22.514Z] Created: `frontend/src/app/admin/page.tsx`
- [2026-04-11T21:01:26.344Z] Created: `frontend/jest.config.ts`
- [2026-04-11T21:02:03.706Z] Created: `frontend/src/app/dashboard/page.tsx`
- [2026-04-11T21:02:11.350Z] Created: `frontend/src/app/dashboard/page.tsx`
- [2026-04-11T21:02:15.595Z] Created: `frontend/src/app/dashboard/page.tsx`
- [2026-04-11T21:02:27.111Z] Created: `frontend/src/app/dashboard/DashboardKPIs.tsx`
- [2026-04-11T21:02:36.159Z] Created: `frontend/src/app/analytics/page.tsx`
- [2026-04-11T21:02:50.630Z] Created: `frontend/src/app/analytics/AnalyticsDashboard.tsx`
- [2026-04-11T23:12:01.277Z] Edited: `requirements.txt`
- [2026-04-11T23:12:01.730Z] Created: `frontend/package.json`
- [2026-04-11T23:14:27.031Z] Created: `frontend/package.json`
- [2026-04-11T23:14:32.846Z] Created: `frontend/jest.config.js`
- [2026-04-12T01:24:37.110Z] Created: `frontend/rename-config.js`
- [2026-04-12T01:24:43.451Z] Created: `frontend/rename-config.js`
- [2026-04-12T01:24:47.664Z] Created: `frontend/next.config.mjs`
- [2026-04-12T14:40:21.107Z] Created: `frontend/src/components/ClinicalAssessmentForm.tsx`
- [2026-04-12T14:40:35.706Z] Created: `frontend/src/components/ClinicalAssessmentForm.tsx`
- [2026-04-12T14:40:40.153Z] Created: `frontend/src/components/ClinicalAssessmentForm.tsx`
- [2026-04-12T14:40:47.503Z] Created: `frontend/src/components/ClinicalAssessmentForm.tsx`
- [2026-04-12T14:40:51.628Z] Created: `frontend/src/components/ClinicalAssessmentForm.tsx`
- [2026-04-12T14:40:56.704Z] Created: `frontend/src/components/ClinicalAssessmentForm.tsx`
- [2026-04-12T14:41:07.015Z] Created: `frontend/src/components/ClinicalAssessmentForm.tsx`
- [2026-04-12T14:41:12.057Z] Created: `frontend/src/components/ClinicalAssessmentForm.tsx`
- [2026-04-12T14:41:17.945Z] Created: `frontend/src/components/ClinicalAssessmentForm.tsx`
- [2026-04-12T14:41:37.261Z] Created: `frontend/src/components/__tests__/ClinicalAssessmentForm.test.tsx`
- [2026-04-12T14:41:52.750Z] Created: `frontend/src/components/__tests__/ClinicalAssessmentForm.test.tsx`
- [2026-04-12T14:42:01.434Z] Created: `frontend/src/app/queue/page.tsx`
- [2026-04-12T14:42:06.811Z] Created: `frontend/src/app/queue/page.tsx`
- [2026-04-12T14:42:26.168Z] Created: `frontend/src/client/index.ts`
- [2026-04-12T17:19:54.539Z] Created: `frontend/src/components/ActivityTimeline.tsx`
- [2026-04-12T17:20:02.417Z] Created: `frontend/src/components/ActivityTimeline.tsx`
- [2026-04-12T17:20:06.193Z] Created: `frontend/src/app/facilities/[facility_id]/page.tsx`
- [2026-04-12T17:20:10.564Z] Created: `frontend/src/app/facilities/[facility_id]/page.tsx`
- [2026-04-12T17:20:16.287Z] Created: `frontend/src/app/dashboard/page.tsx`
- [2026-04-12T17:20:35.913Z] Created: `frontend/src/components/StatusBadge.tsx`
- [2026-04-12T17:20:43.914Z] Created: `frontend/src/app/admin/page.tsx`
- [2026-04-12T17:20:46.862Z] Created: `frontend/src/app/admin/page.tsx`
- [2026-04-12T17:20:51.357Z] Created: `frontend/src/components/ClinicalAssessmentForm.tsx`
- [2026-04-12T17:20:54.848Z] Created: `frontend/src/app/analytics/page.tsx`
- [2026-04-12T17:21:02.588Z] Created: `frontend/src/app/dashboard/DashboardKPIs.tsx`
- [2026-04-12T17:21:12.702Z] Created: `frontend/src/app/cases/[case_id]/page.tsx`
- [2026-04-12T17:21:20.897Z] Created: `frontend/src/app/admin/page.tsx`
- [2026-04-12T17:21:24.014Z] Created: `frontend/src/app/login/page.tsx`
- [2026-04-12T17:25:57.465Z] Created: `frontend/src/components/FacilityCard.tsx`
- [2026-04-12T17:25:59.242Z] Created: `frontend/src/components/DraftEditor.tsx`
- [2026-04-12T17:26:00.600Z] Created: `frontend/src/app/outreach/page.tsx`
- [2026-04-12T17:26:02.224Z] Created: `frontend/src/app/intake/import/page.tsx`
- [2026-04-12T19:10:34.499Z] Created: `frontend/src/app/analytics/AnalyticsDashboard.tsx`
- [2026-04-12T19:10:34.740Z] Created: `frontend/src/app/cases/[case_id]/page.tsx`
- [2026-04-12T19:10:34.975Z] Created: `frontend/src/app/facilities/[facility_id]/page.tsx`
- [2026-04-12T19:10:35.243Z] Created: `frontend/src/app/admin/page.tsx`
- [2026-04-12T19:10:41.322Z] Created: `frontend/src/app/admin/page.tsx`
- [2026-04-12T19:10:45.205Z] Created: `frontend/src/app/admin/page.tsx`
- [2026-04-12T19:10:49.207Z] Created: `frontend/src/components/CaseTable.tsx`
- [2026-04-12T20:47:23.150Z] Created: `frontend/src/client/index.ts`
- [2026-04-12T20:47:30.290Z] Created: `frontend/src/client/index.ts`
- [2026-04-12T20:47:39.492Z] Created: `frontend/src/app/cases/[case_id]/page.tsx`
- [2026-04-12T20:47:44.387Z] Created: `frontend/src/app/cases/[case_id]/page.tsx`
- [2026-04-12T20:47:49.382Z] Created: `frontend/src/app/cases/[case_id]/page.tsx`
- [2026-04-12T20:47:57.056Z] Created: `frontend/src/app/cases/[case_id]/page.tsx`
- [2026-04-12T20:48:03.250Z] Created: `frontend/src/app/cases/[case_id]/page.tsx`
- [2026-04-12T20:48:08.883Z] Created: `frontend/src/app/cases/[case_id]/page.tsx`
- [2026-04-12T20:48:15.041Z] Created: `frontend/src/app/cases/[case_id]/page.tsx`
- [2026-04-12T20:48:20.308Z] Created: `frontend/src/app/cases/[case_id]/page.tsx`
- [2026-04-12T20:48:24.662Z] Created: `frontend/src/app/cases/[case_id]/page.tsx`
- [2026-04-12T20:48:31.657Z] Created: `frontend/src/app/outreach/page.tsx`
- [2026-04-12T20:48:36.445Z] Created: `frontend/src/app/dashboard/DashboardKPIs.tsx`
- [2026-04-12T20:48:47.668Z] Created: `frontend/src/app/dashboard/DashboardKPIs.tsx`
- [2026-04-12T20:49:08.268Z] Created: `frontend/src/components/CaseTable.tsx`
- [2026-04-12T20:49:13.947Z] Created: `frontend/src/app/intake/page.tsx`
- [2026-04-12T20:49:19.004Z] Created: `frontend/src/app/intake/page.tsx`
- [2026-04-12T20:49:29.489Z] Created: `frontend/src/app/intake/page.tsx`
- [2026-04-12T20:49:36.044Z] Created: `frontend/src/app/intake/page.tsx`
- [2026-04-12T20:49:40.725Z] Created: `frontend/src/app/intake/page.tsx`
- [2026-04-12T20:49:48.366Z] Created: `frontend/src/app/intake/page.tsx`
- [2026-04-12T20:49:53.646Z] Created: `frontend/src/app/intake/page.tsx`
- [2026-04-12T20:50:03.086Z] Created: `frontend/src/components/FacilityCard.tsx`
- [2026-04-12T20:50:14.131Z] Created: `frontend/src/components/FacilityCard.tsx`
- [2026-04-12T20:50:26.330Z] Created: `frontend/src/app/intake/import/page.tsx`
- [2026-04-12T20:50:29.933Z] Created: `frontend/src/app/intake/import/page.tsx`
- [2026-04-12T20:50:36.516Z] Created: `frontend/src/components/DraftEditor.tsx`
- [2026-04-12T20:50:42.714Z] Created: `frontend/src/app/admin/page.tsx`
- [2026-04-12T20:50:46.369Z] Created: `frontend/src/app/admin/page.tsx`
- [2026-04-12T20:50:51.190Z] Created: `frontend/src/app/admin/page.tsx`
- [2026-04-12T20:50:57.322Z] Created: `frontend/src/components/ClinicalAssessmentForm.tsx`
- [2026-04-12T20:51:01.744Z] Created: `frontend/src/components/ClinicalAssessmentForm.tsx`
- [2026-04-12T20:51:08.164Z] Created: `frontend/src/components/ClinicalAssessmentForm.tsx`
- [2026-04-12T20:51:23.783Z] Created: `frontend/src/components/__tests__/CaseTable.test.tsx`
- [2026-04-12T20:51:28.499Z] Created: `frontend/src/lib/utils.ts`
- [2026-04-12T20:51:33.913Z] Created: `frontend/src/lib/utils.ts`
- [2026-04-12T20:51:40.191Z] Created: `frontend/src/app/layout.tsx`
- [2026-04-12T20:51:45.782Z] Created: `frontend/src/app/page.tsx`
- [2026-04-12T20:51:54.109Z] Created: `frontend/src/app/outreach/page.tsx`
- [2026-04-12T20:52:05.034Z] Created: `frontend/src/app/queue/page.tsx`
- [2026-04-12T20:52:24.731Z] Created: `frontend/src/app/layout.tsx`
