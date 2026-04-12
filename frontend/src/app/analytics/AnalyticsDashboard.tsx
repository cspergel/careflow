// @forgeplan-node: frontend-app-shell
// @forgeplan-spec: AC2 — Analytics dashboard charts and KPIs (client component)
"use client"

import * as React from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { apiClient, ApiError } from "@/client"

interface AnalyticsData {
  placement_rate: number
  avg_days_to_placement: number
  active_cases: number
  placed_this_month: number
  declined_this_month: number
  top_decline_reasons: { reason: string; count: number }[]
  status_breakdown: { status: string; count: number }[]
}

export function AnalyticsDashboard() {
  const [analytics, setAnalytics] = React.useState<AnalyticsData | null>(null)
  const [error, setError] = React.useState<string | null>(null)
  const [isLoading, setIsLoading] = React.useState(true)

  React.useEffect(() => {
    apiClient
      .fetch<AnalyticsData>("/api/v1/analytics/summary")
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
        Analytics data not available — {error ?? "ensure the FastAPI backend is running"}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Placement Rate
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold text-emerald-600">
              {(analytics.placement_rate * 100).toFixed(1)}%
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
              {analytics.avg_days_to_placement.toFixed(1)}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Placed This Month
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold">{analytics.placed_this_month}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Declined This Month
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-bold text-amber-600">
              {analytics.declined_this_month}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Status breakdown */}
      {analytics.status_breakdown.length > 0 && (
        <div>
          <h2 className="text-base font-semibold mb-3">Cases by Status</h2>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {analytics.status_breakdown.map((item) => (
              <Card key={item.status}>
                <CardHeader className="pb-1 pt-4 px-4">
                  <CardTitle className="text-xs text-muted-foreground capitalize">
                    {item.status.replace(/_/g, " ")}
                  </CardTitle>
                </CardHeader>
                <CardContent className="px-4 pb-4">
                  <p className="text-2xl font-bold">{item.count}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}

      {/* Top decline reasons */}
      {analytics.top_decline_reasons.length > 0 && (
        <div>
          <h2 className="text-base font-semibold mb-3">Top Decline Reasons</h2>
          <div className="space-y-2 max-w-md">
            {analytics.top_decline_reasons.map((item) => (
              <div
                key={item.reason}
                className="flex items-center justify-between rounded-md border px-4 py-2"
              >
                <span className="text-sm">{item.reason}</span>
                <span className="text-sm font-bold">{item.count}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
