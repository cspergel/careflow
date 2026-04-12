# @forgeplan-node: auth-module
"""
Test helpers for auth-module tests.

Shared utilities imported directly by test modules:
  - make_jwt: mint test JWTs
  - make_rbac_app: build a stub FastAPI app for RBAC integration tests
  - TEST_ORG_ID, TEST_USER_ID: stable UUIDs for fixtures

These are importable module-level helpers (not pytest fixtures).
Fixtures that depend on db_session live in conftest.py.
"""

import os
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt

# Stable IDs shared across tests
TEST_ORG_ID: UUID = UUID("11111111-1111-1111-1111-111111111111")
TEST_USER_ID: UUID = UUID("22222222-2222-2222-2222-222222222222")
TEST_SECRET = "test-secret-key-minimum-32-chars-long"


def make_jwt(
    user_id: UUID | None = None,
    org_id: UUID | None = None,
    role_key: str = "intake_staff",
    secret: str = TEST_SECRET,
    expired: bool = False,
    algorithm: str = "HS256",
) -> str:
    """
    Mint a test JWT with app_metadata including organization_id and role_key.

    All test JWTs use HS256 with TEST_SECRET matching the SUPABASE_JWT_SECRET env var.
    """
    uid = user_id or TEST_USER_ID
    oid = org_id or TEST_ORG_ID
    now = datetime.now(timezone.utc)
    exp = now - timedelta(hours=1) if expired else now + timedelta(hours=1)

    payload = {
        "sub": str(uid),
        "aud": "authenticated",
        "iat": now,
        "exp": exp,
        "app_metadata": {
            "organization_id": str(oid),
            "role_key": role_key,
        },
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


def make_rbac_app(db_session):
    """
    Build a FastAPI app with stub routes for RBAC integration tests (AC6-AC11).

    Each stub route applies the same Depends() guards that the real module
    routers would apply, allowing RBAC tests without real module code.
    This app is freshly constructed per test to avoid state leakage.
    """
    from fastapi import FastAPI
    from placementops.core.database import get_db
    from placementops.modules.auth.router import router
    from placementops.modules.auth.dependencies import (
        require_role,
        require_write_permission,
    )

    app = FastAPI()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    # Mount auth router for completeness (logout, me tests from RBAC context)
    app.include_router(router, prefix="/api/v1/auth")

    # ── Case endpoints ────────────────────────────────────────────────────────
    @app.get(
        "/api/v1/cases",
        dependencies=[require_role("admin", "intake_staff", "clinical_reviewer",
                                   "placement_coordinator", "manager", "read_only")],
    )
    async def list_cases():
        return {"cases": []}

    @app.post(
        "/api/v1/cases",
        dependencies=[require_write_permission, require_role("admin", "intake_staff")],
    )
    async def create_case():
        return {"id": str(uuid4())}

    @app.patch(
        "/api/v1/cases/{case_id}",
        dependencies=[require_write_permission,
                      require_role("admin", "intake_staff", "placement_coordinator")],
    )
    async def update_case(case_id: str):
        return {"id": case_id}

    # ── Assessment endpoints ──────────────────────────────────────────────────
    @app.post(
        "/api/v1/cases/{case_id}/assessments",
        dependencies=[require_write_permission, require_role("admin", "clinical_reviewer")],
    )
    async def create_assessment(case_id: str):
        return {"id": str(uuid4())}

    @app.post(
        "/api/v1/assessments",
        dependencies=[require_write_permission, require_role("admin", "clinical_reviewer")],
    )
    async def create_assessment_alt():
        return {"id": str(uuid4())}

    # ── Facility endpoints ────────────────────────────────────────────────────
    @app.get(
        "/api/v1/facilities",
        dependencies=[require_role("admin", "intake_staff", "clinical_reviewer",
                                   "placement_coordinator", "manager", "read_only")],
    )
    async def list_facilities():
        return {"facilities": []}

    @app.post(
        "/api/v1/facilities",
        dependencies=[require_write_permission, require_role("admin")],
    )
    async def create_facility():
        return {"id": str(uuid4())}

    @app.patch(
        "/api/v1/facilities/{facility_id}",
        dependencies=[require_write_permission, require_role("admin")],
    )
    async def update_facility(facility_id: str):
        return {"id": facility_id}

    @app.delete(
        "/api/v1/facilities/{facility_id}",
        dependencies=[require_write_permission, require_role("admin")],
    )
    async def delete_facility(facility_id: str):
        return {}

    # ── Matching endpoints ────────────────────────────────────────────────────
    @app.post(
        "/api/v1/cases/{case_id}/generate-matches",
        dependencies=[require_write_permission,
                      require_role("admin", "placement_coordinator", "clinical_reviewer")],
    )
    async def generate_matches(case_id: str):
        return {"matches": []}

    # ── Outreach endpoints ────────────────────────────────────────────────────
    @app.post(
        "/api/v1/outreach-actions/{action_id}/approve",
        dependencies=[require_write_permission, require_role("admin", "placement_coordinator")],
    )
    async def approve_outreach(action_id: str):
        return {"id": action_id}

    # ── Outcomes endpoints ────────────────────────────────────────────────────
    @app.post(
        "/api/v1/outcomes",
        dependencies=[require_write_permission, require_role("admin", "placement_coordinator")],
    )
    async def record_outcome():
        return {"id": str(uuid4())}

    # ── Analytics endpoints ───────────────────────────────────────────────────
    @app.get(
        "/api/v1/analytics",
        dependencies=[require_role("admin", "manager")],
    )
    async def list_analytics():
        return {"data": []}

    @app.get(
        "/api/v1/analytics/dashboard",
        dependencies=[require_role("admin", "manager")],
    )
    async def analytics_dashboard():
        return {"data": {}}

    # ── Queues endpoints ──────────────────────────────────────────────────────
    @app.get(
        "/api/v1/queues/operations",
        dependencies=[require_role("admin", "manager", "placement_coordinator",
                                   "clinical_reviewer")],
    )
    async def operations_queue():
        return {"queue": []}

    # ── Admin endpoints ───────────────────────────────────────────────────────
    @app.post(
        "/api/v1/admin/users",
        dependencies=[require_write_permission, require_role("admin")],
    )
    async def create_admin_user():
        return {"id": str(uuid4())}

    return app
