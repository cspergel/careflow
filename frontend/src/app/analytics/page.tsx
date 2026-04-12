// @forgeplan-node: frontend-app-shell
// @forgeplan-spec: AC2 — Analytics dashboard for manager/admin
// @forgeplan-spec: AC5 — getUser() in server component; analytics data fetched by client component
import { redirect } from "next/navigation"
import { createClient } from "@/lib/supabase/server"
import { AnalyticsDashboard } from "@/app/analytics/AnalyticsDashboard"

export default async function AnalyticsPage() {
  // @forgeplan-spec: AC5 — getUser() exclusively; never getSession()
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()

  if (!user) redirect("/login")

  const { data: profile } = await supabase
    .from("users")
    .select("role_key")
    .eq("id", user.id)
    .single()

  const allowedRoles = ["manager", "admin"]
  if (!profile || !allowedRoles.includes(profile.role_key)) {
    redirect("/dashboard")
  }

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-xl font-bold">Analytics</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Placement performance and workflow metrics
        </p>
      </div>

      {/* Analytics data fetched client-side to maintain AC5 compliance */}
      <AnalyticsDashboard />
    </div>
  )
}
