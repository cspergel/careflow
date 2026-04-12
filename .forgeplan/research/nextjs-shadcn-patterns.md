# Research: Next.js + shadcn/ui Patterns for Dense Healthcare Operational UI

**Date:** 2026-04-10
**Stack:** Next.js 14+ (App Router), shadcn/ui, Tailwind CSS, Supabase, FastAPI
**Use case:** Dense desktop-first operational UI for healthcare coordinators

---

## 1. Dense Data Tables — TanStack Table + shadcn/ui DataTable

### Verdict: TanStack Table v8 + shadcn/ui DataTable is the canonical choice. No serious alternative exists.

**Why it fits this project:**
- 10.4M downloads/week — this is the React table ecosystem
- shadcn/ui's official DataTable recipe is built directly on TanStack Table v8
- Powers data-heavy apps at Linear, Vercel, and similar operational tools
- v9 alpha exists but v8 (8.21.3) is stable and what all shadcn docs target

**Install:**
```bash
npm install @tanstack/react-table
```

### The Three-Layer Architecture for Operations Queue + Intake Workbench

For dense server-driven tables with 14 case states, the right pattern is:

```
Server Component (page.tsx)
  └── prefetch data with React Query's HydrationBoundary
      └── Client Component (DataTable)
            └── TanStack Table + nuqs for URL state
                └── FastAPI for server-side sort/filter/paginate
```

**Column definitions with status badge cell renderers:**
```typescript
// columns.tsx
import { ColumnDef } from "@tanstack/react-table"
import { Badge } from "@/components/ui/badge"
import { CaseStatusBadge } from "@/components/case-status-badge"

export const columns: ColumnDef<PlacementCase>[] = [
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ row }) => (
      <CaseStatusBadge status={row.getValue("status")} />
    ),
    filterFn: (row, id, value) => value.includes(row.getValue(id)),
  },
  {
    accessorKey: "patient_name",
    header: ({ column }) => (
      <DataTableColumnHeader column={column} title="Patient" />
    ),
  },
  // ...
]
```

### Row Density for Dense Operational View

shadcn's DataTable uses default Tailwind table cell padding (`px-4 py-2`). For dense operational density matching Linear/EMR style, override in your `data-table.tsx`:
```typescript
// Force compact rows — override shadcn default
<TableCell className="px-3 py-1.5 text-sm">
```
Or add a density toggle using a `size` prop that switches between `"default"` (`py-2`) and `"compact"` (`py-1`).

### Server-Side Sort / Filter / Paginate with nuqs

**nuqs** is the right choice for persisting table state in the URL (bookmarkable filter configurations, sharable deep links to filtered queue views).

nuqs provides first-class TanStack Table parsers:
```bash
npm install nuqs  # v2.8.9, MIT, 2.2M downloads/week
```

```typescript
// hooks/use-case-table-filters.ts
import { parseAsInteger, parseAsString, parseAsArrayOf, useQueryStates } from "nuqs"

const caseTableParsers = {
  status: parseAsArrayOf(parseAsString).withDefault([]),
  page: parseAsInteger.withDefault(1),
  per_page: parseAsInteger.withDefault(50),
  sort: parseAsString.withDefault("created_at"),
  sort_dir: parseAsString.withDefault("desc"),
  search: parseAsString.withDefault(""),
}

export function useCaseTableFilters() {
  return useQueryStates(caseTableParsers, { shallow: false }) // shallow: false notifies RSC
}
```

`shallow: false` is critical: it tells nuqs to notify Next.js server components to re-render when filters change, which triggers a fresh fetch to FastAPI with the updated query params.

### Virtualization for Large Queues

For 500+ cases, pair with:
```bash
npm install @tanstack/react-virtual  # v3.13.23, MIT, active
```
Use `useVirtualizer` with `estimateSize: () => 36` (36px compact row height). The TanStack docs include a `virtualized-rows` example that composites cleanly with TanStack Table.

### Reference: openstatusHQ/data-table-filters

**URL:** https://github.com/openstatusHQ/data-table-filters
**Stars:** Actively maintained, backed by openstatus.dev production use

This is the most sophisticated open-source shadcn + TanStack Table reference available. Key patterns to learn:

- **Pluggable state adapters:** Same filter API works with nuqs (URL), Zustand (client), or memory — swap without rewriting table logic
- **Faceted filters:** Checkbox, input, slider, and time range filter types all implemented
- **Column pinning** for frozen ID/status columns
- **Bulk row actions** via row selection + action toolbar
- **Infinite scroll** via `useInfiniteQuery` as alternative to pagination

**File structure lesson:**
```
features/cases/
  components/
    cases-table.tsx         — DataTable wrapper, owns table instance
    cases-table-columns.tsx — ColumnDef array
    cases-table-toolbar.tsx — Filter controls, search, column visibility
    cases-table-pagination.tsx
  hooks/
    use-case-filters.ts     — nuqs state
    use-cases-query.ts      — TanStack Query fetch
```

### Reference: Kiranism/next-shadcn-dashboard-starter

**URL:** https://github.com/Kiranism/next-shadcn-dashboard-starter
**Stack:** Next.js 16 (App Router), shadcn/ui + Tailwind v4, TanStack Query, nuqs, Zustand, kbar

Key patterns:
- `HydrationBoundary + useSuspenseQuery` for server-prefetch + client cache hydration
- Feature-folder structure: `features/[domain]/components/`, `features/[domain]/hooks/`
- nuqs for shallow URL state on table filters
- kbar for command palette (Cmd+K)

**What to avoid:** Uses Clerk for auth (not Supabase), so auth patterns won't translate directly.

---

## 2. Supabase Auth in Next.js App Router

### Verdict: Use @supabase/ssr with the server client / browser client split. Always getUser(), never getSession() in server code.

**Packages:**
```bash
npm install @supabase/supabase-js @supabase/ssr
# @supabase/ssr: 2.29M downloads/week, MIT, actively maintained
```

### The Critical Security Split

| Context | Client to use | Why |
|---|---|---|
| Server Components, Route Handlers, Server Actions | `createServerClient()` from `@supabase/ssr` | Reads cookies from request; validates JWT with Supabase auth server |
| Client Components (browser) | `createBrowserClient()` from `@supabase/ssr` | Session stored in cookies, not localStorage |
| middleware.ts | `createServerClient()` | ONLY for token refresh; never for access control decisions |

### Canonical File Structure

```
lib/supabase/
  client.ts    — createBrowserClient() — for use in Client Components
  server.ts    — createServerClient() — for Server Components, Server Actions, Route Handlers
middleware.ts  — token refresh proxy ONLY, not auth gating
```

**server.ts pattern:**
```typescript
import { createServerClient } from "@supabase/ssr"
import { cookies } from "next/headers"

export async function createClient() {
  const cookieStore = await cookies()
  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() { return cookieStore.getAll() },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value, options }) =>
            cookieStore.set(name, value, options)
          )
        },
      },
    }
  )
}
```

### The getUser() Rule — Non-Negotiable

```typescript
// CORRECT — validates JWT cryptographically against Supabase auth server
const { data: { user } } = await supabase.auth.getUser()

// WRONG — reads session from cookie, can be spoofed, do NOT use for access control
const { data: { session } } = await supabase.auth.getSession()
```

This is not just a best practice — CVE-2025-29927 demonstrated that middleware-only auth can be bypassed. Verify user identity at every data access point in your Data Access Layer.

### Middleware Role: Token Refresh Only

```typescript
// middleware.ts
export async function middleware(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request })
  const supabase = createServerClient(/* ... cookie handlers using request/response ... */)

  // ONLY purpose: refresh token and write updated cookie
  await supabase.auth.getUser()

  return supabaseResponse
  // Do NOT gate routes here — do that in Server Components or Route Handlers
}
```

### Protected Route Pattern (Server Component)

```typescript
// app/dashboard/page.tsx — Server Component
import { createClient } from "@/lib/supabase/server"
import { redirect } from "next/navigation"

export default async function DashboardPage() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()

  if (!user) redirect("/login")

  // fetch data — user is now verified
}
```

### Client Component Auth State

```typescript
// For Client Components that need to react to auth changes:
"use client"
import { createClient } from "@/lib/supabase/client"

export function useCurrentUser() {
  const supabase = createClient()
  const [user, setUser] = useState(null)

  useEffect(() => {
    supabase.auth.getUser().then(({ data }) => setUser(data.user))
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_, session) => setUser(session?.user ?? null)
    )
    return () => subscription.unsubscribe()
  }, [])

  return user
}
```

---

## 3. Typed API Client: Next.js → FastAPI

### Verdict: @hey-api/openapi-ts for code generation + openapi-fetch as runtime client + @tanstack/react-query for UI data layer.

### Tool Comparison

| Tool | Downloads/wk | License | Approach | Best For |
|---|---|---|---|---|
| **@hey-api/openapi-ts** | 2.03M | MIT | Generates SDK (types + services + Zod schemas) | Full SDK with TanStack Query hooks |
| **orval** | 1.09M | MIT | Generates axios or fetch client + react-query hooks | Projects already using Axios |
| **openapi-react-query** | moderate | MIT | Thin wrapper, 1kb runtime | Minimal API surface |

**Recommendation for this project:** `@hey-api/openapi-ts` because it generates TanStack Query hooks natively (you're already using TanStack Query for table data), produces Zod schemas for form validation, and is the approach used by Vercel and PayPal.

### Install

```bash
npm install @hey-api/openapi-ts @hey-api/client-fetch --save-dev
npm install @tanstack/react-query
```

### Generated File Structure

Running `openapi-ts` against FastAPI's `/openapi.json` generates:

```
src/lib/api/
  schemas.gen.ts   — Zod/JSON Schema shapes for all request/response models
  types.gen.ts     — TypeScript types for all API models
  services.gen.ts  — Typed functions for each endpoint
```

### Dev Workflow (Auto-sync with FastAPI)

```json
// package.json scripts
{
  "scripts": {
    "generate-client": "openapi-ts --input http://localhost:8000/openapi.json --output src/lib/api",
    "dev": "concurrently \"next dev\" \"npm run watch-schema\"",
    "watch-schema": "chokidar 'openapi.json' -c 'npm run generate-client'"
  }
}
```

### Usage Pattern with TanStack Query

```typescript
// hooks/use-cases.ts
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { CasesService } from "@/lib/api/services.gen"

export function useCases(filters: CaseFilters) {
  return useQuery({
    queryKey: ["cases", filters],
    queryFn: () => CasesService.listCases({ ...filters }),
    staleTime: 30_000, // 30s for operational data
  })
}

export function useUpdateCaseStatus() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ caseId, status }: UpdateStatusPayload) =>
      CasesService.updateCaseStatus({ caseId, requestBody: { status } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["cases"] }),
  })
}
```

### Server Component Prefetch Pattern

```typescript
// app/dashboard/cases/page.tsx — Server Component
import { HydrationBoundary, dehydrate, QueryClient } from "@tanstack/react-query"
import { CasesService } from "@/lib/api/services.gen"

export default async function CasesPage({ searchParams }) {
  const queryClient = new QueryClient()
  await queryClient.prefetchQuery({
    queryKey: ["cases", searchParams],
    queryFn: () => CasesService.listCases(searchParams),
  })
  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <CasesTable /> {/* Client Component, uses useSuspenseQuery */}
    </HydrationBoundary>
  )
}
```

---

## 4. shadcn/ui Patterns: Multi-Tab Layout + Drawers + Status Badges

### 4a. Multi-Tab Case Detail Layout (6 tabs)

**Component:** shadcn/ui `Tabs` (built on Radix UI Tabs)

Radix handles all ARIA roles, keyboard navigation (arrow keys, Home, End), and focus management automatically. For a 6-tab case detail, use:

```typescript
// components/case-detail/case-detail-tabs.tsx
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

export function CaseDetailTabs({ caseId }: { caseId: string }) {
  return (
    <Tabs defaultValue="overview" className="w-full">
      <TabsList className="border-b rounded-none w-full justify-start h-auto p-0 bg-transparent">
        {/* Strip style — common in operational UIs */}
        <TabsTrigger value="overview" className="rounded-none border-b-2 border-transparent data-[state=active]:border-primary">
          Overview
        </TabsTrigger>
        <TabsTrigger value="clinical">Clinical Review</TabsTrigger>
        <TabsTrigger value="matches">Facility Matches</TabsTrigger>
        <TabsTrigger value="outreach">Outreach</TabsTrigger>
        <TabsTrigger value="timeline">Timeline</TabsTrigger>
        <TabsTrigger value="audit">Audit</TabsTrigger>
      </TabsList>
      <TabsContent value="overview"><OverviewTab caseId={caseId} /></TabsContent>
      {/* ... */}
    </Tabs>
  )
}
```

**Tab content mounting:** By default, Radix Tabs mounts all tab content but only shows the active one. This preserves form state when switching tabs — critical for the Clinical Review form.

**URL-synced tabs:** For deep-linkable tabs (e.g., `/cases/123?tab=outreach`), wire the `value` prop to a nuqs `parseAsString` param:
```typescript
const [tab, setTab] = useQueryState("tab", parseAsString.withDefault("overview"))
<Tabs value={tab} onValueChange={setTab}>
```

### 4b. Drawers for Quick Edits

shadcn/ui has two slide-out patterns:
- **Sheet** — slides from any edge, no drag handle, best for forms and detail panels on desktop
- **Drawer** — built on Vaul, has drag-to-close handle, better for mobile

**For desktop-first operational UI, use Sheet for all quick-edit drawers.**

```typescript
// components/case-quick-edit-sheet.tsx
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet"

export function CaseQuickEditSheet({ caseId, open, onOpenChange }) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-[480px] sm:w-[540px] overflow-y-auto">
        <SheetHeader>
          <SheetTitle>Edit Case</SheetTitle>
          <SheetDescription>Update case status and assignment</SheetDescription>
        </SheetHeader>
        <CaseEditForm caseId={caseId} onSuccess={() => onOpenChange(false)} />
      </SheetContent>
    </Sheet>
  )
}
```

Escape key closes automatically (Radix Dialog primitive). Focus is trapped inside. No custom keyboard handling needed.

**Sheet with tabs pattern** (official shadcn pattern exists at `/patterns/sheet-multi-section-2`): combine `Sheet` + `Tabs` for multi-section quick edit panels.

### 4c. Status Badge Components (14 Case States)

Build a single `CaseStatusBadge` component using shadcn's `Badge` with a status-to-variant map:

```typescript
// components/ui/case-status-badge.tsx
import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

const STATUS_CONFIG = {
  intake_pending:     { label: "Intake Pending",     className: "bg-slate-100 text-slate-700 border-slate-200" },
  clinical_review:    { label: "Clinical Review",    className: "bg-blue-100 text-blue-700 border-blue-200" },
  matching:           { label: "Matching",           className: "bg-indigo-100 text-indigo-700 border-indigo-200" },
  outreach_active:    { label: "Outreach Active",    className: "bg-amber-100 text-amber-700 border-amber-200" },
  placement_confirmed:{ label: "Confirmed",          className: "bg-green-100 text-green-700 border-green-200" },
  declined:           { label: "Declined",           className: "bg-red-100 text-red-700 border-red-200" },
  // ... 8 more states
} as const satisfies Record<CaseStatus, { label: string; className: string }>

export function CaseStatusBadge({ status }: { status: CaseStatus }) {
  const config = STATUS_CONFIG[status]
  return (
    <Badge variant="outline" className={cn("text-xs font-medium", config.className)}>
      {config.label}
    </Badge>
  )
}
```

Use `satisfies Record<CaseStatus, ...>` — TypeScript will error at compile time if you add a new status to the union type but forget to add its config.

---

## 5. Complex Forms — Clinical Assessment (20+ Fields)

### Verdict: React Hook Form + Zod. TanStack Form for new greenfield projects, but RHF wins on ecosystem maturity for clinical forms.

| | react-hook-form | @tanstack/react-form |
|---|---|---|
| Downloads/wk | 34.1M | 1.33M |
| Version | 7.72.1 | 1.29.0 |
| License | MIT | MIT |
| shadcn/ui support | Official `<Form>` wrapper built on RHF | Added official support Oct 2025 |
| Type safety | Good with Zod | Excellent — inferred from defaultValues |
| Bundle | ~13kb | ~20kb |
| Async validation | Via Zod + resolver | Built-in with debounce |
| Recommendation | **Use this for Phase 1** | Consider if adding more TanStack libs |

```bash
npm install react-hook-form zod @hookform/resolvers
```

**Pattern for 20+ field clinical assessment:**
```typescript
// Segment long forms into logical groups, not separate tabs
// Use shadcn Form + FormField + FormItem + FormLabel + FormMessage

const ClinicalAssessmentSchema = z.object({
  // Demographics group
  patient_dob: z.string().min(1),
  diagnosis_primary: z.string().min(1),
  // Clinical indicators group
  acuity_level: z.enum(["low", "medium", "high", "critical"]),
  mobility_status: z.enum(["ambulatory", "wheelchair", "bedbound"]),
  // Care needs group
  requires_iv: z.boolean(),
  requires_wound_care: z.boolean(),
  // ... etc
})

export function ClinicalAssessmentForm({ caseId }) {
  const form = useForm<z.infer<typeof ClinicalAssessmentSchema>>({
    resolver: zodResolver(ClinicalAssessmentSchema),
    defaultValues: { /* ... */ },
  })

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
        <FormSection title="Patient Demographics">
          <FormField control={form.control} name="diagnosis_primary" render={({ field }) => (
            <FormItem>
              <FormLabel>Primary Diagnosis</FormLabel>
              <FormControl><Input {...field} /></FormControl>
              <FormMessage />
            </FormItem>
          )} />
        </FormSection>
        {/* ... more sections */}
      </form>
    </Form>
  )
}
```

---

## 6. Spreadsheet Import Mapper

### Verdict: react-spreadsheet-import for the column-mapping UX. No need to build from scratch.

```bash
npm install react-spreadsheet-import  # v4.7.1, MIT, 14.6k downloads/wk
```

This library provides the complete import flow:
1. Drag-drop file upload (xlsx or CSV)
2. Auto-column matching with fuzzy matching
3. Per-row validation with error display
4. Confirmation step before submit

**Integration:**
```typescript
import { ReactSpreadsheetImport } from "react-spreadsheet-import"

const fields = [
  { label: "Patient Name",    key: "patient_name",    fieldType: { type: "input" }, validations: [{ rule: "required" }] },
  { label: "DOB",             key: "date_of_birth",   fieldType: { type: "input" }, example: "1980-01-15" },
  { label: "Insurance ID",    key: "insurance_id",    fieldType: { type: "input" } },
  { label: "Acuity Level",    key: "acuity_level",    fieldType: { type: "select", options: ["low", "medium", "high"] } },
  // ... more fields
]

<ReactSpreadsheetImport
  isOpen={importOpen}
  onClose={() => setImportOpen(false)}
  onSubmit={handleImportSubmit}
  fields={fields}
/>
```

**Note:** The library has its own styling (Chakra UI internally) which may conflict with shadcn/ui Tailwind setup. You will need to isolate it in a modal. The sadmann7/csv-importer template (shadcn registry) is a lighter alternative if you want full Tailwind control, but requires building the column-mapping UX yourself.

---

## 7. Command Palette (Cmd+K)

shadcn/ui's `Command` component is built on cmdk (21.1M downloads/week, MIT). It is already installed as a dependency of shadcn/ui.

```typescript
// components/command-palette.tsx
import { Command, CommandDialog, CommandInput, CommandList, CommandGroup, CommandItem } from "@/components/ui/command"

export function CommandPalette() {
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault()
        setOpen(prev => !prev)
      }
    }
    document.addEventListener("keydown", handler)
    return () => document.removeEventListener("keydown", handler)
  }, [])

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput placeholder="Search cases, patients, facilities..." />
      <CommandList>
        <CommandGroup heading="Cases">
          {/* search results from TanStack Query */}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  )
}
```

---

## License Report

| Package | License | Downloads/wk | Last Published | Status |
|---|---|---|---|---|
| @tanstack/react-table | MIT | 10.4M | 2026 (v8.21.3) | APPROVED |
| @tanstack/react-virtual | MIT | active | 2026 (v3.13.23) | APPROVED |
| @tanstack/react-query | MIT | 33.2M | 2026 | APPROVED |
| @tanstack/react-form | MIT | 1.33M | 2026 (v1.29.0) | APPROVED |
| @supabase/ssr | MIT | 2.29M | 2026 | APPROVED |
| @supabase/supabase-js | MIT | high | 2026 | APPROVED |
| nuqs | MIT | 2.23M | Oct 2025 (v2.8.9) | APPROVED |
| react-hook-form | MIT | 34.1M | 2026 (v7.72.1) | APPROVED |
| @hey-api/openapi-ts | MIT | 2.03M | 2026 (v0.95.0) | APPROVED |
| orval | MIT | 1.09M | 2026 (v8.7.0) | APPROVED |
| react-spreadsheet-import | MIT | 14.6k | 2026 (v4.7.1) | APPROVED |
| cmdk | MIT | 21.1M | 2026 | APPROVED (bundled via shadcn) |

**Flagged Packages:** None.

**Summary:** 12 approved, 0 warnings, 0 flagged.

---

## Reference Projects

### 1. openstatusHQ/data-table-filters

**URL:** https://github.com/openstatusHQ/data-table-filters
**Live demo:** https://data-table.openstatus.dev/
**Stack:** TanStack Table, shadcn/ui, nuqs, Zustand, TanStack Query, Drizzle ORM
**Architecture:** Feature component with pluggable state adapters

**File structure:**
```
app/
  (app)/
    page.tsx             — Server component, prefetches data
components/
  data-table/
    data-table.tsx       — Core table component
    data-table-toolbar.tsx
    data-table-filter-*.tsx — Faceted filter components
    data-table-column-header.tsx
hooks/
  use-data-table.ts      — Table state + nuqs sync
  use-filter-params.ts   — Typed filter parsers
```

**What to learn:**
- Pluggable state adapters (nuqs vs Zustand) — allows choosing URL vs client state per table
- Faceted filter types (checkbox, range slider, date range) for the case status multi-select
- Bulk action toolbar pattern (select N rows → apply batch status update)
- Column pinning for frozen patient name column on wide tables

**What to avoid:** Drizzle ORM is used for server queries — you use FastAPI instead, so only take the client-side patterns.

### 2. Kiranism/next-shadcn-dashboard-starter

**URL:** https://github.com/Kiranism/next-shadcn-dashboard-starter
**Stack:** Next.js 16 (App Router), shadcn/ui + Tailwind v4, TanStack Query, nuqs, Zustand, kbar
**Architecture:** Feature-folder monolith

**File structure:**
```
app/
  (dashboard)/
    dashboard/
      cases/
        page.tsx         — Server component with HydrationBoundary
features/
  cases/
    components/
      cases-table.tsx
      cases-table-columns.tsx
    hooks/
      use-cases-table-filters.ts
components/
  layout/
    sidebar.tsx
    header.tsx
```

**What to learn:**
- `HydrationBoundary` + `useSuspenseQuery` for no-flash server-prefetch pattern
- Feature-folder structure scales well for 6+ domain areas (cases, facilities, outreach, etc.)
- kbar integration for command palette (alternative to rolling your own with cmdk)

**What to avoid:** Uses Clerk for auth; substitute Supabase `@supabase/ssr` patterns instead.

---

## Implementation Patterns

### Pattern 1: Two-Column Operational Layout

```
┌──────────────┬─────────────────────────────────────────┐
│   Sidebar    │  Main Content Area                       │
│  (nav, 240px)│  ┌─────────────────────────────────────┐ │
│              │  │ Page Header + Toolbar               │ │
│              │  ├─────────────────────────────────────┤ │
│              │  │ DataTable (fills remaining height)  │ │
│              │  │ ... dense rows ...                  │ │
│              │  └─────────────────────────────────────┘ │
└──────────────┴─────────────────────────────────────────┘
```

Use `h-[calc(100vh-64px)]` on the table container to fill remaining viewport height. Set `overflow-auto` on the table body for fixed-header scrollable tables.

### Pattern 2: Case Detail Split-Pane

```
┌──────────────┬─────────────────────────────────────────┐
│  Cases List  │  Case Detail                             │
│  (DataTable) │  ┌─────────────────────────────────────┐ │
│              │  │ Patient Header Bar                  │ │
│              │  ├─────────────────────────────────────┤ │
│              │  │ Tabs: Overview | Clinical | Matches │ │
│              │  │       Outreach | Timeline | Audit   │ │
│              │  ├─────────────────────────────────────┤ │
│              │  │ Tab Content (scrollable)            │ │
│              │  └─────────────────────────────────────┘ │
└──────────────┴─────────────────────────────────────────┘
```

Route: `/dashboard/cases` renders the list; `/dashboard/cases/[id]` renders the detail with the same sidebar visible.

### Pattern 3: Optimistic Status Updates

For quick status changes directly in the table (dropdown in status cell), use TanStack Query's `onMutate` + `onError` rollback:

```typescript
const mutation = useMutation({
  mutationFn: updateCaseStatus,
  onMutate: async ({ caseId, status }) => {
    await queryClient.cancelQueries({ queryKey: ["cases"] })
    const previous = queryClient.getQueryData(["cases", filters])
    queryClient.setQueryData(["cases", filters], (old) =>
      old.map(c => c.id === caseId ? { ...c, status } : c)
    )
    return { previous }
  },
  onError: (err, vars, context) => {
    queryClient.setQueryData(["cases", filters], context.previous)
    toast.error("Failed to update status")
  },
})
```

---

## Gotchas

1. **Tailwind v4 CSS variables change:** If starting fresh with shadcn/ui and Tailwind v4 (v4 is now default), CSS config moves from `tailwind.config.js` to your main CSS file. The `tailwindcss-animate` package is deprecated — use `tw-animate-css` instead. Run `shadcn@latest init` fresh; don't migrate v3 configs manually.

2. **Never use getSession() in server code:** The single most common Supabase + Next.js mistake. `getSession()` reads from the cookie without cryptographic validation. Always `getUser()` in any server-side access control path.

3. **Middleware is not a security boundary for RLS:** Attempting to query Supabase RLS-protected tables from `middleware.ts` returns empty data even with correct credentials. Middleware's only job is cookie/token refresh. Put all data-layer auth checks in Server Components, Server Actions, or Route Handlers.

4. **TanStack Table manual mode for server-side ops:** When sorting/filtering/paginating on the server, you MUST set `manualSorting: true`, `manualFiltering: true`, `manualPagination: true` on the table config. Forgetting any one of these causes the table to apply client-side logic on top of the already-filtered server response.

5. **nuqs shallow vs deep routing:** `shallow: true` (default) updates the URL without triggering a server re-render — fast but data won't refresh. For tables backed by server fetches, use `shallow: false` to trigger RSC re-render, or handle the filter change purely client-side in TanStack Query's `queryKey`.

6. **react-spreadsheet-import + Tailwind conflict:** This library uses Chakra UI internally. When rendered alongside Tailwind, base styles can conflict. Always render it inside a scoped container or within a Dialog that is isolated from the main layout's CSS cascade.

7. **shadcn/ui component ownership:** shadcn components are copy-pasted into your repo, not imported from a package. This means: (a) you own all customization, and (b) updates from shadcn require manual merging. For a stable operational product, this is a feature — you won't have surprise breaking changes from upstream.

8. **Tab content is always mounted (Radix default):** All 6 tab panels render in the DOM, only visibility toggles. This is good for form state preservation but can cause 6x data fetches on case detail load. Use `useSuspenseQuery` with appropriate `staleTime` or lazy-load tab content via `React.lazy` if needed.

9. **openapi-ts v0.x semver instability:** `@hey-api/openapi-ts` is currently at v0.95.0. The 0.x version means API stability is not guaranteed between minor versions. Pin your version in `package.json` and test generated code after bumping. `orval` at v8.x has more stable API semver.

---

## Research Gaps

- **Row-level density benchmarks:** Could not find production benchmarks comparing TanStack Table row density (32px vs 40px vs 48px) performance at 1000+ rows with and without virtualization. If the Operations Queue regularly shows >500 cases, test with `@tanstack/react-virtual` early.

- **Supabase RLS with FastAPI backend:** This project uses FastAPI (not Supabase directly) for all business logic. The Supabase auth patterns documented here cover Next.js → Supabase Auth only. The FastAPI service will need to verify the Supabase JWT on its own (using Supabase's JWT secret or public key verification). This auth handoff pattern between Next.js frontend auth → FastAPI backend auth was not researched here and should be a separate research task.

- **react-spreadsheet-import Tailwind isolation:** Confirmed the library uses Chakra UI internally but could not find a documented isolation pattern that is specific to shadcn/ui + Tailwind v4. Plan for CSS scoping work when integrating the import mapper.

- **HIPAA audit log architecture:** The timeline and audit tabs imply an event sourcing / audit log requirement. No research was done on the audit log data model or whether Supabase's built-in audit log features are sufficient vs a custom events table. This needs design-level attention.

- **Contradiction — TanStack Form adoption:** The TanStack Form docs position it as a react-hook-form replacement, but community evidence (34M vs 1.3M weekly downloads) shows RHF remains dominant. Both have official shadcn/ui integration as of Oct 2025. The recommendation here is RHF for Phase 1 due to ecosystem maturity, but this may change in 12 months as TanStack Form adoption grows.
