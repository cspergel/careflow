// @forgeplan-node: frontend-app-shell
// @forgeplan-spec: AC1 — Root redirects to role-appropriate landing
import { redirect } from "next/navigation"
import { createClient } from "@/lib/supabase/server"
// F23: getRoleLanding extracted to lib/utils to avoid duplication with layout.tsx
import { getRoleLanding } from "@/lib/utils"
import type { UserRole } from "@shared/types"

export default async function RootPage() {
  // @forgeplan-spec: AC5 — getUser() exclusively
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()

  if (!user) {
    redirect("/login")
  }

  const { data: profile } = await supabase
    .from("users")
    .select("role_key")
    .eq("id", user.id)
    .single()

  redirect(
    profile?.role_key
      ? getRoleLanding(profile.role_key as UserRole)
      : "/dashboard"
  )
}
