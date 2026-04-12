// @forgeplan-node: frontend-app-shell
// @forgeplan-spec: AC5 — Browser client for Client Components
import { createBrowserClient } from "@supabase/ssr"

/**
 * Creates a Supabase client for use in Client Components (browser-side).
 * Session is stored in cookies, not localStorage.
 */
export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  )
}
