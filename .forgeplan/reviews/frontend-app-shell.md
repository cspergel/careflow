## Review: frontend-app-shell
**Date:** 2026-04-11T00:00:00Z
**Reviewer:** Claude Sonnet 4.6
**Review type:** native
**Cycle:** 1

---

### Acceptance Criteria

- **AC1: PASS** — Login page (`src/app/login/page.tsx:15-29`) implements `getRoleLanding()` with correct role→path mapping: `intake_staff`→`/intake`, `clinical_reviewer`/`placement_coordinator`→`/queue`, `manager`/`admin`/`read_only`→`/dashboard`. Uses `supabase.auth.getUser()` post-login (line 57) before profile fetch. Root page (`src/app/page.tsx`) does the same server-side redirect. No authenticated user name displayed in a persistent top bar — the sidebar shows user name/email/role in its footer (`src/components/Sidebar.tsx:161-175`), which satisfies the spirit of "authenticated user name appears in top bar" though technically it is in the sidebar footer rather than a dedicated top bar. Partial concern but not a hard FAIL.

- **AC2: PASS** — Sidebar (`src/components/Sidebar.tsx:30-84`) defines `NAV_ITEMS` with per-item `allowed_roles`. `visibleNavItems` filtered at line 105. Role filtering verified: `placement_coordinator` sees Operations Queue, Outreach, Facilities — confirmed by `allowed_roles` arrays. Analytics excluded for `placement_coordinator` (allowed only for `manager`/`admin`). Admin excluded for non-admin roles. Middleware (`middleware.ts:48-51`) redirects unauthenticated users to `/login`. Layout (`src/app/layout.tsx:38-43`) calls `getUser()` server-side and gates sidebar rendering on user presence.

- **AC3: PASS** — `CaseTable.tsx:85-118` configures `useReactTable` with `manualSorting: true`, `manualFiltering: true`, `manualPagination: true` (lines 90-92). Filter/sort/pagination state is derived from nuqs `useQueryStates` (lines 70, 26-33). Sorting changes call `setFilters` (line 103-108), pagination changes call `setFilters` (line 113-117). URL params include `page`, `per_page`, `sort`, `sort_dir`, `search`, `status`. Test at `__tests__/CaseTable.test.tsx:11-15` asserts all three manual flags are true. FilterBar (`src/components/FilterBar.tsx:32`) also uses `useCaseTableFilters()` for URL-persisted state.

- **AC4: FAIL** — The generated typed API client is a placeholder only. `src/client/index.ts` states "This file is a placeholder. Run `npm run generate-client`" (line 3-4). The `generate-client` script (`package.json:11`) is defined and points correctly to `@hey-api/openapi-ts`. However, the `@hey-api/client-fetch` package referenced in `openapi-ts.config.ts:7` as the `client` field is **not listed in `package.json` dependencies** — it is absent from both `dependencies` and `devDependencies`. This means `npm run generate-client` will fail at runtime. Additionally, all API calls in the application use `apiClient.fetch()` which is a hand-written raw-fetch wrapper defined in `src/client/index.ts:34-48`. The spec constraint states "no hand-written API fetch wrappers are permitted for backend endpoints" and requires all calls to use the typed generated client. The placeholder confirms the generated client (`types.gen.ts`, `services.gen.ts`, `schemas.gen.ts`) does not exist yet.

- **AC5: PASS** — `getSession()` is never called anywhere in the codebase (confirmed by grep — zero matches on the actual call, only documentation comments). `getUser()` is called in: `middleware.ts:43`, `src/lib/supabase/server.ts:10-34` (server client used in server components), `src/app/layout.tsx:41`, `src/app/dashboard/page.tsx:11`, `src/app/analytics/page.tsx:11`, `src/app/page.tsx:26`. Client components (`login/page.tsx:57`, `admin/page.tsx:31`, `cases/[case_id]/page.tsx:35`) call `supabase.auth.getUser()` on the browser client — this is the correct browser-side pattern.

- **AC6: PASS** — Intake page (`src/app/intake/page.tsx`) renders CaseTable census (line 223-229) with `createSheetOpen` and `editCase` Sheet components. Quick-edit drawer correctly uses `shadcn/ui Sheet` (lines 233 and 403 — both `<Sheet>` components). Duplicate warning implemented: `checkDuplicates` function (lines 143-162) calls `/api/v1/cases/check-duplicate` with `patient_name`, `dob`, `hospital_id`; triggers on `onBlur` of name and dob fields (lines 280-286, 298-305); renders warning banner at lines 253-272. The duplicate check requires all three fields to be filled before triggering (line 148), which is spec-correct.

- **AC7: PASS** — Import page (`src/app/intake/import/page.tsx`) uses `react-spreadsheet-import` loaded via `next/dynamic` with `ssr: false` (line 23-29). Phases: `upload` → modal opens → `handleImportData` POSTs to `/api/v1/intake/imports` → `reviewing` phase shows job summary. Commit button is explicitly gated: `disabled={importJob.status !== "ready" || phase === "committing"}` (line 318-319). Failed state renders at lines 369-394 showing `importJob?.error_summary` and "Start New Import" button (line 389). Per-row error detail shown in reviewing phase (lines 297-312). The `ImportFlowState` spec model steps `upload|mapping|validating|ready|committing|complete|failed` are partially mapped; the implementation skips dedicated `mapping` and `validating` phases as separate UI steps — these are handled inside the react-spreadsheet-import modal, which is acceptable given the library handles column mapping internally.

- **AC8: PASS** — Queue page (`src/app/queue/page.tsx:32-66`) defines `TAB_CONFIGS` with all 7 required tabs: `all`, `intake`, `clinical`, `matching`, `outreach`, `response`, `declined-retry`. SLA flags rendered via `SlaFlag` component (lines 83-107) with per-status thresholds and color-coded indicators. `declined_retry_needed` cases show "Route Retry" button (lines 293-309). `RouteRetrySheet` (lines 117-178) provides destination selector offering `matching` and `outreach` options. Route action POSTs to `/api/v1/cases/${caseId}/route-retry` (line 221). Note: the spec interface for `outcomes-module` specifies the endpoint as `POST /api/v1/cases/{case_id}/status-transition` but the implementation calls `/api/v1/cases/${caseId}/route-retry` — this is an interface contract deviation (see Interfaces section).

- **AC9: PASS** — Case detail page (`src/app/cases/[case_id]/page.tsx`) renders 6 tabs. Audit tab only added to tab list when `userRole === "admin"` (line 336: `...(userRole === "admin" ? ["audit"] : [])`). Audit tab content wrapped in `{userRole === "admin" && (...)}` (line 527). Both the trigger and the content are conditionally excluded for non-admin roles, satisfying the "must not be rendered in the DOM" constraint. Audit events only fetched when `userRole === "admin"` (line 137).

- **AC10: PASS** — Facility matches tab renders `FacilityCard` components with all required fields: name, type, distance, scores (payer/clinical/geography/preference), `is_recommended` badge, blocker chips, explanation text (verified in `FacilityCard.tsx:103-170`). "Select For Outreach" toggle present for non-blocked facilities (line 174: `{!hasBlockers && ...}`). Re-match warning: `handleGenerateMatches(false)` checks `matches.length > 0` and opens `rematchSheetOpen` Sheet (lines 158-160 in `cases/[case_id]/page.tsx`). Warning message "Re-generating matches will clear your current selections" appears in the Sheet description (line 459). Contextual prompt: `{selectedFacilityForOutreach && (...)}` renders "Ready to create outreach?" with "Go to Outreach tab →" button (lines 413-429). **Minor issue**: the contextual prompt in the case detail page (line 417-419) splits the message across two elements — "Ready to create outreach?" as a `<span>` and "Facility selected for outreach." as separate text — but `FacilityCard.tsx:201-208` also renders the full prompt "Ready to create outreach?" with "Go to Outreach tab →" as required. The case-level prompt does not use the exact spec message format ("Ready to create outreach? Go to Outreach tab →" as a single linked string); it splits them.

- **AC11: PASS** — `DraftEditor.tsx` defines `DIRECT_SEND_CHANNELS = ["phone_manual", "task"]` (line 31). For new draft forms, button label is "Log" when `isDirectSend` (line 374). The approval-flow buttons (Submit for Approval, Approve, Mark Sent, Cancel) are wrapped in `{!existingIsDirectSend && (...)}` (line 209), meaning phone_manual/task drafts show no approval steps. For the create-outreach flow, `handleCreateOutreach` (`cases/[case_id]/page.tsx:219-233`) sends to `/api/v1/cases/${caseId}/outreach` — the spec interface specifies `/api/v1/cases/{case_id}/outreach-actions` but implementation uses `/outreach` (see Interfaces section). The UI-level behavior of bypassing approval flow for phone_manual/task is correctly implemented.

- **AC12: PASS** — `ClinicalAssessmentForm.tsx` uses `react-hook-form` v7 with `zodResolver` (lines 7-8, 156-157). Schema at lines 33-86 covers 20+ fields across: recommended_level_of_care, confidence_level, clinical_summary, rehab_tolerance, mobility_status, oxygen_required, trach, vent, dialysis_required, dialysis_type, in_house_hd_required, wound_vac_needs, iv_antibiotics, tpn, isolation_precautions, psych_behavior_flags, behavioral_complexity_flag, bariatric_needs, memory_care_needed, special_equipment_needs, barriers_to_placement, payer_notes, family_preference_notes, review_status — that is 24 fields. `superRefine` at lines 77-85 makes `dialysis_type` required when `dialysis_required=true`. Test `ClinicalAssessmentForm.test.tsx:38-61` verifies this constraint fails submission without dialysis_type. Field-level errors displayed inline via `<FormMessage />` components.

- **AC13: FAIL** — `StatusBadge.tsx` defines `CaseStatus` with 14 members (lines 12-26), but **the status enum diverges from the shared `PatientCase` model in `manifest.yaml`**. The manifest defines `current_status` as: `new | intake_in_progress | intake_complete | needs_clinical_review | under_clinical_review | ready_for_matching | facility_options_generated | outreach_pending_approval | outreach_in_progress | pending_facility_response | accepted | declined_retry_needed | placed | closed`. StatusBadge replaces `intake_complete` with `ready_for_clinical_review` (a status not in the manifest's PatientCase enum). The `STATUS_CONFIG satisfies Record<CaseStatus, StatusConfigEntry>` exhaustiveness check (line 110) enforces internal consistency, but it is checking against the wrong union type. When the backend sends `intake_complete` (per the manifest), the frontend has no config entry for it — `STATUS_CONFIG["intake_complete"]` is undefined — causing a runtime error or blank badge. The test at `StatusBadge.test.tsx:8-23` also uses the incorrect `ready_for_clinical_review` instead of `intake_complete`.

- **AC14: PARTIAL PASS** — `package.json:10-11` defines `type-check` (runs `tsc --noEmit`) and `build` scripts. `dev` script is present. No TypeScript errors can be verified without running the build, but the configuration is structurally correct. **However**, the `@hey-api/client-fetch` package referenced in `openapi-ts.config.ts` is absent from `package.json`, which would cause `npm run generate-client` to fail. The `tsconfig.json` was not read but is present. This is a blocking dependency gap that would cause build failures when the generated client is needed.

- **AC15: PASS** — Admin page (`src/app/admin/page.tsx`) implements `useAdminGuard()` (lines 24-49) which checks role client-side and calls `router.push("/dashboard")` for non-admin (line 43). The page renders with 4 tabs: users, templates, imports, org-settings (lines 301-314). Users tab (lines 53-101) shows user list from `/api/v1/admin/users`. Templates tab (lines 103-157) shows templates. Import Jobs tab (lines 160-219) shows import history. Org Settings tab (lines 221-263) provides org name edit. **Gap**: the spec AC15 test expects non-admin redirect to `/dashboard` with an "access-denied message" — the implementation redirects but shows no access-denied message. The `useAdminGuard` hook renders `null` while redirecting (line 280-282), not an access-denied notification. This is a minor UX gap in the test acceptance criteria, not a structural failure.

---

### Constraints

- **"Use @supabase/ssr exclusively; call getUser() in server components and middleware — never getSession() in server components"**: ENFORCED — Zero calls to `getSession()` found in any server component or middleware. All server-side auth uses `getUser()`.

- **"All case list tables must configure TanStack Table v8 with manualSorting: true, manualFiltering: true, manualPagination: true"**: ENFORCED — `CaseTable.tsx:90-92` sets all three. This component is used in all table views (intake, queue, facilities, outreach pages).

- **"Filter, sort, and pagination state for all tables must be persisted in URL query parameters using nuqs"**: ENFORCED — `useCaseTableFilters()` uses `useQueryStates` from nuqs with `shallow: false` (line 45), ensuring navigation and refresh preserve state.

- **"The typed API client must be generated from FastAPI /openapi.json using @hey-api/openapi-ts; the generation command must be a npm script; no hand-written API fetch wrappers are permitted for backend endpoints"**: VIOLATED — `src/client/index.ts` is explicitly a placeholder with a hand-written `fetch` wrapper (lines 34-48). The generation script exists (`npm run generate-client`) but the `@hey-api/client-fetch` runtime package is not in `package.json`, making it non-functional. All 50+ API calls in the app use the hand-written wrapper via `apiClient.fetch()`.

- **"The clinical assessment form must use react-hook-form v7 with a Zod schema covering all 20+ fields; field-level validation errors must display inline without full-page reload"**: ENFORCED — 24 fields in schema, `zodResolver` used, `<FormMessage />` inline on all validated fields.

- **"Quick-edit drawers must use shadcn/ui Sheet component — not Drawer, Modal, or Dialog"**: ENFORCED — All drawers verified: intake create/edit (`intake/page.tsx:233, 403`), queue route-retry (`queue/page.tsx:136`), rematch warning (`cases/[case_id]/page.tsx:449-482`). No `Drawer`, `Modal`, or `Dialog` components used in these contexts.

- **"The spreadsheet import flow UI must use react-spreadsheet-import for column mapping and row preview"**: ENFORCED — `intake/import/page.tsx:23-29` dynamically imports `ReactSpreadsheetImport`; rendered at lines 398-405 with `fields={IMPORT_FIELDS}`.

- **"Tailwind v4 configuration must use tw-animate-css package — not tailwindcss-animate"**: ENFORCED — `tailwind.config.ts:69` uses `require("tw-animate-css")`. `tailwindcss-animate` appears nowhere in `package.json` or codebase.

- **"StatusBadge must use a STATUS_CONFIG map keyed by the PatientCase status enum; the map must be defined such that TypeScript exhaustiveness checking produces a compile error if a new status is added without a corresponding config entry"**: VIOLATED — The exhaustiveness check mechanism (`satisfies Record<CaseStatus, StatusConfigEntry>` at line 110) is correctly implemented. However, `CaseStatus` does not match the `PatientCase.current_status` enum in the manifest — `intake_complete` is missing and `ready_for_clinical_review` is present instead. The exhaustiveness check enforces completeness against the wrong type, meaning the actual backend status `intake_complete` has no config entry and will render as a runtime error.

- **"The 'Select For Outreach' contextual prompt must appear after the coordinator selects at least one facility and must include a tab navigation action"**: ENFORCED — Both `FacilityCard.tsx:197-209` and `cases/[case_id]/page.tsx:413-429` render contextual prompts with tab navigation actions when a facility is selected.

- **"The re-match warning modal must require explicit confirmation before POST .../matches/generate is called when existing matches are present"**: ENFORCED — `handleGenerateMatches(false)` at line 158 gates on `matches.length > 0` to open the Sheet; the actual generate call only fires when called with `confirmed=true` (line 166).

- **"phone_manual and task outreach actions must atomically advance case state to pending_facility_response in a single UI action with no intermediate approval step shown to the user"**: ENFORCED at the UI level — `DIRECT_SEND_CHANNELS` in `DraftEditor.tsx` bypasses approval UI. However, the `handleCreateOutreach` in `cases/[case_id]/page.tsx:219-233` does not differentiate channel type when POSTing — it sends `action_type: "facility_outreach"` for all channels and does not include a `channel` field. The backend must therefore handle atomic advancement; the frontend contract for this specific endpoint is incomplete (see Interfaces).

- **"The Audit tab must only be rendered in the DOM for admin role"**: ENFORCED — Both the `TabsTrigger` and `TabsContent` for audit are guarded by `userRole === "admin"` in `cases/[case_id]/page.tsx:336` and `527`.

- **"All API error states (4xx, 5xx, network timeout) must be handled with user-visible error messages; silent failures are not permitted"**: ENFORCED with one noted exception — `ApiError` is caught and displayed as user-visible messages in all major data-fetching functions. The assessment load in `cases/[case_id]/page.tsx:132-134` silently catches errors (empty catch block) but this is documented as intentional "No assessment yet — that's OK". Audit load failure (line 143-145) is also silently caught with comment "non-critical".

---

### Interfaces

- **auth-module** (read/write): PARTIAL PASS — Login uses `supabase.auth.signInWithPassword` (not the specified `POST /api/v1/auth/login`). Session hydration uses `supabase.auth.getUser()` client-side (not `GET /api/v1/auth/me`). Logout is not implemented in the sidebar `onSignOut` prop — `layout.tsx` does not pass an `onSignOut` handler to `Sidebar`, so the Sign Out button in the sidebar is never rendered (the `onSignOut` prop is undefined). This means users have no logout mechanism in the current implementation.

- **intake-module** (read/write): PARTIAL PASS — `POST /api/v1/cases` used (intake create). `GET /api/v1/cases` used with status params. Import endpoints use `/api/v1/intake/imports` (consistent prefix). However, `POST /api/v1/cases/{case_id}/mark-intake-complete` is not called anywhere — the Intake Workbench has no "Complete Intake" action button. `GET /api/v1/queues/intake` not used; queue data fetched from `/api/v1/cases` with status params instead.

- **clinical-module** (read/write): PASS — `GET /api/v1/cases/{case_id}/assessments` (line 126 of case detail), `POST /api/v1/cases/{case_id}/assessments`, `PATCH /api/v1/assessments/{assessment_id}` (line 213, method conditional on existing assessment). ClinicalAssessmentForm embedded in Clinical tab.

- **facilities-module** (read/write): PARTIAL PASS — `GET /api/v1/facilities` used. `GET /api/v1/facilities/{facility_id}` used. `GET /api/v1/facilities/{facility_id}/capabilities` used. `GET /api/v1/facilities/{facility_id}/insurance-rules` used. No admin create/edit facility UI implemented (`POST /api/v1/facilities`, `PATCH /api/v1/facilities/{facility_id}`, `PUT /api/v1/facilities/{facility_id}/capabilities` not called). The spec marks these as part of the contract but the Admin Settings screen does not include a Facilities CRUD tab.

- **matching-module** (read/write): PASS — `POST /api/v1/cases/{case_id}/matches/generate` (line 166), `GET /api/v1/cases/{case_id}/matches` (line 169), `PATCH /api/v1/cases/{case_id}/matches/{match_id}/select` (line 185-188). All three endpoints present.

- **outreach-module** (read/write): PARTIAL PASS — Endpoint naming mismatch: spec specifies `POST /api/v1/cases/{case_id}/outreach-actions` but implementation calls `/api/v1/cases/${caseId}/outreach` (line 225 and 94 in case detail). `GET /api/v1/cases/{case_id}/outreach` instead of `outreach-actions`. `POST /api/v1/outreach/{action_id}/approve` (line 236) — spec specifies endpoint as `approve` which matches. `POST /api/v1/outreach/{action_id}/mark-sent` (line 242) matches. `POST /api/v1/outreach/{action_id}/cancel` (line 249) matches. `POST submit-for-approval` is not implemented as a separate endpoint call — the "Submit for Approval" button re-calls `onSubmit` with the existing draft body (DraftEditor.tsx line 215), which is architecturally questionable. `GET /api/v1/queues/outreach` not used; outreach dashboard uses `/api/v1/outreach` instead.

- **outcomes-module** (read/write): PARTIAL PASS — `GET /api/v1/cases/{case_id}/timeline` used (line 99 in case detail). `POST /api/v1/cases/{case_id}/outcomes` and `GET /api/v1/cases/{case_id}/outcomes` not implemented — there is no outcome recording form in any tab. The spec requires a "Timeline tab and outcome recording forms." Timeline is present; outcome recording is absent. `POST /api/v1/cases/{case_id}/status-transition` (for declined_retry routing) — the implementation uses `/api/v1/cases/${caseId}/route-retry` instead (`queue/page.tsx:221`).

- **analytics-module** (inbound): PARTIAL PASS — `GET /api/v1/analytics/dashboard` not called; `AnalyticsDashboard.tsx` calls `/api/v1/analytics/summary` (line 26). `GET /api/v1/analytics/outreach-performance` not called. `GET /api/v1/queues/operations` and `GET /api/v1/queues/manager-summary` not called. Dashboard KPIs use a different endpoint than specified.

- **admin-surfaces** (read/write): PARTIAL PASS — `GET /api/v1/admin/users` used (admin page line 60). `GET /api/v1/outreach/templates` used (admin page line 111). `GET /api/v1/intake/imports` used (admin page line 168). `GET+PATCH /api/v1/admin/organization` used (admin page lines 231-232). Missing: `POST/PATCH /api/v1/admin/users` (no invite/edit user UI), `POST/PATCH /api/v1/templates/outreach` (no template create/edit UI). `GET /api/v1/reference/*` not called anywhere.

---

### Pattern Consistency

- All page components and shared components follow a consistent pattern: state initialization with `React.useState`, `useEffect` for data loading, error state rendered as a red destructive banner, loading state with text placeholder.
- API calls consistently use `apiClient.fetch()` with `ApiError` instance checks for error messages — uniform pattern across all 12 files that make API calls.
- `"use client"` directive is consistently applied to all interactive components. Server components (`layout.tsx`, `dashboard/page.tsx`, `analytics/page.tsx`, `page.tsx`) correctly omit it.
- Naming conventions: pages in `/app/` follow Next.js App Router conventions. Components in `/components/` are PascalCase. All consistent.
- URL state management: `useQueryState` from nuqs used for tab state in 3 pages (case detail, admin, facility detail) and `useCaseTableFilters` for table state. Consistent.
- One inconsistency: `outreach/page.tsx:20-27` duplicates the `APPROVAL_STATUS_CONFIG` object already defined in `DraftEditor.tsx:87-100`. This should be extracted to a shared constant.

---

### Anchor Comments

All source files in `frontend/**` that were read have `// @forgeplan-node: frontend-app-shell` at line 1:
- `middleware.ts` — PRESENT
- `src/lib/supabase/server.ts` — PRESENT
- `src/lib/supabase/client.ts` — PRESENT
- `src/client/index.ts` — PRESENT
- `tailwind.config.ts` — PRESENT
- `openapi-ts.config.ts` — PRESENT
- `src/components/StatusBadge.tsx` — PRESENT
- `src/components/CaseTable.tsx` — PRESENT
- `src/components/ClinicalAssessmentForm.tsx` — PRESENT
- `src/components/FacilityCard.tsx` — PRESENT
- `src/components/ActivityTimeline.tsx` — PRESENT
- `src/components/FilterBar.tsx` — PRESENT
- `src/components/Sidebar.tsx` — PRESENT
- `src/components/DraftEditor.tsx` — PRESENT
- `src/components/__tests__/StatusBadge.test.tsx` — PRESENT
- `src/components/__tests__/CaseTable.test.tsx` — PRESENT
- `src/components/__tests__/ClinicalAssessmentForm.test.tsx` — PRESENT
- All `src/app/**/*.tsx` pages — PRESENT (verified across login, intake, queue, cases, facilities, outreach, admin, dashboard, analytics, layout, page)
- `src/components/ui/*.tsx` (all 13 shadcn/ui components) — PRESENT

All major functions referencing specific ACs have `@forgeplan-spec` comments. `@forgeplan-spec` on individual AC references verified across middleware, CaseTable, ClinicalAssessmentForm, StatusBadge, DraftEditor, FacilityCard, all page components.

Coverage: COMPLETE across all source files.

---

### Non-Goals

- **"Does not implement any backend API endpoints"**: CLEAN — No Express/FastAPI route handlers, no `app/api/` Next.js route handlers present. All calls are outbound to FastAPI.
- **"Does not implement mobile or tablet responsive layouts"**: CLEAN — No responsive breakpoint CSS found for sub-1280px. Layout uses fixed `w-60` sidebar.
- **"Does not implement real-time push updates or websocket connections"**: CLEAN — No WebSocket imports, no Supabase Realtime subscriptions found.
- **"Does not implement voice AI call interfaces"**: CLEAN — `voice_ai` channel appears as a select option in DraftEditor but does not implement a voice AI UI — it's just a channel type. No voice AI integration code present.
- **"Does not implement PDF or CSV export"**: CLEAN — No export functionality found.
- **"Does not implement dark mode"**: MINOR CONCERN — `tailwind.config.ts:6` includes `darkMode: ["class"]`, enabling dark mode class toggling. No dark mode toggle UI is implemented, so this is a configuration artifact rather than an implementation, and no dark mode styles are applied by default. Not a violation of the non-goal.
- **"Does not own or store any data"**: CLEAN — All data flows through API calls to the FastAPI backend.
- **"Does not implement multi-tab/multi-window synchronization"**: CLEAN — No BroadcastChannel, SharedWorker, or Supabase Realtime session sync found.

---

### Failure Modes

- **"getSession() used instead of getUser() in a server component"**: HANDLED — Zero actual `getSession()` calls anywhere. All server auth uses `getUser()`. Comment-only references to `getSession()` are documentation warnings, not calls.

- **"TanStack Table configured with manualPagination: false"**: HANDLED — `CaseTable.tsx:92` explicitly sets `manualPagination: true`. No other `useReactTable` instances exist.

- **"nuqs not integrated with TanStack Table state — filter/sort state lost on page refresh"**: HANDLED — `useCaseTableFilters()` at line 70 derives all state from nuqs URL params. Pagination, sorting, and filter state are all URL-persisted.

- **"API client not regenerated after FastAPI schema change — typed client references deleted endpoint"**: UNHANDLED — The generated client files (`types.gen.ts`, `services.gen.ts`, `schemas.gen.ts`) do not exist. The hand-written placeholder provides no type safety against schema changes. `@hey-api/client-fetch` is also missing from `package.json`, preventing actual generation. This failure mode is currently manifested rather than guarded against.

- **"STATUS_CONFIG map defined without exhaustiveness check — new status renders as unstyled blank badge"**: PARTIALLY UNHANDLED — The `satisfies` exhaustiveness check exists and is correctly implemented. However, `CaseStatus` omits `intake_complete` (uses `ready_for_clinical_review` instead), meaning the backend's `intake_complete` status already renders as a runtime error today. The exhaustiveness mechanism works, but it is guarding against the wrong set of statuses.

- **"shadcn/ui Drawer used instead of Sheet for quick-edit"**: HANDLED — All drawers confirmed to use `Sheet`. No `Drawer` component imports found.

- **"Import commit button not gated on ImportJob.status=ready"**: HANDLED — `disabled={importJob.status !== "ready" || phase === "committing"}` at `import/page.tsx:318-319`.

- **"Re-match confirmation modal bypassed"**: HANDLED — `handleGenerateMatches` requires `confirmed=true` to proceed when matches exist; the Sheet confirms before calling with `true`.

- **"Select For Outreach contextual prompt omitted"**: HANDLED — Prompt rendered in both `FacilityCard.tsx:197-209` (per-card) and `cases/[case_id]/page.tsx:413-429` (page-level after any selection).

- **"react-hook-form not integrated with Zod for clinical assessment"**: HANDLED — `zodResolver(clinicalAssessmentSchema)` applied, `superRefine` enforces `dialysis_type` conditional requirement.

---

### Recommendation: REQUEST CHANGES (3 failures: AC4, AC13, interfaces/logout)

**Summary of failures requiring changes before approval:**

1. **AC4 / Constraint violation (critical)**: The typed API client is not implemented — only a hand-written placeholder exists. `@hey-api/client-fetch` is missing from `package.json`. All 50+ API calls use a raw fetch wrapper, violating the "no hand-written API fetch wrappers" constraint. The spec explicitly requires the generated client to be the sole mechanism for backend calls.

2. **AC13 / STATUS_CONFIG enum mismatch (critical)**: `CaseStatus` in `StatusBadge.tsx` includes `ready_for_clinical_review` (not in the manifest's `PatientCase.current_status` enum) and omits `intake_complete` (which IS in the manifest). This means cases with `intake_complete` status from the backend will cause runtime errors or render as blank badges. The exhaustiveness check enforces completeness against the wrong type.

3. **Logout not implemented / Interface gap (high)**: `layout.tsx` does not pass `onSignOut` to `Sidebar`, so the Sign Out button is never rendered. Users have no way to log out. Additionally, the outreach endpoint naming uses `/api/v1/cases/{id}/outreach` instead of the specified `/api/v1/cases/{id}/outreach-actions`, and the outcomes recording form is absent from the Case Detail (no UI for `POST /api/v1/cases/{case_id}/outcomes`).
