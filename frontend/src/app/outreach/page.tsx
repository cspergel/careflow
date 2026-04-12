// @forgeplan-node: frontend-app-shell
// @forgeplan-spec: AC2 — Outreach dashboard for placement coordinators
"use client"

import * as React from "react"
import Link from "next/link"
import { ColumnDef } from "@tanstack/react-table"
import { Badge } from "@/components/ui/badge"
import { CaseTable } from "@/components/CaseTable"
import { FilterBar } from "@/components/FilterBar"
import { formatDate } from "@/lib/utils"
import { apiClient, ApiError } from "@/client"
import type { OutreachAction } from "@shared/types"

interface OutreachRow extends OutreachAction {
  patient_name?: string
  facility_name?: string
}

const APPROVAL_STATUS_CONFIG = {
  draft: { label: "Draft", color: "bg-slate-100 text-slate-700" },
  pending_approval: { label: "Pending Approval", color: "bg-amber-100 text-amber-700" },
  approved: { label: "Approved", color: "bg-emerald-100 text-emerald-700" },
  sent: { label: "Sent", color: "bg-blue-100 text-blue-700" },
  canceled: { label: "Canceled", color: "bg-gray-100 text-gray-600" },
  failed: { label: "Failed", color: "bg-red-100 text-red-700" },
} as const

const outreachColumns: ColumnDef<OutreachRow>[] = [
  {
    accessorKey: "patient_name",
    header: "Patient",
    cell: ({ row }) => (
      <Link
        href={`/cases/${row.original.patient_case_id}?tab=outreach`}
        className="font-medium hover:underline"
      >
        {row.getValue("patient_name") ?? row.original.patient_case_id.slice(0, 8) + "…"}
      </Link>
    ),
  },
  {
    accessorKey: "facility_name",
    header: "Facility",
    cell: ({ row }) => row.getValue("facility_name") ?? "—",
  },
  {
    accessorKey: "channel",
    header: "Channel",
    cell: ({ row }) => {
      const channel = row.getValue("channel") as string
      return (
        <Badge variant="outline" className="text-xs capitalize">
          {channel.replace("_", " ")}
        </Badge>
      )
    },
  },
  {
    accessorKey: "approval_status",
    header: "Status",
    cell: ({ row }) => {
      const status = row.getValue("approval_status") as keyof typeof APPROVAL_STATUS_CONFIG
      const config = APPROVAL_STATUS_CONFIG[status]
      return (
        <Badge variant="outline" className={`text-xs ${config?.color ?? ""}`}>
          {config?.label ?? status}
        </Badge>
      )
    },
  },
  {
    accessorKey: "created_at",
    header: "Created",
    cell: ({ row }) => formatDate(row.getValue("created_at")),
  },
]

export default function OutreachPage() {
  const [outreachActions, setOutreachActions] = React.useState<OutreachRow[]>([])
  const [totalCount, setTotalCount] = React.useState(0)
  const [isLoading, setIsLoading] = React.useState(true)
  const [pageError, setPageError] = React.useState<string | null>(null)

  React.useEffect(() => {
    loadOutreach()
  }, [])

  const loadOutreach = async () => {
    setIsLoading(true)
    setPageError(null)
    try {
      // F4: correct backend route is GET /api/v1/queues/outreach
      const data = await apiClient.fetch<{ items: OutreachRow[]; total: number }>(
        "/api/v1/queues/outreach?limit=50"
      )
      setOutreachActions(data.items)
      setTotalCount(data.total)
    } catch (err) {
      setPageError(
        err instanceof ApiError
          ? `Failed to load outreach: ${err.message}`
          : "Failed to load outreach"
      )
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="border-b px-6 py-4">
        <h1 className="text-xl font-bold">Outreach Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          Cross-case outreach communications — {totalCount} total actions
        </p>
      </div>

      <div className="flex-1 overflow-auto p-6 space-y-4">
        {pageError && (
          <div className="rounded-md bg-destructive/10 border border-destructive/20 px-4 py-3 text-sm text-destructive">
            {pageError}
          </div>
        )}

        <FilterBar showStatusFilter={false} />

        {/* F11: pageKey namespaces URL params so outreach filters don't contaminate other pages */}
        <CaseTable
          data={outreachActions}
          columns={outreachColumns}
          totalCount={totalCount}
          isLoading={isLoading}
          pageKey="outreach"
        />
      </div>
    </div>
  )
}
