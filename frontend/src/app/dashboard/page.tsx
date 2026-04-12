// @forgeplan-node: frontend-app-shell
// @forgeplan-spec: AC1 — manager/admin/read_only landing; AC5 — getUser() in server component
import { redirect } from "next/navigation"
import { createClient } from "@/lib/supabase/server"
import { formatDate } from "@/lib/utils"
import { DashboardKPIs } from "@/app/dashboard/DashboardKPIs"

export default async function DashboardPage() {
  // @forgeplan-spec: AC5 — getUser() exclusively
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()

  if (!user) {
    redirect("/login")
  }

  const { data: profile } = await supabase
    .from("users")
    .select("role_key, full_name, organization_id")
    .eq("id", user.id)
    .single()

  // @forgeplan-spec: AC1 — Dashboard restricted to manager/admin/read_only
  const allowedRoles = ["manager", "admin", "read_only"]
  if (!profile || !allowedRoles.includes(profile.role_key)) {
    redirect("/queue")
  }

  // KPI data is fetched client-side via DashboardKPIs component
  // to avoid using getSession() in server components (AC5 compliance)

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-xl font-bold">Dashboard</h1>
        <p className="text-sm text-muted-foreground mt-1">
          {new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })} | {profile?.role_key.replace(/_/g, ' ')} view
        </p>
      </div>

      {/* KPI Cards — loaded client-side to maintain AC5 getUser()-only server compliance */}
      <DashboardKPIs />

      {/* Link to full analytics */}
      <div className="rounded-lg border bg-card p-6 text-center text-muted-foreground text-sm">
        For full reporting, visit the{" "}
        <a href="/analytics" className="text-primary underline">
          Analytics dashboard
        </a>
        .
      </div>
    </div>
  )
}
