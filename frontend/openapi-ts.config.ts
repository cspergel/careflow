// @forgeplan-node: frontend-app-shell
// @forgeplan-spec: AC4 — @hey-api/openapi-ts config pointing to FastAPI /openapi.json
// @forgeplan-decision: D-frontend-1-openapi-ts-config -- Used @hey-api/openapi-ts v0.43.x config format (input/output flat style). Why: spec pins ^0.43.0; this version uses input/output at root level
import { defineConfig } from "@hey-api/openapi-ts"

export default defineConfig({
  client: "@hey-api/client-fetch",
  input: `${process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000"}/openapi.json`,
  output: "src/client",
  format: "prettier",
})
