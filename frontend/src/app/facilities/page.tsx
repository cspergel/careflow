// @forgeplan-node: frontend-app-shell
// @forgeplan-spec: AC2 — Facilities directory page
"use client"

import * as React from "react"
import Link from "next/link"
import { ColumnDef } from "@tanstack/react-table"
import { Building2 } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { CaseTable } from "@/components/CaseTable"
import { FilterBar } from "@/components/FilterBar"
import { apiClient, ApiError } from "@/client"
import type { Facility } from "@shared/types"

const FACILITY_TYPE_LABELS = {
  snf: "SNF",
  irf: "IRF",
  ltach: "LTACH",
} as const

const facilityColumns: ColumnDef<Facility>[] = [
  {
    accessorKey: "facility_name",
    header: "Facility",
    cell: ({ row }) => (
      <Link
        href={`/facilities/${row.original.id}`}
        className="font-medium hover:underline flex items-center gap-2"
      >
        <Building2 className="h-4 w-4 text-muted-foreground shrink-0" />
        {row.getValue("facility_name")}
      </Link>
    ),
  },
  {
    accessorKey: "facility_type",
    header: "Type",
    cell: ({ row }) => {
      const type = row.getValue("facility_type") as keyof typeof FACILITY_TYPE_LABELS
      return (
        <Badge variant="outline" className="text-xs">
          {FACILITY_TYPE_LABELS[type] ?? type}
        </Badge>
      )
    },
  },
  {
    accessorKey: "city",
    header: "City",
    cell: ({ row }) => row.getValue("city") ?? "—",
  },
  {
    accessorKey: "state",
    header: "State",
    cell: ({ row }) => row.getValue("state") ?? "—",
  },
  {
    accessorKey: "active_status",
    header: "Status",
    cell: ({ row }) => {
      const active = row.getValue("active_status") as boolean
      return (
        <Badge
          variant="outline"
          className={
            active
              ? "bg-emerald-50 text-emerald-700 border-emerald-200 text-xs"
              : "bg-gray-50 text-gray-500 border-gray-200 text-xs"
          }
        >
          {active ? "Active" : "Inactive"}
        </Badge>
      )
    },
  },
]

export default function FacilitiesPage() {
  const [facilities, setFacilities] = React.useState<Facility[]>([])
  const [totalCount, setTotalCount] = React.useState(0)
  const [isLoading, setIsLoading] = React.useState(true)
  const [pageError, setPageError] = React.useState<string | null>(null)

  React.useEffect(() => {
    loadFacilities()
  }, [])

  const loadFacilities = async () => {
    setIsLoading(true)
    setPageError(null)
    try {
      const data = await apiClient.fetch<{ items: Facility[]; total: number }>(
        "/api/v1/facilities?limit=50&active_only=true"
      )
      setFacilities(data.items)
      setTotalCount(data.total)
    } catch (err) {
      setPageError(
        err instanceof ApiError
          ? `Failed to load facilities: ${err.message}`
          : "Failed to load facilities"
      )
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="border-b px-6 py-4">
        <h1 className="text-xl font-bold">Facility Directory</h1>
        <p className="text-sm text-muted-foreground">
          {totalCount} facilities in your network
        </p>
      </div>

      <div className="flex-1 overflow-auto p-6 space-y-4">
        {pageError && (
          <div className="rounded-md bg-destructive/10 border border-destructive/20 px-4 py-3 text-sm text-destructive">
            {pageError}
          </div>
        )}

        <FilterBar showStatusFilter={false} />

        <CaseTable
          data={facilities}
          columns={facilityColumns}
          totalCount={totalCount}
          isLoading={isLoading}
        />
      </div>
    </div>
  )
}
