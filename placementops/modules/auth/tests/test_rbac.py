# @forgeplan-node: auth-module
"""
RBAC tests: role-based access control for all 6 roles.

AC6:  intake_staff permissions
AC7:  clinical_reviewer permissions
AC8:  placement_coordinator permissions
AC9:  manager permissions
AC10: admin permissions
AC11: read_only permissions (including handler-never-called assertion)
AC12: role_key comes from DB row, not JWT claims
"""
# @forgeplan-spec: AC6
# @forgeplan-spec: AC7
# @forgeplan-spec: AC8
# @forgeplan-spec: AC9
# @forgeplan-spec: AC10
# @forgeplan-spec: AC11
# @forgeplan-spec: AC12

from unittest.mock import MagicMock, patch, call
from uuid import uuid4

import pytest
from httpx import AsyncClient, ASGITransport

from placementops.modules.auth.tests.helpers import TEST_ORG_ID, make_jwt, make_rbac_app


def _headers_for(user) -> dict:
    """Build Authorization headers for a user using a test JWT."""
    token = make_jwt(
        user_id=user.id,
        org_id=user.organization_id,
        role_key=user.role_key,
    )
    return {"Authorization": f"Bearer {token}"}


async def _make_rbac_client(db_session):
    """Build an AsyncClient for the RBAC stub app."""
    app = make_rbac_app(db_session)
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ── AC6: intake_staff ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_intake_staff(db_session, org, intake_staff_user):
    """
    AC6: intake_staff can create/edit cases; cannot access assessments,
    analytics, /queues/operations, or admin endpoints.
    """
    # @forgeplan-spec: AC6
    headers = _headers_for(intake_staff_user)

    async with await _make_rbac_client(db_session) as client:
        # Allowed: POST /cases (intake_staff in allowed_roles)
        resp = await client.post("/api/v1/cases", headers=headers)
        assert resp.status_code == 200, f"POST /cases: {resp.status_code} {resp.text}"

        # Allowed: GET /cases
        resp = await client.get("/api/v1/cases", headers=headers)
        assert resp.status_code == 200

        # Forbidden: POST /cases/{id}/assessments
        resp = await client.post(f"/api/v1/cases/{uuid4()}/assessments", headers=headers)
        assert resp.status_code == 403, f"Expected 403 on assessment creation: {resp.status_code}"

        # Forbidden: GET /analytics/dashboard (intake_staff not in allowed roles)
        resp = await client.get("/api/v1/analytics/dashboard", headers=headers)
        assert resp.status_code == 403

        # Forbidden: GET /queues/operations
        resp = await client.get("/api/v1/queues/operations", headers=headers)
        assert resp.status_code == 403

        # Forbidden: POST /admin/users
        resp = await client.post("/api/v1/admin/users", headers=headers)
        assert resp.status_code == 403


# ── AC7: clinical_reviewer ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_clinical_reviewer(db_session, org, clinical_reviewer_user):
    """
    AC7: clinical_reviewer can create assessments and access /queues/operations;
    cannot approve outreach, record outcomes, view analytics dashboard, or access admin.
    """
    # @forgeplan-spec: AC7
    headers = _headers_for(clinical_reviewer_user)

    async with await _make_rbac_client(db_session) as client:
        # Allowed: POST /cases/{id}/assessments
        resp = await client.post(f"/api/v1/cases/{uuid4()}/assessments", headers=headers)
        assert resp.status_code == 200, f"Expected 200 on assessment creation: {resp.status_code}"

        # Forbidden: POST /outreach-actions/{id}/approve
        resp = await client.post(f"/api/v1/outreach-actions/{uuid4()}/approve", headers=headers)
        assert resp.status_code == 403

        # Forbidden: POST /outcomes
        resp = await client.post("/api/v1/outcomes", headers=headers)
        assert resp.status_code == 403

        # Forbidden: GET /analytics/dashboard
        resp = await client.get("/api/v1/analytics/dashboard", headers=headers)
        assert resp.status_code == 403

        # Allowed: GET /queues/operations
        resp = await client.get("/api/v1/queues/operations", headers=headers)
        assert resp.status_code == 200

        # Forbidden: POST /admin/users
        resp = await client.post("/api/v1/admin/users", headers=headers)
        assert resp.status_code == 403


# ── AC8: placement_coordinator ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_placement_coordinator(db_session, org, placement_coordinator_user):
    """
    AC8: placement_coordinator can generate matches, approve outreach,
    access /queues/operations; cannot access analytics dashboard or admin.
    """
    # @forgeplan-spec: AC8
    headers = _headers_for(placement_coordinator_user)

    async with await _make_rbac_client(db_session) as client:
        # Allowed: POST /cases/{id}/generate-matches
        resp = await client.post(f"/api/v1/cases/{uuid4()}/generate-matches", headers=headers)
        assert resp.status_code == 200

        # Forbidden: POST /admin/users
        resp = await client.post("/api/v1/admin/users", headers=headers)
        assert resp.status_code == 403

        # Forbidden: GET /analytics/dashboard
        resp = await client.get("/api/v1/analytics/dashboard", headers=headers)
        assert resp.status_code == 403

        # Allowed: GET /queues/operations
        resp = await client.get("/api/v1/queues/operations", headers=headers)
        assert resp.status_code == 200


# ── AC9: manager ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_manager(db_session, org, manager_user):
    """
    AC9: manager can read all data, view queues, view analytics;
    cannot manage users, edit facilities, or approve outreach.
    """
    # @forgeplan-spec: AC9
    headers = _headers_for(manager_user)

    async with await _make_rbac_client(db_session) as client:
        # Allowed: GET /analytics
        resp = await client.get("/api/v1/analytics", headers=headers)
        assert resp.status_code == 200

        # Allowed: GET /cases
        resp = await client.get("/api/v1/cases", headers=headers)
        assert resp.status_code == 200

        # Forbidden: POST /admin/users
        resp = await client.post("/api/v1/admin/users", headers=headers)
        assert resp.status_code == 403

        # Forbidden: PATCH /facilities/{id}
        resp = await client.patch(f"/api/v1/facilities/{uuid4()}", headers=headers)
        assert resp.status_code == 403

        # Forbidden: POST /outreach-actions/{id}/approve
        resp = await client.post(f"/api/v1/outreach-actions/{uuid4()}/approve", headers=headers)
        assert resp.status_code == 403


# ── AC10: admin ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin(db_session, org, admin_user):
    """
    AC10: admin has full access to all endpoints across all modules.
    """
    # @forgeplan-spec: AC10
    headers = _headers_for(admin_user)

    async with await _make_rbac_client(db_session) as client:
        # All of these must return 2xx

        resp = await client.post("/api/v1/cases", headers=headers)
        assert resp.status_code == 200, f"POST /cases: {resp.status_code}"

        resp = await client.post(f"/api/v1/cases/{uuid4()}/assessments", headers=headers)
        assert resp.status_code == 200, f"POST /assessments: {resp.status_code}"

        resp = await client.post("/api/v1/facilities", headers=headers)
        assert resp.status_code == 200, f"POST /facilities: {resp.status_code}"

        resp = await client.post("/api/v1/admin/users", headers=headers)
        assert resp.status_code == 200, f"POST /admin/users: {resp.status_code}"

        resp = await client.get("/api/v1/analytics", headers=headers)
        assert resp.status_code == 200, f"GET /analytics: {resp.status_code}"

        resp = await client.get("/api/v1/analytics/dashboard", headers=headers)
        assert resp.status_code == 200, f"GET /analytics/dashboard: {resp.status_code}"

        resp = await client.get("/api/v1/queues/operations", headers=headers)
        assert resp.status_code == 200, f"GET /queues/operations: {resp.status_code}"


# ── AC11: read_only ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_read_only(db_session, org, read_only_user):
    """
    AC11: read_only can GET cases/facilities/clinical.
    All analytics GETs and admin GETs return 403.
    All POST/PATCH/DELETE return 403 without executing handler logic.
    """
    # @forgeplan-spec: AC11
    headers = _headers_for(read_only_user)

    async with await _make_rbac_client(db_session) as client:
        # Allowed: GET /cases
        resp = await client.get("/api/v1/cases", headers=headers)
        assert resp.status_code == 200, f"GET /cases: {resp.status_code}"

        # Allowed: GET /facilities
        resp = await client.get("/api/v1/facilities", headers=headers)
        assert resp.status_code == 200, f"GET /facilities: {resp.status_code}"

        # Forbidden: GET /queues/operations (read_only not in allowed roles)
        resp = await client.get("/api/v1/queues/operations", headers=headers)
        assert resp.status_code == 403, f"GET /queues/operations: {resp.status_code}"

        # Forbidden: GET /analytics/dashboard
        resp = await client.get("/api/v1/analytics/dashboard", headers=headers)
        assert resp.status_code == 403, f"GET /analytics/dashboard: {resp.status_code}"

        # Forbidden: POST /cases (mutating + read_only)
        resp = await client.post("/api/v1/cases", headers=headers)
        assert resp.status_code == 403, f"POST /cases: {resp.status_code}"

        # Forbidden: PATCH /cases/{id}
        resp = await client.patch(f"/api/v1/cases/{uuid4()}", headers=headers)
        assert resp.status_code == 403, f"PATCH /cases: {resp.status_code}"

        # Forbidden: DELETE /facilities/{id}
        resp = await client.delete(f"/api/v1/facilities/{uuid4()}", headers=headers)
        assert resp.status_code == 403, f"DELETE /facilities: {resp.status_code}"


@pytest.mark.asyncio
async def test_read_only_handler_never_called(db_session, org, read_only_user):
    """
    AC11: For POST/PATCH/DELETE from read_only, the handler body must never execute.
    Verify using a mock counter — if handler runs, counter increments.
    """
    # @forgeplan-spec: AC11
    from fastapi import Depends

    from placementops.modules.auth.dependencies import require_role, require_write_permission

    handler_call_count = {"n": 0}

    app = make_rbac_app(db_session)

    # Add an instrumented POST endpoint to count handler invocations
    @app.post(
        "/api/v1/test/create",
        dependencies=[require_write_permission, require_role("admin", "intake_staff")],
    )
    async def counted_create():
        handler_call_count["n"] += 1
        return {"ok": True}

    headers = _headers_for(read_only_user)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post("/api/v1/test/create", headers=headers)

    assert resp.status_code == 403
    assert handler_call_count["n"] == 0, (
        "Handler body was called for read_only role — require_write_permission did not intercept"
    )


# ── AC12: role_key from DB row ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_role_from_db_row_not_jwt_claim(db_session, org):
    """
    AC12: Permission checks use AuthContext.role_key from the User DB row,
    not raw JWT claims.

    Scenario: user has role_key='admin' in JWT but 'read_only' in DB.
    A POST request should return 403 (read_only from DB), not 200 (admin from JWT).
    """
    # @forgeplan-spec: AC12
    from placementops.core.models import User

    user_id = uuid4()
    # DB row has role_key='read_only'
    user = User(
        id=str(user_id),
        organization_id=str(TEST_ORG_ID),
        email=f"demoted_{str(user_id)[:8]}@example.com",
        full_name="Demoted User",
        role_key="read_only",  # DB says read_only
        status="active",
    )
    db_session.add(user)
    await db_session.commit()

    # JWT claims role_key='admin' (stale claim — user was demoted)
    stale_token = make_jwt(user_id=user_id, org_id=TEST_ORG_ID, role_key="admin")
    headers = {"Authorization": f"Bearer {stale_token}"}

    async with await _make_rbac_client(db_session) as client:
        # POST /cases — intake_staff and admin allowed, but DB says read_only
        resp = await client.post("/api/v1/cases", headers=headers)
        # Should be 403 (read_only cannot POST, even if JWT claims admin)
        assert resp.status_code == 403, (
            f"Expected 403 (DB role=read_only overrides JWT role=admin), "
            f"got {resp.status_code}: {resp.text}"
        )


# ── RolePermissions mapping ───────────────────────────────────────────────────

def test_role_permissions_mapping_has_all_roles():
    """AC12: RolePermissions exported dict has all 6 canonical role keys."""
    from placementops.modules.auth.dependencies import RolePermissions

    expected_roles = {
        "admin",
        "intake_staff",
        "clinical_reviewer",
        "placement_coordinator",
        "manager",
        "read_only",
    }
    assert set(RolePermissions.keys()) == expected_roles


def test_admin_has_full_access():
    """AC10: admin role has the broadest permission set."""
    from placementops.modules.auth.dependencies import RolePermissions

    admin_perms = RolePermissions["admin"]
    # Admin should include analytics and admin actions
    assert "analytics:dashboard" in admin_perms
    assert "admin:users" in admin_perms
    assert "cases:create" in admin_perms


def test_read_only_has_minimal_permissions():
    """AC11: read_only has only read permissions — no create/update/delete/analytics."""
    from placementops.modules.auth.dependencies import RolePermissions

    read_only_perms = RolePermissions["read_only"]
    # Exact permission set — no more, no less
    expected_read_only_perms = frozenset(["cases:read", "facilities:read", "assessments:read"])
    assert read_only_perms == expected_read_only_perms, (
        f"read_only permissions mismatch.\n"
        f"  Extra:   {read_only_perms - expected_read_only_perms}\n"
        f"  Missing: {expected_read_only_perms - read_only_perms}"
    )
