// @forgeplan-node: frontend-app-shell
// @forgeplan-spec: AC2 — Analytics dashboard charts and KPIs (client component)
"use client"

import * as React from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { apiClient, ApiError } from "@/client"

interface AnalyticsData {
  total_cases: number
  cases_by_status: Record<string, number>
  placement_rate_pct: number
  avg_placement_days?: number | null
  stage_metrics: { stage_name: string; avg_cycle_hours: number; case_count: number }[]
  date_from: string
  date_to: string
  generated_at: string
}

export function AnalyticsDashboard() {
  const [analytics, setAnalytics] = React.useState<AnalyticsData | null>(null)
  const [error, setError] = React.useState<string | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)

  React.useEffect(() => {
    apiClient
      .fetch<AnalyticsData>("/api/v1/analytics/dashboard")
      .then(setAnalytics)
      .catch((err) => {
        setError(
          err instanceof ApiError
            ? err.message
            : "Analytics data unavailable"
        )
      })
      .finally(() => setIsLoading(false))
  }, [])

  if (isLoading) {
    return (
      <div className="animate-pulse space-y-4">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="rounded-lg border bg-card p-6">
              <div className="bg-gray-200 rounded h-3 w-24 mb-3" />
              <div className="bg-gray-200 rounded h-8 w-16" />
            </div>
          ))}
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {[...Array(2)].map((_, i) => (
            <div key={i} className="rounded-lg border bg-card p-6">
              <div className="bg-gray-200 rounded h-3 w-32 mb-4" />
              <div className="bg-gray-200 rounded h-40 w-full" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (error || !analytics) {
    return (
      <div className="rounded-lg border bg-card p-6 text-center text-muted-foreground text-sm">
        Analytics data not available. Try refreshing the page, or contact your administrator if the issue persists.
      </div>
    )
  }

  const statusEntries = Object.entries(analytics.cases_by_status)

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total Cases
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{analytics.total_cases}</p>
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
              {analytics.placement_rate_pct.toFixed(1)}%
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Avg Days to Placement
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">
              {analytics.avg_placement_days != null
                ? analytics.avg_placement_days.toFixed(1)
                : "—"}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Stage Metrics
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{analytics.stage_metrics.length}</p>
          </CardContent>
        </Card>
      </div>

      {/* Status breakdown */}
      {statusEntries.length > 0 && (
        <div>
          <h2 className="text-base font-semibold mb-3">Cases by Status</h2>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {statusEntries.map(([status, count]) => (
              <Card key={status}>
                <CardHeader className="pb-1 pt-4 px-4">
                  <CardTitle className="text-xs text-muted-foreground capitalize">
                    {status.replace(/_/g, " ")}
                  </CardTitle>
                </CardHeader>
                <CardContent className="px-4 pb-4">
                  <p className="text-2xl font-bold">{count}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* Stage metrics */}
      {analytics.stage_metrics.length > 0 && (
        <div>
          <h2 className="text-base font-semibold mb-3">Stage Cycle Times</h2>
          <div className="space-y-2 max-w-md">
            {analytics.stage_metrics.map((item) => (
              <div
                key={item.stage_name}
                className="flex items-center justify-between rounded-md border px-4 py-2"
              >
                <span className="text-sm capitalize">{item.stage_name.replace(/_/g, " ")}</span>
                <span className="text-sm font-bold">{item.avg_cycle_hours.toFixed(1)}h</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
