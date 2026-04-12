# @forgeplan-node: admin-surfaces
# @forgeplan-spec: AC7, AC8, AC9, AC10
"""
Tests for import monitoring, org settings, and reference data endpoints.

Covers: AC7 (list imports), AC8 (get import detail + cross-org 404),
        AC9 (org settings GET/PATCH), AC10 (reference data — all roles)
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import select

from placementops.core.models import AuditEvent, ImportJob
from placementops.core.models.reference_tables import Organization
from placementops.modules.admin.tests.conftest import auth_headers

os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret-key-minimum-32-chars-long")

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# AC7: GET /api/v1/imports — paginated import list, admin only
# ---------------------------------------------------------------------------


async def test_list_imports_returns_seeded_jobs(
    client, db_session, seed_org, seed_admin_user, seed_import_job
):
    """AC7: admin GET /imports returns both seeded jobs with status and counts."""
    # Seed a second job
    second_job_id = str(uuid.uuid4())
    second_job = ImportJob(
        id=second_job_id,
        organization_id=seed_org,
        created_by_user_id=seed_admin_user["user_id"],
        file_name="second_import.xlsx",
        file_size_bytes=2048,
        status="failed",
        total_rows=5,
        created_count=0,
        updated_count=0,
        failed_count=5,
    )
    db_session.add(second_job)
    await db_session.commit()

    headers = auth_headers(seed_admin_user["user_id"], seed_org, "admin")
    resp = await client.get("/api/v1/imports", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2

    # Both jobs must have status and counts
    for item in body["items"]:
        assert "status" in item
        assert "created_count" in item
        assert "updated_count" in item
        assert "failed_count" in item


async def test_list_imports_org_scoped(
    client, db_session, seed_org, seed_other_org, seed_admin_user, seed_import_job, seed_other_org_import
):
    """AC7: import from other org does not appear in list."""
    headers = auth_headers(seed_admin_user["user_id"], seed_org, "admin")
    resp = await client.get("/api/v1/imports", headers=headers)
    assert resp.status_code == 200
    returned_ids = [j["id"] for j in resp.json()["items"]]
    assert seed_other_org_import not in returned_ids
    assert seed_import_job["job_id"] in returned_ids


async def test_list_imports_pagination(
    client, db_session, seed_org, seed_admin_user, seed_import_job
):
    """AC7: pagination params work."""
    # Add more jobs
    for i in range(3):
        job = ImportJob(
            id=str(uuid.uuid4()),
            organization_id=seed_org,
            created_by_user_id=seed_admin_user["user_id"],
            file_name=f"extra{i}.csv",
            file_size_bytes=100,
            status="complete",
        )
        db_session.add(job)
    await db_session.commit()

    headers = auth_headers(seed_admin_user["user_id"], seed_org, "admin")
    resp = await client.get("/api/v1/imports?page=1&page_size=2", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["page"] == 1
    assert body["page_size"] == 2


async def test_list_imports_non_admin_returns_403(
    client, seed_org, seed_manager_user
):
    """AC7: non-admin → 403."""
    headers = auth_headers(
        seed_manager_user["user_id"], seed_manager_user["org_id"], "manager"
    )
    resp = await client.get("/api/v1/imports", headers=headers)
    assert resp.status_code == 403


async def test_no_post_imports_route_in_admin_module(
    client, seed_org, seed_admin_user
):
    """AC7: POST /imports must not exist in admin-surfaces router (intake-module owns it)."""
    headers = auth_headers(seed_admin_user["user_id"], seed_org, "admin")
    resp = await client.post(
        "/api/v1/imports",
        headers=headers,
        content=b"some data",
    )
    # 405 Method Not Allowed or 404 Not Found — either is correct; 201/202 is NOT
    assert resp.status_code in (404, 405, 415, 422)


# ---------------------------------------------------------------------------
# AC8: GET /api/v1/imports/{import_id} — full detail, cross-org 404
# ---------------------------------------------------------------------------


async def test_get_import_returns_full_detail(
    client, seed_org, seed_admin_user, seed_import_job
):
    """AC8: GET /imports/{id} returns full ImportJob including error_detail_json."""
    headers = auth_headers(seed_admin_user["user_id"], seed_org, "admin")
    resp = await client.get(
        f"/api/v1/imports/{seed_import_job['job_id']}", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == seed_import_job["job_id"]
    assert body["error_detail_json"] is not None
    assert "errors" in body["error_detail_json"]
    assert body["status"] == "complete"
    assert body["created_count"] == 8
    assert body["failed_count"] == 1


async def test_get_import_cross_org_returns_404(
    client, seed_org, seed_admin_user, seed_other_org_import
):
    """AC8: cross-org import_id → 404 (not 403)."""
    headers = auth_headers(seed_admin_user["user_id"], seed_org, "admin")
    resp = await client.get(f"/api/v1/imports/{seed_other_org_import}", headers=headers)
    assert resp.status_code == 404


async def test_get_import_not_found_returns_404(
    client, seed_org, seed_admin_user
):
    """AC8: non-existent import_id → 404."""
    headers = auth_headers(seed_admin_user["user_id"], seed_org, "admin")
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/imports/{fake_id}", headers=headers)
    assert resp.status_code == 404


async def test_get_import_non_admin_returns_403(
    client, seed_org, seed_manager_user, seed_import_job
):
    """AC8: non-admin → 403."""
    headers = auth_headers(
        seed_manager_user["user_id"], seed_manager_user["org_id"], "manager"
    )
    resp = await client.get(
        f"/api/v1/imports/{seed_import_job['job_id']}", headers=headers
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# AC9: GET+PATCH /api/v1/admin/organization
# ---------------------------------------------------------------------------


async def test_get_org_settings_admin_returns_200(
    client, seed_org, seed_admin_user
):
    """AC9: admin GET /admin/organization → 200 with correct org."""
    headers = auth_headers(seed_admin_user["user_id"], seed_org, "admin")
    resp = await client.get("/api/v1/admin/organization", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == seed_org
    assert body["org_name"] == "Test Org"


async def test_patch_org_settings_updates_name(
    client, db_session, seed_org, seed_admin_user
):
    """AC9: admin PATCH /admin/organization updates org_name, persists change."""
    headers = auth_headers(seed_admin_user["user_id"], seed_org, "admin")
    resp = await client.patch(
        "/api/v1/admin/organization",
        headers=headers,
        json={"org_name": "Updated Org Name"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["org_name"] == "Updated Org Name"

    # Verify persisted
    result = await db_session.execute(
        select(Organization).where(Organization.id == seed_org)
    )
    org = result.scalar_one()
    assert org.name == "Updated Org Name"


async def test_patch_org_settings_writes_audit_event(
    client, db_session, seed_org, seed_admin_user
):
    """AC9: PATCH org settings writes AuditEvent(event_type=org_settings_updated)."""
    headers = auth_headers(seed_admin_user["user_id"], seed_org, "admin")
    resp = await client.patch(
        "/api/v1/admin/organization",
        headers=headers,
        json={"org_name": "Audit Test Org"},
    )
    assert resp.status_code == 200

    result = await db_session.execute(
        select(AuditEvent).where(
            AuditEvent.entity_type == "organization",
            AuditEvent.entity_id == seed_org,
            AuditEvent.event_type == "org_settings_updated",
        )
    )
    audit = result.scalar_one()
    assert audit.actor_user_id == seed_admin_user["user_id"]
    assert audit.organization_id == seed_org
    assert audit.old_value_json is not None
    assert audit.new_value_json["org_name"] == "Audit Test Org"


async def test_patch_org_settings_with_settings_json(
    client, seed_org, seed_admin_user
):
    """AC9: settings_json is accepted in PATCH and echoed back."""
    headers = auth_headers(seed_admin_user["user_id"], seed_org, "admin")
    resp = await client.patch(
        "/api/v1/admin/organization",
        headers=headers,
        json={"settings_json": {"sla_hours": 24, "timezone": "America/Chicago"}},
    )
    assert resp.status_code == 200
    body = resp.json()
    # Phase 1: settings_json is echoed back (not stored in DB)
    assert body["settings_json"] == {"sla_hours": 24, "timezone": "America/Chicago"}


async def test_get_org_settings_non_admin_returns_403(
    client, seed_org, seed_manager_user
):
    """AC9: non-admin GET → 403."""
    headers = auth_headers(
        seed_manager_user["user_id"], seed_manager_user["org_id"], "manager"
    )
    resp = await client.get("/api/v1/admin/organization", headers=headers)
    assert resp.status_code == 403


async def test_patch_org_settings_non_admin_returns_403(
    client, seed_org, seed_manager_user
):
    """AC9: non-admin PATCH → 403."""
    headers = auth_headers(
        seed_manager_user["user_id"], seed_manager_user["org_id"], "manager"
    )
    resp = await client.patch(
        "/api/v1/admin/organization",
        headers=headers,
        json={"org_name": "Forbidden Update"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# AC10: Reference data endpoints — all authenticated roles
# ---------------------------------------------------------------------------


async def test_list_hospitals_all_roles_return_200(
    client, seed_org, seed_admin_user, seed_manager_user, seed_coordinator_user,
    seed_intake_user, seed_clinical_reviewer, seed_read_only_user,
    seed_hospital
):
    """AC10: all 6 roles can list hospitals → 200."""
    all_users = [
        seed_admin_user,
        seed_manager_user,
        seed_coordinator_user,
        seed_intake_user,
        seed_clinical_reviewer,
        seed_read_only_user,
    ]
    for user in all_users:
        headers = auth_headers(user["user_id"], user["org_id"], user["role_key"])
        resp = await client.get("/api/v1/reference/hospitals", headers=headers)
        assert resp.status_code == 200, f"Failed for role {user['role_key']}: {resp.text}"


async def test_list_hospitals_returns_org_scoped(
    client, db_session, seed_org, seed_other_org, seed_admin_user, seed_hospital
):
    """AC10: hospital records are scoped to caller's org."""
    # Add hospital in other org
    from placementops.core.models import HospitalReference
    other_h_id = str(uuid.uuid4())
    other_h = HospitalReference(
        id=other_h_id,
        organization_id=seed_other_org,
        hospital_name="Other Hospital",
    )
    db_session.add(other_h)
    await db_session.commit()

    headers = auth_headers(seed_admin_user["user_id"], seed_org, "admin")
    resp = await client.get("/api/v1/reference/hospitals", headers=headers)
    assert resp.status_code == 200
    returned_ids = [h["id"] for h in resp.json()]
    assert seed_hospital in returned_ids
    assert other_h_id not in returned_ids


async def test_list_hospitals_non_empty(
    client, seed_org, seed_admin_user, seed_hospital
):
    """AC10: hospital list is non-empty after seeding."""
    headers = auth_headers(seed_admin_user["user_id"], seed_org, "admin")
    resp = await client.get("/api/v1/reference/hospitals", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


async def test_list_decline_reasons_all_roles_return_200(
    client, seed_org, seed_admin_user, seed_manager_user, seed_coordinator_user,
    seed_intake_user, seed_clinical_reviewer, seed_read_only_user,
    seed_decline_reason
):
    """AC10: all 6 roles can list decline reasons → 200."""
    all_users = [
        seed_admin_user,
        seed_manager_user,
        seed_coordinator_user,
        seed_intake_user,
        seed_clinical_reviewer,
        seed_read_only_user,
    ]
    for user in all_users:
        headers = auth_headers(user["user_id"], user["org_id"], user["role_key"])
        resp = await client.get("/api/v1/reference/decline-reasons", headers=headers)
        assert resp.status_code == 200, f"Failed for role {user['role_key']}"


async def test_list_decline_reasons_contains_seeded_code(
    client, seed_org, seed_admin_user, seed_decline_reason
):
    """AC10: seeded decline reason code appears in response."""
    headers = auth_headers(seed_admin_user["user_id"], seed_org, "admin")
    resp = await client.get("/api/v1/reference/decline-reasons", headers=headers)
    assert resp.status_code == 200
    codes = [r["code"] for r in resp.json()]
    assert "no_beds" in codes


async def test_list_payers_all_roles_return_200(
    client, seed_org, seed_admin_user, seed_manager_user, seed_coordinator_user,
    seed_intake_user, seed_clinical_reviewer, seed_read_only_user,
    seed_payer
):
    """AC10: all 6 roles can list payers → 200."""
    all_users = [
        seed_admin_user,
        seed_manager_user,
        seed_coordinator_user,
        seed_intake_user,
        seed_clinical_reviewer,
        seed_read_only_user,
    ]
    for user in all_users:
        headers = auth_headers(user["user_id"], user["org_id"], user["role_key"])
        resp = await client.get("/api/v1/reference/payers", headers=headers)
        assert resp.status_code == 200, f"Failed for role {user['role_key']}"


async def test_list_payers_contains_seeded_entry(
    client, seed_org, seed_admin_user, seed_payer
):
    """AC10: seeded payer appears in response."""
    headers = auth_headers(seed_admin_user["user_id"], seed_org, "admin")
    resp = await client.get("/api/v1/reference/payers", headers=headers)
    assert resp.status_code == 200
    payer_ids = [p["id"] for p in resp.json()]
    assert seed_payer in payer_ids


async def test_reference_endpoints_unauthenticated_return_401(client):
    """AC10: no auth → 401 on all reference endpoints."""
    for endpoint in [
        "/api/v1/reference/hospitals",
        "/api/v1/reference/decline-reasons",
        "/api/v1/reference/payers",
    ]:
        resp = await client.get(endpoint)
        assert resp.status_code == 401, f"Expected 401 for {endpoint}, got {resp.status_code}"
