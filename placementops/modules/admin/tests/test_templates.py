# @forgeplan-node: admin-surfaces
# @forgeplan-spec: AC4, AC5, AC6
"""
Tests for OutreachTemplate management endpoints.

Covers: AC4 (list templates — all roles), AC5 (create template), AC6 (update template + cross-org 404)
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import select

from placementops.core.models import AuditEvent, OutreachTemplate
from placementops.modules.admin.tests.conftest import auth_headers

os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret-key-minimum-32-chars-long")

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# AC4: GET /api/v1/templates/outreach — all authenticated roles
# ---------------------------------------------------------------------------


async def test_list_templates_admin_returns_200(
    client, seed_org, seed_admin_user, seed_template
):
    """AC4: admin can list templates."""
    headers = auth_headers(
        seed_admin_user["user_id"], seed_admin_user["org_id"], "admin"
    )
    resp = await client.get("/api/v1/templates/outreach", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] >= 1
    assert any(t["id"] == seed_template["template_id"] for t in body["items"])


async def test_list_templates_manager_returns_200(
    client, seed_org, seed_manager_user, seed_template
):
    """AC4: manager can list templates."""
    headers = auth_headers(
        seed_manager_user["user_id"], seed_manager_user["org_id"], "manager"
    )
    resp = await client.get("/api/v1/templates/outreach", headers=headers)
    assert resp.status_code == 200


async def test_list_templates_coordinator_returns_200(
    client, seed_org, seed_coordinator_user, seed_template
):
    """AC4: placement_coordinator can list templates."""
    headers = auth_headers(
        seed_coordinator_user["user_id"], seed_coordinator_user["org_id"], "placement_coordinator"
    )
    resp = await client.get("/api/v1/templates/outreach", headers=headers)
    assert resp.status_code == 200


async def test_list_templates_intake_staff_returns_200(
    client, seed_org, seed_intake_user, seed_template
):
    """AC4: intake_staff can list templates."""
    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )
    resp = await client.get("/api/v1/templates/outreach", headers=headers)
    assert resp.status_code == 200


async def test_list_templates_clinical_reviewer_returns_200(
    client, seed_org, seed_clinical_reviewer, seed_template
):
    """AC4: clinical_reviewer can list templates."""
    headers = auth_headers(
        seed_clinical_reviewer["user_id"], seed_clinical_reviewer["org_id"], "clinical_reviewer"
    )
    resp = await client.get("/api/v1/templates/outreach", headers=headers)
    assert resp.status_code == 200


async def test_list_templates_read_only_returns_200(
    client, seed_org, seed_read_only_user, seed_template
):
    """AC4: read_only can list templates."""
    headers = auth_headers(
        seed_read_only_user["user_id"], seed_read_only_user["org_id"], "read_only"
    )
    resp = await client.get("/api/v1/templates/outreach", headers=headers)
    assert resp.status_code == 200


async def test_list_templates_org_scoped(
    client, db_session, seed_org, seed_other_org, seed_admin_user, seed_template, seed_other_org_template
):
    """AC4: no cross-org templates returned."""
    headers = auth_headers(seed_admin_user["user_id"], seed_org, "admin")
    resp = await client.get("/api/v1/templates/outreach", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    returned_ids = [t["id"] for t in body["items"]]
    assert seed_other_org_template not in returned_ids
    assert seed_template["template_id"] in returned_ids


async def test_list_templates_unauthenticated_returns_401(client):
    """AC4: no auth → 401."""
    resp = await client.get("/api/v1/templates/outreach")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# AC5: POST /api/v1/templates/outreach — create template, admin only
# ---------------------------------------------------------------------------


async def test_create_template_admin_returns_201(
    client, db_session, seed_org, seed_admin_user
):
    """AC5: admin creates template → 201, row persisted with correct org and created_by."""
    headers = auth_headers(
        seed_admin_user["user_id"], seed_admin_user["org_id"], "admin"
    )
    payload = {
        "template_name": "New Email Template",
        "template_type": "email",
        "subject_template": "Hello {patient_name}",
        "body_template": "Dear {patient_name}, your coordinator is {coordinator_name}.",
        "allowed_variables": ["patient_name", "coordinator_name"],
        "is_active": True,
    }
    resp = await client.post("/api/v1/templates/outreach", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["template_name"] == "New Email Template"
    assert body["organization_id"] == seed_org
    assert body["created_by_user_id"] == seed_admin_user["user_id"]

    # Verify in DB
    result = await db_session.execute(
        select(OutreachTemplate).where(OutreachTemplate.id == body["id"])
    )
    t = result.scalar_one()
    assert t.organization_id == seed_org


async def test_create_template_writes_audit_event(
    client, db_session, seed_org, seed_admin_user
):
    """AC5: creating template writes AuditEvent(event_type=template_created)."""
    headers = auth_headers(
        seed_admin_user["user_id"], seed_admin_user["org_id"], "admin"
    )
    payload = {
        "template_name": "Audit Template",
        "template_type": "task",
        "body_template": "Task for {facility_name}",
        "allowed_variables": ["facility_name"],
    }
    resp = await client.post("/api/v1/templates/outreach", headers=headers, json=payload)
    assert resp.status_code == 201
    template_id = resp.json()["id"]

    result = await db_session.execute(
        select(AuditEvent).where(
            AuditEvent.entity_type == "outreach_template",
            AuditEvent.entity_id == template_id,
            AuditEvent.event_type == "template_created",
        )
    )
    audit = result.scalar_one()
    assert audit.actor_user_id == seed_admin_user["user_id"]
    assert audit.old_value_json is None
    assert audit.new_value_json is not None


async def test_create_template_invalid_variable_returns_400(
    client, seed_org, seed_admin_user
):
    """AC5: allowed_variables outside safe allowlist → 400."""
    headers = auth_headers(
        seed_admin_user["user_id"], seed_admin_user["org_id"], "admin"
    )
    payload = {
        "template_name": "Bad Vars",
        "template_type": "email",
        "body_template": "Hello {patient_name} and {__class__}",
        "allowed_variables": ["patient_name", "__class__"],
    }
    resp = await client.post("/api/v1/templates/outreach", headers=headers, json=payload)
    assert resp.status_code == 400
    assert "Invalid template variables" in resp.json()["detail"]


async def test_create_template_invalid_type_returns_400(
    client, seed_org, seed_admin_user
):
    """AC5: invalid template_type → 400."""
    headers = auth_headers(
        seed_admin_user["user_id"], seed_admin_user["org_id"], "admin"
    )
    payload = {
        "template_name": "Bad Type",
        "template_type": "sms",
        "body_template": "Hello",
        "allowed_variables": [],
    }
    resp = await client.post("/api/v1/templates/outreach", headers=headers, json=payload)
    assert resp.status_code == 400


async def test_create_template_empty_name_returns_400(
    client, seed_org, seed_admin_user
):
    """AC5: empty template_name → 400."""
    headers = auth_headers(
        seed_admin_user["user_id"], seed_admin_user["org_id"], "admin"
    )
    payload = {
        "template_name": "   ",
        "template_type": "email",
        "body_template": "Valid body",
        "allowed_variables": [],
    }
    resp = await client.post("/api/v1/templates/outreach", headers=headers, json=payload)
    assert resp.status_code == 400


async def test_create_template_coordinator_returns_403(
    client, seed_org, seed_coordinator_user
):
    """AC5: placement_coordinator → 403."""
    headers = auth_headers(
        seed_coordinator_user["user_id"], seed_coordinator_user["org_id"], "placement_coordinator"
    )
    payload = {
        "template_name": "Forbidden Template",
        "template_type": "email",
        "body_template": "Hello",
        "allowed_variables": [],
    }
    resp = await client.post("/api/v1/templates/outreach", headers=headers, json=payload)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# AC6: PATCH /api/v1/templates/outreach/{template_id} — update, cross-org 404
# ---------------------------------------------------------------------------


async def test_update_template_admin_returns_200(
    client, db_session, seed_org, seed_admin_user, seed_template
):
    """AC6: admin updates template name and body → 200 and persisted."""
    headers = auth_headers(
        seed_admin_user["user_id"], seed_admin_user["org_id"], "admin"
    )
    resp = await client.patch(
        f"/api/v1/templates/outreach/{seed_template['template_id']}",
        headers=headers,
        json={
            "template_name": "Updated Template Name",
            "body_template": "Updated body for {patient_name}",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["template_name"] == "Updated Template Name"
    assert body["body_template"] == "Updated body for {patient_name}"

    # Verify persisted
    result = await db_session.execute(
        select(OutreachTemplate).where(OutreachTemplate.id == seed_template["template_id"])
    )
    t = result.scalar_one()
    assert t.template_name == "Updated Template Name"


async def test_update_template_writes_audit_event(
    client, db_session, seed_org, seed_admin_user, seed_template
):
    """AC6: updating template writes AuditEvent(event_type=template_updated)."""
    headers = auth_headers(
        seed_admin_user["user_id"], seed_admin_user["org_id"], "admin"
    )
    resp = await client.patch(
        f"/api/v1/templates/outreach/{seed_template['template_id']}",
        headers=headers,
        json={"is_active": False},
    )
    assert resp.status_code == 200

    result = await db_session.execute(
        select(AuditEvent).where(
            AuditEvent.entity_type == "outreach_template",
            AuditEvent.entity_id == seed_template["template_id"],
            AuditEvent.event_type == "template_updated",
        )
    )
    audit = result.scalar_one()
    assert audit.actor_user_id == seed_admin_user["user_id"]
    assert audit.old_value_json["is_active"] is True
    assert audit.new_value_json["is_active"] is False


async def test_update_template_cross_org_returns_404(
    client, seed_org, seed_admin_user, seed_other_org_template
):
    """AC6: cross-org template_id → 404 (not 403)."""
    headers = auth_headers(
        seed_admin_user["user_id"], seed_admin_user["org_id"], "admin"
    )
    resp = await client.patch(
        f"/api/v1/templates/outreach/{seed_other_org_template}",
        headers=headers,
        json={"template_name": "Attempted Hijack"},
    )
    assert resp.status_code == 404


async def test_update_template_nonexistent_returns_404(
    client, seed_org, seed_admin_user
):
    """AC6: non-existent template_id → 404."""
    headers = auth_headers(
        seed_admin_user["user_id"], seed_admin_user["org_id"], "admin"
    )
    fake_id = str(uuid.uuid4())
    resp = await client.patch(
        f"/api/v1/templates/outreach/{fake_id}",
        headers=headers,
        json={"template_name": "Ghost"},
    )
    assert resp.status_code == 404


async def test_update_template_invalid_variable_returns_400(
    client, seed_org, seed_admin_user, seed_template
):
    """AC6: updating with unsafe variable → 400."""
    headers = auth_headers(
        seed_admin_user["user_id"], seed_admin_user["org_id"], "admin"
    )
    resp = await client.patch(
        f"/api/v1/templates/outreach/{seed_template['template_id']}",
        headers=headers,
        json={"allowed_variables": ["patient_name", "sql_injection"]},
    )
    assert resp.status_code == 400


async def test_update_template_manager_returns_403(
    client, seed_org, seed_manager_user, seed_template
):
    """AC6: manager → 403."""
    headers = auth_headers(
        seed_manager_user["user_id"], seed_manager_user["org_id"], "manager"
    )
    resp = await client.patch(
        f"/api/v1/templates/outreach/{seed_template['template_id']}",
        headers=headers,
        json={"template_name": "Manager Attempt"},
    )
    assert resp.status_code == 403
