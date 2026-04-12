# @forgeplan-node: admin-surfaces
# @forgeplan-spec: AC1, AC2, AC3, AC11
"""
Tests for user management endpoints.

Covers: AC1 (list users), AC2 (create user), AC3 (update user / last-admin guard), AC11 (audit events)
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import select

from placementops.core.models import AuditEvent, User
from placementops.modules.admin.tests.conftest import auth_headers

os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret-key-minimum-32-chars-long")

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# AC1: GET /api/v1/admin/users — admin only, org-scoped
# ---------------------------------------------------------------------------


async def test_list_users_admin_returns_200_with_users(
    client, db_session, seed_org, seed_admin_user, seed_manager_user
):
    """AC1: admin can list users, all results are in caller's org."""
    headers = auth_headers(
        seed_admin_user["user_id"], seed_admin_user["org_id"], "admin"
    )
    resp = await client.get("/api/v1/admin/users", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "items" in body
    assert "total" in body
    assert body["total"] >= 2  # admin + manager seeded
    # All returned users must belong to the caller's org
    for user in body["items"]:
        assert user["organization_id"] == seed_org


async def test_list_users_org_scoped(
    client, db_session, seed_org, seed_other_org, seed_admin_user
):
    """AC1: users from other org never appear in results."""
    # Create user in other org
    other_user_id = str(uuid.uuid4())
    other_user = User(
        id=other_user_id,
        organization_id=seed_other_org,
        email="other@other.com",
        full_name="Other User",
        role_key="manager",
        status="active",
    )
    db_session.add(other_user)
    await db_session.commit()

    headers = auth_headers(seed_admin_user["user_id"], seed_org, "admin")
    resp = await client.get("/api/v1/admin/users", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    returned_ids = [u["id"] for u in body["items"]]
    assert other_user_id not in returned_ids


async def test_list_users_pagination(
    client, db_session, seed_org, seed_admin_user
):
    """AC1: page_size parameter limits results returned."""
    # Seed extra users
    for i in range(5):
        user = User(
            id=str(uuid.uuid4()),
            organization_id=seed_org,
            email=f"extra{i}@test.com",
            full_name=f"Extra User {i}",
            role_key="read_only",
            status="active",
        )
        db_session.add(user)
    await db_session.commit()

    headers = auth_headers(seed_admin_user["user_id"], seed_org, "admin")
    resp = await client.get("/api/v1/admin/users?page=1&page_size=2", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["page"] == 1
    assert body["page_size"] == 2


async def test_list_users_manager_returns_403(
    client, seed_org, seed_manager_user
):
    """AC1: manager role gets 403."""
    headers = auth_headers(
        seed_manager_user["user_id"], seed_manager_user["org_id"], "manager"
    )
    resp = await client.get("/api/v1/admin/users", headers=headers)
    assert resp.status_code == 403


async def test_list_users_coordinator_returns_403(
    client, seed_org, seed_coordinator_user
):
    """AC1: placement_coordinator gets 403."""
    headers = auth_headers(
        seed_coordinator_user["user_id"], seed_coordinator_user["org_id"], "placement_coordinator"
    )
    resp = await client.get("/api/v1/admin/users", headers=headers)
    assert resp.status_code == 403


async def test_list_users_intake_staff_returns_403(
    client, seed_org, seed_intake_user
):
    """AC1: intake_staff gets 403."""
    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )
    resp = await client.get("/api/v1/admin/users", headers=headers)
    assert resp.status_code == 403


async def test_list_users_clinical_reviewer_returns_403(
    client, seed_org, seed_clinical_reviewer
):
    """AC1: clinical_reviewer gets 403."""
    headers = auth_headers(
        seed_clinical_reviewer["user_id"], seed_clinical_reviewer["org_id"], "clinical_reviewer"
    )
    resp = await client.get("/api/v1/admin/users", headers=headers)
    assert resp.status_code == 403


async def test_list_users_read_only_returns_403(
    client, seed_org, seed_read_only_user
):
    """AC1: read_only gets 403."""
    headers = auth_headers(
        seed_read_only_user["user_id"], seed_read_only_user["org_id"], "read_only"
    )
    resp = await client.get("/api/v1/admin/users", headers=headers)
    assert resp.status_code == 403


async def test_list_users_unauthenticated_returns_401(client):
    """AC1: no auth header → 401."""
    resp = await client.get("/api/v1/admin/users")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# AC2: POST /api/v1/admin/users — create user, audit event
# ---------------------------------------------------------------------------


async def test_create_user_admin_returns_201(
    client, db_session, seed_org, seed_admin_user
):
    """AC2: admin creates user → 201, user row exists with correct fields."""
    headers = auth_headers(
        seed_admin_user["user_id"], seed_admin_user["org_id"], "admin"
    )
    payload = {
        "email": "newuser@test.com",
        "full_name": "New User",
        "role_key": "intake_staff",
    }
    resp = await client.post("/api/v1/admin/users", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["email"] == "newuser@test.com"
    assert body["full_name"] == "New User"
    assert body["role_key"] == "intake_staff"
    assert body["status"] == "active"
    assert body["organization_id"] == seed_org

    # Verify the row is in the DB
    result = await db_session.execute(select(User).where(User.id == body["id"]))
    db_user = result.scalar_one()
    assert db_user.email == "newuser@test.com"
    assert db_user.organization_id == seed_org


async def test_create_user_writes_audit_event(
    client, db_session, seed_org, seed_admin_user
):
    """AC2 + AC11: creating a user writes AuditEvent with event_type=user_created."""
    headers = auth_headers(
        seed_admin_user["user_id"], seed_admin_user["org_id"], "admin"
    )
    payload = {
        "email": "audit_user@test.com",
        "full_name": "Audit User",
        "role_key": "read_only",
    }
    resp = await client.post("/api/v1/admin/users", headers=headers, json=payload)
    assert resp.status_code == 201
    user_id = resp.json()["id"]

    # Check audit event
    result = await db_session.execute(
        select(AuditEvent).where(
            AuditEvent.entity_type == "user",
            AuditEvent.entity_id == user_id,
            AuditEvent.event_type == "user_created",
        )
    )
    audit = result.scalar_one()
    assert audit.actor_user_id == seed_admin_user["user_id"]
    assert audit.organization_id == seed_org
    assert audit.new_value_json is not None
    assert audit.new_value_json["role_key"] == "read_only"
    assert audit.old_value_json is None


async def test_create_user_duplicate_email_returns_409(
    client, seed_org, seed_admin_user
):
    """AC2: duplicate email → 409."""
    headers = auth_headers(
        seed_admin_user["user_id"], seed_admin_user["org_id"], "admin"
    )
    payload = {"email": "admin@test.com", "full_name": "Dup User", "role_key": "read_only"}
    resp = await client.post("/api/v1/admin/users", headers=headers, json=payload)
    assert resp.status_code == 409


async def test_create_user_invalid_role_key_returns_400(
    client, seed_org, seed_admin_user
):
    """AC2: invalid role_key → 400."""
    headers = auth_headers(
        seed_admin_user["user_id"], seed_admin_user["org_id"], "admin"
    )
    payload = {
        "email": "bad_role@test.com",
        "full_name": "Bad Role",
        "role_key": "superadmin",
    }
    resp = await client.post("/api/v1/admin/users", headers=headers, json=payload)
    assert resp.status_code == 400


async def test_create_user_non_admin_returns_403(
    client, seed_org, seed_manager_user
):
    """AC2: non-admin caller → 403."""
    headers = auth_headers(
        seed_manager_user["user_id"], seed_manager_user["org_id"], "manager"
    )
    payload = {
        "email": "forbidden@test.com",
        "full_name": "Forbidden",
        "role_key": "intake_staff",
    }
    resp = await client.post("/api/v1/admin/users", headers=headers, json=payload)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# AC3: PATCH /api/v1/admin/users/{user_id} — update user, last-admin guard
# ---------------------------------------------------------------------------


async def test_update_user_role_returns_200(
    client, db_session, seed_org, seed_admin_user, seed_manager_user
):
    """AC3: admin PATCHes role, assert 200 and persisted change."""
    headers = auth_headers(
        seed_admin_user["user_id"], seed_admin_user["org_id"], "admin"
    )
    resp = await client.patch(
        f"/api/v1/admin/users/{seed_manager_user['user_id']}",
        headers=headers,
        json={"role_key": "read_only"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["role_key"] == "read_only"
    assert body["id"] == seed_manager_user["user_id"]

    # Verify persisted in DB
    result = await db_session.execute(
        select(User).where(User.id == seed_manager_user["user_id"])
    )
    user = result.scalar_one()
    assert user.role_key == "read_only"


async def test_update_user_writes_audit_event(
    client, db_session, seed_org, seed_admin_user, seed_manager_user
):
    """AC3 + AC11: updating role writes AuditEvent with old_value_json and new_value_json."""
    headers = auth_headers(
        seed_admin_user["user_id"], seed_admin_user["org_id"], "admin"
    )
    resp = await client.patch(
        f"/api/v1/admin/users/{seed_manager_user['user_id']}",
        headers=headers,
        json={"role_key": "clinical_reviewer"},
    )
    assert resp.status_code == 200
    user_id = seed_manager_user["user_id"]

    result = await db_session.execute(
        select(AuditEvent).where(
            AuditEvent.entity_type == "user",
            AuditEvent.entity_id == user_id,
            AuditEvent.event_type == "user_updated",
        )
    )
    audit = result.scalar_one()
    assert audit.actor_user_id == seed_admin_user["user_id"]
    assert audit.old_value_json["role_key"] == "manager"
    assert audit.new_value_json["role_key"] == "clinical_reviewer"


async def test_update_user_status_deactivate(
    client, db_session, seed_org, seed_admin_user, seed_manager_user
):
    """AC3: admin can deactivate a non-admin user without triggering last-admin guard."""
    headers = auth_headers(
        seed_admin_user["user_id"], seed_admin_user["org_id"], "admin"
    )
    resp = await client.patch(
        f"/api/v1/admin/users/{seed_manager_user['user_id']}",
        headers=headers,
        json={"status": "inactive"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "inactive"


async def test_update_user_last_admin_deactivate_returns_400(
    client, db_session, seed_org, seed_admin_user
):
    """AC3: deactivating the ONLY active admin → 400 last-admin guard."""
    headers = auth_headers(
        seed_admin_user["user_id"], seed_admin_user["org_id"], "admin"
    )
    # seed_admin_user is the only admin — try to deactivate them
    resp = await client.patch(
        f"/api/v1/admin/users/{seed_admin_user['user_id']}",
        headers=headers,
        json={"status": "inactive"},
    )
    assert resp.status_code == 400
    assert "last active admin" in resp.json()["detail"].lower()


async def test_update_user_last_admin_role_change_returns_400(
    client, db_session, seed_org, seed_admin_user
):
    """AC3: changing role away from admin when they're the last active admin → 400."""
    headers = auth_headers(
        seed_admin_user["user_id"], seed_admin_user["org_id"], "admin"
    )
    resp = await client.patch(
        f"/api/v1/admin/users/{seed_admin_user['user_id']}",
        headers=headers,
        json={"role_key": "manager"},
    )
    assert resp.status_code == 400
    assert "last active admin" in resp.json()["detail"].lower()


async def test_update_user_two_admins_allows_deactivate(
    client, db_session, seed_org, seed_admin_user
):
    """AC3: if org has 2 active admins, deactivating one is allowed."""
    # Create a second admin
    second_admin_id = str(uuid.uuid4())
    second_admin = User(
        id=second_admin_id,
        organization_id=seed_org,
        email="admin2@test.com",
        full_name="Second Admin",
        role_key="admin",
        status="active",
    )
    db_session.add(second_admin)
    await db_session.commit()

    headers = auth_headers(
        seed_admin_user["user_id"], seed_admin_user["org_id"], "admin"
    )
    # Deactivate the second admin — this is fine (first admin still active)
    resp = await client.patch(
        f"/api/v1/admin/users/{second_admin_id}",
        headers=headers,
        json={"status": "inactive"},
    )
    assert resp.status_code == 200


async def test_update_user_non_admin_returns_403(
    client, seed_org, seed_manager_user
):
    """AC3: non-admin caller → 403."""
    headers = auth_headers(
        seed_manager_user["user_id"], seed_manager_user["org_id"], "manager"
    )
    resp = await client.patch(
        f"/api/v1/admin/users/{seed_manager_user['user_id']}",
        headers=headers,
        json={"role_key": "admin"},
    )
    assert resp.status_code == 403


async def test_update_user_not_found_returns_404(
    client, seed_org, seed_admin_user
):
    """AC3: updating non-existent user → 404."""
    headers = auth_headers(
        seed_admin_user["user_id"], seed_admin_user["org_id"], "admin"
    )
    fake_id = str(uuid.uuid4())
    resp = await client.patch(
        f"/api/v1/admin/users/{fake_id}",
        headers=headers,
        json={"role_key": "manager"},
    )
    assert resp.status_code == 404


async def test_update_user_invalid_status_returns_400(
    client, seed_org, seed_admin_user, seed_manager_user
):
    """AC3: invalid status value → 400."""
    headers = auth_headers(
        seed_admin_user["user_id"], seed_admin_user["org_id"], "admin"
    )
    resp = await client.patch(
        f"/api/v1/admin/users/{seed_manager_user['user_id']}",
        headers=headers,
        json={"status": "suspended"},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# AC11: Audit event completeness
# ---------------------------------------------------------------------------


async def test_audit_event_has_all_required_fields(
    client, db_session, seed_org, seed_admin_user, seed_manager_user
):
    """AC11: AuditEvent row must contain actor_user_id, entity_type, entity_id, event_type, old/new values."""
    headers = auth_headers(
        seed_admin_user["user_id"], seed_admin_user["org_id"], "admin"
    )
    resp = await client.patch(
        f"/api/v1/admin/users/{seed_manager_user['user_id']}",
        headers=headers,
        json={"role_key": "intake_staff"},
    )
    assert resp.status_code == 200

    result = await db_session.execute(
        select(AuditEvent).where(
            AuditEvent.entity_type == "user",
            AuditEvent.entity_id == seed_manager_user["user_id"],
            AuditEvent.event_type == "user_updated",
        )
    )
    audit = result.scalar_one()

    # AC11 requirements
    assert audit.actor_user_id == seed_admin_user["user_id"]
    assert audit.entity_type == "user"
    assert audit.entity_id == seed_manager_user["user_id"]
    assert audit.event_type == "user_updated"
    assert audit.old_value_json is not None
    assert audit.new_value_json is not None
    assert audit.old_value_json["role_key"] == "manager"
    assert audit.new_value_json["role_key"] == "intake_staff"
    assert audit.organization_id == seed_org
