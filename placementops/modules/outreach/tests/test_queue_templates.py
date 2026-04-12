# @forgeplan-node: outreach-module
# @forgeplan-spec: AC9
# @forgeplan-spec: AC10
"""
Tests for outreach queue (AC9) and template listing (AC10).

AC9  — Outreach queue returns cross-case actions filterable by status
AC10 — Template listing is read-only (GET allowed, POST/PATCH/DELETE → 405)
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.auth import AuthContext
from placementops.modules.outreach import service
from placementops.modules.outreach.tests.conftest import (
    TEST_ORG_ID,
    TEST_ORG2_ID,
    auth_headers,
    make_auth_ctx,
    make_id,
    seed_case,
    seed_org,
    seed_outreach_action,
    seed_template,
    seed_user,
)


# ---------------------------------------------------------------------------
# AC9: Outreach queue filterable by approval_status
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC9
@pytest.mark.asyncio
async def test_ac9_queue_returns_org_scoped_actions(
    db_session: AsyncSession,
    auth_ctx_coordinator: AuthContext,
    seeded_case,
):
    """Queue returns only OutreachActions for the authenticated user's org."""
    # Seed 2 actions for the org
    await seed_outreach_action(
        db_session, seeded_case.id, approval_status="pending_approval"
    )
    await seed_outreach_action(
        db_session, seeded_case.id, approval_status="draft"
    )

    # Seed org2 with its own case and action (should NOT appear)
    await seed_org(db_session, TEST_ORG2_ID)
    await seed_user(db_session, "placement_coordinator", org_id=TEST_ORG2_ID)
    case2 = await seed_case(db_session, org_id=TEST_ORG2_ID)
    await seed_outreach_action(
        db_session, case2.id, approval_status="pending_approval"
    )

    items, total = await service.get_outreach_queue(
        session=db_session,
        auth_ctx=auth_ctx_coordinator,
    )
    assert total == 2
    assert len(items) == 2
    # Verify all returned items belong to our case (which is org-scoped)
    case_ids = {a.patient_case_id for a in items}
    assert seeded_case.id in case_ids


# @forgeplan-spec: AC9
@pytest.mark.asyncio
async def test_ac9_queue_filter_by_pending_approval(
    db_session: AsyncSession,
    auth_ctx_coordinator: AuthContext,
    seeded_case,
):
    """Queue with filter approval_status=pending_approval returns only those records."""
    await seed_outreach_action(
        db_session, seeded_case.id, approval_status="pending_approval"
    )
    await seed_outreach_action(
        db_session, seeded_case.id, approval_status="pending_approval"
    )
    await seed_outreach_action(
        db_session, seeded_case.id, approval_status="draft"
    )
    await seed_outreach_action(
        db_session, seeded_case.id, approval_status="sent"
    )

    items, total = await service.get_outreach_queue(
        session=db_session,
        auth_ctx=auth_ctx_coordinator,
        approval_status_filter="pending_approval",
    )
    assert total == 2
    assert all(a.approval_status == "pending_approval" for a in items)


# @forgeplan-spec: AC9
@pytest.mark.asyncio
async def test_ac9_queue_unauthenticated_returns_401(client):
    """Unauthenticated request to queue returns 401."""
    resp = await client.get("/api/v1/queues/outreach")
    assert resp.status_code == 401


# @forgeplan-spec: AC9
@pytest.mark.asyncio
async def test_ac9_queue_cross_case(
    db_session: AsyncSession,
    auth_ctx_coordinator: AuthContext,
):
    """Queue surfaces actions from multiple cases within the same org."""
    case1 = await seed_case(db_session, current_status="outreach_pending_approval")
    case2 = await seed_case(db_session, current_status="outreach_in_progress")

    await seed_outreach_action(db_session, case1.id, approval_status="pending_approval")
    await seed_outreach_action(db_session, case2.id, approval_status="approved")

    items, total = await service.get_outreach_queue(
        session=db_session,
        auth_ctx=auth_ctx_coordinator,
    )
    assert total >= 2
    case_ids = {a.patient_case_id for a in items}
    assert case1.id in case_ids
    assert case2.id in case_ids


# @forgeplan-spec: AC9
@pytest.mark.asyncio
async def test_ac9_queue_pagination(
    db_session: AsyncSession,
    auth_ctx_coordinator: AuthContext,
    seeded_case,
):
    """Queue respects page and page_size parameters."""
    for _ in range(10):
        await seed_outreach_action(db_session, seeded_case.id, approval_status="draft")

    items_p1, total = await service.get_outreach_queue(
        session=db_session,
        auth_ctx=auth_ctx_coordinator,
        page=1,
        page_size=5,
    )
    assert total == 10
    assert len(items_p1) == 5

    items_p2, _ = await service.get_outreach_queue(
        session=db_session,
        auth_ctx=auth_ctx_coordinator,
        page=2,
        page_size=5,
    )
    assert len(items_p2) == 5

    # Verify pages don't overlap
    ids_p1 = {a.id for a in items_p1}
    ids_p2 = {a.id for a in items_p2}
    assert ids_p1.isdisjoint(ids_p2)


# ---------------------------------------------------------------------------
# AC10: Template listing is read-only
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC10
@pytest.mark.asyncio
async def test_ac10_get_templates_returns_active_templates(
    db_session: AsyncSession,
    auth_ctx_coordinator: AuthContext,
    seed_org_fixture,
    coordinator_user,
):
    """GET /templates/outreach returns active templates for the org."""
    t1 = await seed_template(
        db_session,
        org_id=TEST_ORG_ID,
        template_name="Template 1",
        created_by_user_id=coordinator_user.id,
        is_active=True,
    )
    t2 = await seed_template(
        db_session,
        org_id=TEST_ORG_ID,
        template_name="Template 2",
        created_by_user_id=coordinator_user.id,
        is_active=True,
    )
    # Inactive template should not appear
    t3 = await seed_template(
        db_session,
        org_id=TEST_ORG_ID,
        template_name="Inactive Template",
        created_by_user_id=coordinator_user.id,
        is_active=False,
    )

    templates = await service.get_templates(
        session=db_session, auth_ctx=auth_ctx_coordinator
    )
    ids = [str(t.id) for t in templates]
    assert t1.id in ids
    assert t2.id in ids
    assert t3.id not in ids  # Inactive templates excluded


# @forgeplan-spec: AC10
@pytest.mark.asyncio
async def test_ac10_templates_org_scoped(
    db_session: AsyncSession,
    auth_ctx_coordinator: AuthContext,
    seed_org_fixture,
    coordinator_user,
):
    """Templates from other orgs are not returned."""
    await seed_org(db_session, TEST_ORG2_ID)
    other_user = await seed_user(
        db_session, "admin", org_id=TEST_ORG2_ID
    )
    # My org template
    t_mine = await seed_template(
        db_session,
        org_id=TEST_ORG_ID,
        template_name="Mine",
        created_by_user_id=coordinator_user.id,
    )
    # Other org template
    t_other = await seed_template(
        db_session,
        org_id=TEST_ORG2_ID,
        template_name="Not Mine",
        created_by_user_id=other_user.id,
    )
    templates = await service.get_templates(
        session=db_session, auth_ctx=auth_ctx_coordinator
    )
    ids = [str(t.id) for t in templates]
    assert t_mine.id in ids
    assert t_other.id not in ids


# @forgeplan-spec: AC10
@pytest.mark.asyncio
async def test_ac10_post_templates_returns_405(
    client,
    db_session: AsyncSession,
    coordinator_user,
):
    """POST /api/v1/templates/outreach returns 405 with correct detail."""
    headers = auth_headers(
        user_id=coordinator_user.id,
        org_id=str(TEST_ORG_ID),
        role_key="placement_coordinator",
    )
    resp = await client.post(
        "/api/v1/templates/outreach",
        json={"template_name": "Test"},
        headers=headers,
    )
    assert resp.status_code == 405
    assert "admin-surfaces" in resp.json()["detail"].lower()


# @forgeplan-spec: AC10
@pytest.mark.asyncio
async def test_ac10_patch_templates_returns_405(
    client,
    db_session: AsyncSession,
    coordinator_user,
):
    """PATCH /api/v1/templates/outreach returns 405."""
    headers = auth_headers(
        user_id=coordinator_user.id,
        org_id=str(TEST_ORG_ID),
        role_key="placement_coordinator",
    )
    resp = await client.patch(
        "/api/v1/templates/outreach",
        json={"template_name": "Test"},
        headers=headers,
    )
    assert resp.status_code == 405


# @forgeplan-spec: AC10
@pytest.mark.asyncio
async def test_ac10_delete_templates_returns_405(
    client,
    db_session: AsyncSession,
    coordinator_user,
):
    """DELETE /api/v1/templates/outreach returns 405."""
    headers = auth_headers(
        user_id=coordinator_user.id,
        org_id=str(TEST_ORG_ID),
        role_key="placement_coordinator",
    )
    resp = await client.delete(
        "/api/v1/templates/outreach",
        headers=headers,
    )
    assert resp.status_code == 405


# @forgeplan-spec: AC10
@pytest.mark.asyncio
async def test_ac10_get_templates_via_router(
    client,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
):
    """GET /api/v1/templates/outreach via HTTP returns 200 with template list."""
    await seed_template(
        db_session,
        org_id=TEST_ORG_ID,
        template_name="Router Template",
        created_by_user_id=coordinator_user.id,
        is_active=True,
    )
    headers = auth_headers(
        user_id=coordinator_user.id,
        org_id=str(TEST_ORG_ID),
        role_key="placement_coordinator",
    )
    resp = await client.get("/api/v1/templates/outreach", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "templates" in data
    assert any(t["template_name"] == "Router Template" for t in data["templates"])
