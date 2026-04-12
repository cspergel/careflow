// @forgeplan-node: frontend-app-shell
// @forgeplan-spec: AC1 — Dashboard KPI cards; fetches from API using browser session
// @forgeplan-spec: AC5 — This client component fetches with browser auth (no getSession() in server)
"use client"

import * as React from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { apiClient, ApiError } from "@/client"

// F6: Field names match backend DashboardReport schema
interface KpiData {
  total_cases: number
  cases_by_status: Record<string, number>
  placement_rate_pct: number
  stage_metrics?: Record<string, unknown>
  avg_placement_days?: number
}

/**
 * DashboardKPIs fetches and displays KPI cards.
 * Rendered as a client component so it uses browser auth (session cookie)
 * instead of requiring getSession() in the server component.
 */
export function DashboardKPIs() {
  const [kpiData, setKpiData] = React.useState<KpiData | null>(null)
  const [error, setError] = React.useState<string | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)

  React.useEffect(() => {
    apiClient
      .fetch<KpiData>("/api/v1/analytics/dashboard")
      .then(setKpiData)
      .catch((err) => {
        setError(
          err instanceof ApiError ? err.message : "Failed to load KPIs"
        )
      })
      .finally(() => setIsLoading(false))
  }, [])

  if (isLoading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 animate-pulse">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="rounded-lg border bg-card p-6 space-y-3">
            <div className="h-3 w-28 rounded bg-muted" />
            <div className="h-8 w-16 rounded bg-muted" />
          </div>
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-md bg-muted px-4 py-3 text-sm text-muted-foreground">
        KPI data unavailable — {error}
      </div>
    )
  }

  // F6: Map backend DashboardReport fields to KPI display
  // pending_approvals is derived from cases_by_status (pending_approval bucket)
  const pendingApprovals = kpiData?.cases_by_status?.["pending_approval"] ?? "—"

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Total Cases
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-3xl font-bold">
            {kpiData?.total_cases ?? "—"}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Placement Rate
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-3xl font-bold text-emerald-600">
            {kpiData?.placement_rate_pct != null
              ? `${kpiData.placement_rate_pct.toFixed(1)}%`
              : "—"}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Avg. Days to Placement
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-3xl font-bold">
            {kpiData?.avg_placement_days != null
              ? kpiData.avg_placement_days.toFixed(1)
              : "—"}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium text-muted-foreground">
            Pending Approvals
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-3xl font-bold text-amber-600">
            {pendingApprovals}
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
