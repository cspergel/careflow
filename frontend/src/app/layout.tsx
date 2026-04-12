// @forgeplan-node: frontend-app-shell
// @forgeplan-spec: AC2 — Root layout with sidebar; AC5 — uses getUser() in server component
import type { Metadata } from "next"
import "./globals.css"
import { createClient } from "@/lib/supabase/server"
import { Sidebar } from "@/components/Sidebar"
import type { UserRole } from "@shared/types"

export const metadata: Metadata = {
  title: "PlacementOps",
  description: "Post-acute placement operating system",
}

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  // @forgeplan-spec: AC5 — getUser() exclusively, never getSession()
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()

  // Fetch user profile for role/name display
  let userProfile: { role_key: UserRole; full_name: string; email: string } | null = null
  if (user) {
    const { data } = await supabase
      .from("users")
      .select("role_key, full_name, email")
      .eq("id", user.id)
      .single()
    userProfile = data
  }

  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        {user ? (
          <div className="flex h-screen overflow-hidden">
            <Sidebar
              userRole={userProfile?.role_key}
              userEmail={userProfile?.email ?? user.email}
              userFullName={userProfile?.full_name}
            />
            <main className="flex-1 overflow-auto">
              {children}
            </main>
          </div>
        ) : (
          // Unauthenticated — only login page renders without sidebar
          <main>{children}</main>
        )}
      </body>
    </html>
  )
}
