// @forgeplan-node: frontend-app-shell
// @forgeplan-spec: AC8 — Operations Queue: status tab filters, SLA aging flags, declined_retry_needed "Route Retry" action
"use client"

import * as React from "react"
import Link from "next/link"
import { ColumnDef } from "@tanstack/react-table"
import { AlertTriangle, RotateCcw } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { StatusBadge } from "@/components/StatusBadge"
import { CaseTable } from "@/components/CaseTable"
import { cn } from "@/lib/utils"
import { daysElapsed, formatDate } from "@/lib/utils"
import { apiClient, ApiError } from "@/client"
import type { PatientCase } from "@shared/types"

// @forgeplan-spec: AC8 — Tab filters mapping to status groups
type QueueTab = "all" | "intake" | "clinical" | "matching" | "outreach" | "response" | "declined-retry"

const TAB_CONFIGS: { key: QueueTab; label: string; statuses: string[] }[] = [
  { key: "all", label: "All", statuses: [] },
  {
    key: "intake",
    label: "Intake",
    statuses: ["new", "intake_in_progress", "intake_complete"],
  },
  {
    key: "clinical",
    label: "Clinical",
    statuses: ["needs_clinical_review", "under_clinical_review"],
  },
  {
    key: "matching",
    label: "Matching",
    statuses: ["ready_for_matching", "facility_options_generated"],
  },
  {
    key: "outreach",
    label: "Outreach",
    statuses: ["outreach_pending_approval", "outreach_in_progress"],
  },
  {
    key: "response",
    label: "Response",
    statuses: ["pending_facility_response", "accepted"],
  },
  {
    key: "declined-retry",
    label: "Declined/Retry",
    statuses: ["declined_retry_needed"],
  },
]

// SLA thresholds in days — flag as overdue when exceeded
const SLA_THRESHOLDS: Partial<Record<string, number>> = {
  new: 1,
  intake_in_progress: 2,
  intake_complete: 1,
  needs_clinical_review: 1,
  under_clinical_review: 2,
  ready_for_matching: 1,
  facility_options_generated: 2,
  outreach_pending_approval: 1,
  outreach_in_progress: 5,
  pending_facility_response: 3,
  declined_retry_needed: 1,
}

function SlaFlag({ case_: c }: { case_: PatientCase }) {
  const threshold = SLA_THRESHOLDS[c.current_status]
  if (!threshold) return null

  const days = daysElapsed(c.updated_at)
  const isOverdue = days >= threshold
  const isWarning = days >= threshold * 0.7

  if (!isWarning) return null

  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-xs font-medium",
        isOverdue
          ? "bg-red-100 text-red-700"
          : "bg-amber-100 text-amber-700"
      )}
      title={`${days} days since last update (SLA: ${threshold} days)`}
    >
      <AlertTriangle className="h-3 w-3" />
      {days}d
    </span>
  )
}

interface RouteRetrySheetProps {
  case_: PatientCase | null
  open: boolean
  onClose: () => void
  onRoute: (caseId: string, destination: "matching" | "outreach") => Promise<void>
}

// @forgeplan-spec: AC8 — Route Retry action for declined_retry_needed
function RouteRetrySheet({ case_, open, onClose, onRoute }: RouteRetrySheetProps) {
  const [destination, setDestination] = React.useState<"matching" | "outreach">("matching")
  const [isLoading, setIsLoading] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  const handleRoute = async () => {
    if (!case_) return
    setIsLoading(true)
    setError(null)
    try {
      await onRoute(case_.id, destination)
      onClose()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Routing failed. Please try again or contact your administrator if the issue persists.")
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <Sheet open={open} onOpenChange={(v) => !v && onClose()}>
      <SheetContent side="right" className="w-[400px]">
        <SheetHeader>
          <SheetTitle>Route Retry</SheetTitle>
          <SheetDescription>
            {case_?.patient_name} — Select where to route this case for retry
          </SheetDescription>
        </SheetHeader>
        <div className="mt-6 space-y-4">
          {error && (
            <div className="rounded-md bg-destructive/10 border border-destructive/20 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}
          <div className="space-y-1.5">
            <label className="text-sm font-medium">Route to</label>
            <Select
              value={destination}
              onValueChange={(v) => setDestination(v as "matching" | "outreach")}
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="matching">Matching (generate new options)</SelectItem>
                <SelectItem value="outreach">Outreach (contact other facilities)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex gap-2">
            <Button onClick={handleRoute} disabled={isLoading} size="sm">
              <RotateCcw className="h-3 w-3 mr-1" />
              {isLoading ? "Routing..." : "Route Case"}
            </Button>
            <Button variant="outline" size="sm" onClick={onClose}>
              Cancel
            </Button>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}

export default function QueuePage() {
  const [activeTab, setActiveTab] = React.useState<QueueTab>("all")
  const [cases, setCases] = React.useState<PatientCase[]>([])
  const [totalCount, setTotalCount] = React.useState(0)
  const [isLoading, setIsLoading] = React.useState(true)
  const [routeCase, setRouteCase] = React.useState<PatientCase | null>(null)
  const [pageError, setPageError] = React.useState<string | null>(null)

  React.useEffect(() => {
    loadCases(activeTab)
  }, [activeTab])

  const loadCases = async (tab: QueueTab) => {
    setIsLoading(true)
    setPageError(null)
    const tabConfig = TAB_CONFIGS.find((t) => t.key === tab)

    // F23: backend PaginationParams uses "page_size" not "limit"
    // F26: repeated status= params instead of comma-separated string
    const params = new URLSearchParams({ page_size: "50", active_only: "true" })
    if (tabConfig && tabConfig.statuses.length > 0) {
      tabConfig.statuses.forEach((s) => params.append("status", s))
    }

    try {
      const data = await apiClient.fetch<{ cases: PatientCase[]; total: number }>(
        `/api/v1/cases?${params.toString()}`
      )
      setCases(data.cases)
      setTotalCount(data.total)
    } catch (err) {
      setPageError(
        err instanceof ApiError ? `Failed to load queue: ${err.message}` : "Failed to load queue"
      )
    } finally {
      setIsLoading(false)
    }
  }

  const handleRouteRetry = async (
    caseId: string,
    destination: "matching" | "outreach"
  ) => {
    await apiClient.fetch(`/api/v1/cases/${caseId}/route-retry`, {
      method: "POST",
      body: JSON.stringify({ destination }),
    })
    await loadCases(activeTab)
  }

  // @forgeplan-spec: AC8 — Columns with SLA flags and Route Retry action
  const queueColumns: ColumnDef<PatientCase>[] = [
    {
      accessorKey: "patient_name",
      header: "Patient",
      cell: ({ row }) => (
        <Link
          href={`/cases/${row.original.id}`}
          className="font-medium hover:underline"
        >
          {row.getValue("patient_name")}
        </Link>
      ),
    },
    {
      accessorKey: "current_status",
      header: "Status",
      cell: ({ row }) => (
        <div className="flex items-center gap-2">
          <StatusBadge status={row.getValue("current_status")} />
          <SlaFlag case_={row.original} />
        </div>
      ),
    },
    {
      accessorKey: "priority_level",
      header: "Priority",
      cell: ({ row }) => {
        const priority = row.getValue("priority_level") as string | null
        if (!priority) return "—"
        return (
          <span
            className={cn(
              "text-xs font-medium",
              priority === "emergent"
                ? "text-red-600"
                : priority === "urgent"
                  ? "text-amber-600"
                  : "text-muted-foreground"
            )}
          >
            {priority.charAt(0).toUpperCase() + priority.slice(1)}
          </span>
        )
      },
    },
    {
      accessorKey: "primary_diagnosis_text",
      header: "Diagnosis",
      cell: ({ row }) => (
        <span className="text-sm text-muted-foreground truncate max-w-40 block">
          {row.getValue("primary_diagnosis_text") ?? "—"}
        </span>
      ),
    },
    {
      accessorKey: "updated_at",
      header: "Updated",
      cell: ({ row }) => formatDate(row.getValue("updated_at")),
    },
    {
      id: "actions",
      header: "",
      cell: ({ row }) => {
        const c = row.original
        if (c.current_status === "declined_retry_needed") {
          return (
            <Button
              size="sm"
              variant="outline"
              className="text-xs"
              onClick={(e) => {
                e.stopPropagation()
                setRouteCase(c)
              }}
            >
              <RotateCcw className="h-3 w-3 mr-1" />
              Route Retry
            </Button>
          )
        }
        return null
      },
    },
  ]

  return (
    <div className="flex flex-col h-full">
      {/* Page header */}
      <div className="border-b px-6 py-4">
        <h1 className="text-xl font-bold">Operations Queue</h1>
        <p className="text-sm text-muted-foreground">
          {totalCount} active cases across all stages
        </p>
      </div>

      {/* @forgeplan-spec: AC8 — Status tab filters */}
      <div className="border-b px-6">
        <div className="flex gap-0 -mb-px">
          {TAB_CONFIGS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={cn(
                "px-4 py-2.5 text-sm font-medium border-b-2 transition-colors",
                activeTab === tab.key
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
              )}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-auto p-6">
        {pageError && (
          <div className="mb-4 rounded-md bg-destructive/10 border border-destructive/20 px-4 py-3 text-sm text-destructive">
            {pageError}
          </div>
        )}

        {/* F11: pageKey namespaces URL params so queue filters don't contaminate other pages */}
        <CaseTable
          data={cases}
          columns={queueColumns}
          totalCount={totalCount}
          isLoading={isLoading}
          pageKey="queue"
        />
      </div>

      <RouteRetrySheet
        case_={routeCase}
        open={!!routeCase}
        onClose={() => setRouteCase(null)}
        onRoute={handleRouteRetry}
      />
    </div>
  )
}
