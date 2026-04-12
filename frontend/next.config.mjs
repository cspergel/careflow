// @forgeplan-node: frontend-app-shell
/** @type {import('next').NextConfig} */
const nextConfig = {
  // Allow cross-origin requests to the FastAPI backend during development
  async rewrites() {
    return []
  },
  // Ensure environment variables are available at build time
  env: {
    NEXT_PUBLIC_API_BASE_URL: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
  },
}

export default nextConfig
