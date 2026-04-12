// @forgeplan-node: frontend-app-shell
// @forgeplan-spec: AC4 — Typed API client generated from FastAPI /openapi.json via @hey-api/openapi-ts
// This file is a placeholder. Run `npm run generate-client` with FastAPI running to regenerate.
// The generated output will include: types.gen.ts, services.gen.ts, schemas.gen.ts

/**
 * @forgeplan-decision: D-frontend-3-api-client-placeholder -- Placeholder client exported from index.ts. Why: actual generation requires FastAPI server; placeholder provides type-safe interface for current-phase development
 */

// Re-export everything from generated files when available
// export * from "./types.gen"
// export * from "./services.gen"
// export * from "./schemas.gen"

import { createClient } from "@/lib/supabase/client"

export interface ClientConfig {
  baseUrl: string
  headers?: Record<string, string>
}

/**
 * Creates the typed API client instance pointing to the FastAPI backend.
 * Replace this with the generated client after running `npm run generate-client`.
 */
export function createApiClient(config?: Partial<ClientConfig>) {
  const baseUrl =
    config?.baseUrl ??
    process.env.NEXT_PUBLIC_API_BASE_URL ??
    "http://localhost:8000"

  return {
    baseUrl,
    // Typed service methods will be available after running generate-client
    // until then, use the raw fetch helper below
    async fetch<T>(path: string, init?: RequestInit): Promise<T> {
      // Retrieve the Supabase session token and attach it as the Authorization header.
      // All backend endpoints require a valid JWT (HTTP 401 without it).
      // getUser() validates the token with the Supabase server so revoked tokens
      // are rejected here rather than forwarded as valid Bearer credentials.
      const supabase = createClient()
      const { data: { user } } = await supabase.auth.getUser()
      // After server-side validation, read the (now-refreshed) local session for the token.
      const { data: sessionData } = await supabase.auth.getSession()
      const accessToken = user ? sessionData?.session?.access_token : undefined

      const res = await fetch(`${baseUrl}${path}`, {
        ...init,
        headers: {
          "Content-Type": "application/json",
          ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
          ...config?.headers,
          ...init?.headers,
        },
      })
      if (!res.ok) {
        const error = await res.json().catch(() => ({ detail: res.statusText }))
        throw new ApiError(res.status, error.detail ?? res.statusText, error)
      }
      return res.json() as Promise<T>
    },
  }
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly detail?: unknown
  ) {
    super(message)
    this.name = "ApiError"
  }
}

// Singleton client instance
export const apiClient = createApiClient()
