# @forgeplan-node: core-infrastructure
"""
PlacementOps FastAPI application entry point.

Registers: CORS, PHI-safe logging, health endpoint.
Feature-module routers are imported here when those modules are built.
"""
# @forgeplan-spec: AC2

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from placementops.core.middleware import configure_phi_safe_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup → configure logging."""
    log_level = os.getenv("LOG_LEVEL", "INFO")
    configure_phi_safe_logging(level=log_level)
    yield
    # Teardown: engine disposal is handled by NullPool — no pool to drain


app = FastAPI(
    title="PlacementOps API",
    description="Post-acute care placement operating system",
    version="1.0.0",
    lifespan=lifespan,
    # Disable OpenAPI docs in production
    docs_url="/docs" if os.getenv("APP_ENV", "production") != "production" else None,
    redoc_url="/redoc" if os.getenv("APP_ENV", "production") != "production" else None,
)

# CORS — origins configured via env var (comma-separated list)
_cors_origins = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health endpoint ───────────────────────────────────────────────────────────
# @forgeplan-spec: AC2
@app.get("/api/v1/health", tags=["infrastructure"])
async def health_check() -> dict:
    """
    GET /api/v1/health

    Returns HTTP 200 with {"status": "ok"} when the application is running.
    Does NOT perform a database ping — liveness only (readiness probes are separate).
    """
    return {"status": "ok", "service": "placementops-api"}


# ── Module routers ────────────────────────────────────────────────────────────
from placementops.modules.auth.router import router as auth_router
app.include_router(auth_router, prefix="/api/v1")

from placementops.modules.facilities.router import router as facilities_router
app.include_router(facilities_router, prefix="/api/v1")

from placementops.modules.clinical.router import router as clinical_router
app.include_router(clinical_router, prefix="/api/v1")

from placementops.modules.intake.router import router as intake_router
app.include_router(intake_router, prefix="/api/v1")

from placementops.modules.matching.router import router as matching_router
app.include_router(matching_router, prefix="/api/v1")

# admin_router registered BEFORE outreach_router so that admin's POST/PATCH
# handlers on /templates/outreach take precedence over outreach's 405 stubs
# (FastAPI resolves routes in registration order). F29 fix.
from placementops.modules.admin.router import router as admin_router
app.include_router(admin_router, prefix="/api/v1")

from placementops.modules.outreach.router import router as outreach_router
app.include_router(outreach_router, prefix="/api/v1")

from placementops.modules.outcomes.router import router as outcomes_router
app.include_router(outcomes_router, prefix="/api/v1")

from placementops.modules.analytics.router import router as analytics_router
app.include_router(analytics_router, prefix="/api/v1")

# Additional module routers registered here as each node is built:
