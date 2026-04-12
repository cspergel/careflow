# @forgeplan-node: outcomes-module
# @forgeplan-spec: AC9, AC11, AC12, AC13
"""
Tests for timeline, outcome history, and status transitions: AC9, AC11-AC13.

Test coverage:
  AC9  — Retry routing: declined_retry_needed → ready_for_matching / outreach_pending_approval
  AC11 — Case closure requires closure_reason + manager/admin role
  AC12 — GET /timeline returns chronological case_activity_events
  AC13 — GET /outcomes returns all PlacementOutcome records for a case
"""
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from placementops.core.models import CaseStatusHistory, PatientCase, PlacementOutcome
from placementops.modules.outcomes.tests.conftest import (
    TEST_ORG_ID,
    TEST_FACILITY_ID,
    auth_headers,
    make_id,
    seed_case,
    seed_decline_reasons,
    seed_facility,
    seed_outreach_action,
    seed_outcome,
    seed_user,
)


# ── AC12 — Timeline endpoint ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ac12_timeline_returns_empty_for_new_case(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """Timeline for a case with no transitions returns empty events list."""
    case = await seed_case(db_session, current_status="pending_facility_response")

    resp = await client.get(
        f"/api/v1/cases/{case.id}/timeline",
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "events" in body
    assert "total" in body
    assert body["total"] == 0
    assert body["events"] == []


@pytest.mark.asyncio
async def test_ac12_timeline_returns_chronological_events_after_outcome(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """Timeline includes status transitions after recording an accepted outcome."""
    await seed_facility(db_session)
    case = await seed_case(db_session, current_status="pending_facility_response")
    await seed_outreach_action(
        db_session, case_id=case.id, facility_id=str(TEST_FACILITY_ID), approval_status="sent"
    )

    # Record accepted outcome — triggers status transition to accepted
    resp = await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={"outcome_type": "accepted", "facility_id": str(TEST_FACILITY_ID)},
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 201, resp.text

    # Get timeline
    timeline_resp = await client.get(
        f"/api/v1/cases/{case.id}/timeline",
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert timeline_resp.status_code == 200, timeline_resp.text
    body = timeline_resp.json()

    assert body["total"] >= 1
    events = body["events"]

    # Should have at least one event for the accepted transition
    accepted_event = next((e for e in events if e["new_status"] == "accepted"), None)
    assert accepted_event is not None
    assert accepted_event["old_status"] == "pending_facility_response"
    assert accepted_event["event_type"] == "status_changed"

    # Verify chronological ordering (occurred_at ascending)
    if len(events) > 1:
        for i in range(len(events) - 1):
            assert events[i]["occurred_at"] <= events[i + 1]["occurred_at"]


@pytest.mark.asyncio
async def test_ac12_timeline_event_fields(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """Each timeline event has actor_user_id, event_type, old_status, new_status, occurred_at."""
    await seed_facility(db_session)
    case = await seed_case(db_session, current_status="pending_facility_response")
    await seed_outreach_action(
        db_session, case_id=case.id, facility_id=str(TEST_FACILITY_ID), approval_status="sent"
    )

    # Record accepted outcome to generate timeline entry
    await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={"outcome_type": "accepted", "facility_id": str(TEST_FACILITY_ID)},
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )

    resp = await client.get(
        f"/api/v1/cases/{case.id}/timeline",
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["events"]) >= 1

    event = body["events"][0]
    assert "case_id" in event
    assert "actor_user_id" in event
    assert "event_type" in event
    assert "old_status" in event
    assert "new_status" in event
    assert "occurred_at" in event


@pytest.mark.asyncio
async def test_ac12_timeline_tenant_isolation_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
) -> None:
    """Timeline request from a different org returns 404."""
    from placementops.modules.outcomes.tests.conftest import TEST_ORG2_ID, seed_org
    await seed_org(db_session, TEST_ORG2_ID)
    cross_org_user = await seed_user(db_session, "placement_coordinator", org_id=TEST_ORG2_ID)
    case = await seed_case(db_session, current_status="pending_facility_response")

    resp = await client.get(
        f"/api/v1/cases/{case.id}/timeline",
        headers=auth_headers(cross_org_user.id, str(TEST_ORG2_ID), "placement_coordinator"),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_ac12_timeline_rbac_403(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    intake_user,
) -> None:
    """intake_staff cannot read timeline → 403."""
    case = await seed_case(db_session, current_status="pending_facility_response")

    resp = await client.get(
        f"/api/v1/cases/{case.id}/timeline",
        headers=auth_headers(intake_user.id, str(TEST_ORG_ID), "intake_staff"),
    )
    assert resp.status_code == 403


# ── AC13 — Outcome history ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ac13_outcome_history_returns_all_outcomes(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """GET /outcomes returns all PlacementOutcome records in creation order."""
    await seed_facility(db_session)
    case = await seed_case(db_session, current_status="placed")

    # Seed multiple outcomes for this case
    await seed_outcome(
        db_session,
        case_id=case.id,
        recorded_by_user_id=coordinator_user.id,
        outcome_type="family_declined",
    )
    await seed_outcome(
        db_session,
        case_id=case.id,
        recorded_by_user_id=coordinator_user.id,
        outcome_type="withdrawn",
    )

    resp = await client.get(
        f"/api/v1/cases/{case.id}/outcomes",
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    outcome_types = {item["outcome_type"] for item in body["items"]}
    assert "family_declined" in outcome_types
    assert "withdrawn" in outcome_types


@pytest.mark.asyncio
async def test_ac13_outcome_history_tenant_isolation(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
) -> None:
    """Outcomes from another org are not visible."""
    from placementops.modules.outcomes.tests.conftest import TEST_ORG2_ID, seed_org
    await seed_org(db_session, TEST_ORG2_ID)
    cross_org_user = await seed_user(db_session, "placement_coordinator", org_id=TEST_ORG2_ID)
    case = await seed_case(db_session, current_status="placed")

    await seed_outcome(
        db_session,
        case_id=case.id,
        recorded_by_user_id=cross_org_user.id,
        outcome_type="family_declined",
    )

    # Request as different org user — case not found
    resp = await client.get(
        f"/api/v1/cases/{case.id}/outcomes",
        headers=auth_headers(cross_org_user.id, str(TEST_ORG2_ID), "placement_coordinator"),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_ac13_outcome_history_empty(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """GET /outcomes with no outcomes returns empty list."""
    case = await seed_case(db_session, current_status="pending_facility_response")

    resp = await client.get(
        f"/api/v1/cases/{case.id}/outcomes",
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["items"] == []


# ── AC9 — Retry routing ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ac9_retry_to_ready_for_matching_returns_200(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """Retry routing: declined_retry_needed → ready_for_matching returns 200."""
    case = await seed_case(db_session, current_status="declined_retry_needed")

    resp = await client.post(
        f"/api/v1/cases/{case.id}/status-transition",
        json={"to_status": "ready_for_matching", "transition_reason": "Retrying after decline"},
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["current_status"] == "ready_for_matching"


@pytest.mark.asyncio
async def test_ac9_retry_to_outreach_pending_approval_returns_200(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """Retry routing: declined_retry_needed → outreach_pending_approval returns 200."""
    case = await seed_case(db_session, current_status="declined_retry_needed")

    resp = await client.post(
        f"/api/v1/cases/{case.id}/status-transition",
        json={"to_status": "outreach_pending_approval", "transition_reason": "Re-opening outreach"},
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["current_status"] == "outreach_pending_approval"


@pytest.mark.asyncio
async def test_ac9_intake_staff_retry_returns_403(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    intake_user,
) -> None:
    """intake_staff cannot perform status transitions → 403."""
    case = await seed_case(db_session, current_status="declined_retry_needed")

    resp = await client.post(
        f"/api/v1/cases/{case.id}/status-transition",
        json={"to_status": "ready_for_matching", "transition_reason": "Retry"},
        headers=auth_headers(intake_user.id, str(TEST_ORG_ID), "intake_staff"),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_ac9_admin_retry_returns_200(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    admin_user,
) -> None:
    """admin can perform retry routing → 200."""
    case = await seed_case(db_session, current_status="declined_retry_needed")

    resp = await client.post(
        f"/api/v1/cases/{case.id}/status-transition",
        json={"to_status": "ready_for_matching", "transition_reason": "Admin retry"},
        headers=auth_headers(admin_user.id, str(TEST_ORG_ID), "admin"),
    )
    assert resp.status_code == 200, resp.text


# ── AC11 — Case closure ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ac11_closure_without_reason_returns_400(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    manager_user,
) -> None:
    """Closure without transition_reason → 400."""
    case = await seed_case(db_session, current_status="placed")

    resp = await client.post(
        f"/api/v1/cases/{case.id}/status-transition",
        json={"to_status": "closed"},
        headers=auth_headers(manager_user.id, str(TEST_ORG_ID), "manager"),
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "closure_reason_required" in str(detail)


@pytest.mark.asyncio
async def test_ac11_closure_empty_reason_returns_400(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    manager_user,
) -> None:
    """Closure with empty transition_reason → 400."""
    case = await seed_case(db_session, current_status="placed")

    resp = await client.post(
        f"/api/v1/cases/{case.id}/status-transition",
        json={"to_status": "closed", "transition_reason": "   "},
        headers=auth_headers(manager_user.id, str(TEST_ORG_ID), "manager"),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_ac11_coordinator_closure_returns_403(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """placement_coordinator cannot close a case → 403."""
    case = await seed_case(db_session, current_status="placed")

    resp = await client.post(
        f"/api/v1/cases/{case.id}/status-transition",
        json={"to_status": "closed", "transition_reason": "Case complete"},
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 403
    detail = resp.json()["detail"]
    assert "insufficient_role_for_closure" in str(detail)


@pytest.mark.asyncio
async def test_ac11_manager_closure_with_reason_returns_200(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    manager_user,
) -> None:
    """manager with valid transition_reason → 200 and case is closed."""
    case = await seed_case(db_session, current_status="placed")

    resp = await client.post(
        f"/api/v1/cases/{case.id}/status-transition",
        json={"to_status": "closed", "transition_reason": "Patient successfully placed"},
        headers=auth_headers(manager_user.id, str(TEST_ORG_ID), "manager"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["current_status"] == "closed"


@pytest.mark.asyncio
async def test_ac11_admin_closure_with_reason_returns_200(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    admin_user,
) -> None:
    """admin with valid transition_reason → 200 and case is closed."""
    case = await seed_case(db_session, current_status="placed")

    resp = await client.post(
        f"/api/v1/cases/{case.id}/status-transition",
        json={"to_status": "closed", "transition_reason": "Administrative closure"},
        headers=auth_headers(admin_user.id, str(TEST_ORG_ID), "admin"),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["current_status"] == "closed"


@pytest.mark.asyncio
async def test_ac11_family_declined_requires_manager_to_close(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
    manager_user,
) -> None:
    """
    After family_declined outcome (case not auto-advanced), manager must explicitly close.
    This validates the full AC7+AC11 path.
    """
    case = await seed_case(db_session, current_status="pending_facility_response")

    # Record family_declined — case stays at pending_facility_response
    outcome_resp = await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={"outcome_type": "family_declined"},
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert outcome_resp.status_code == 201, outcome_resp.text

    await db_session.refresh(case)
    assert case.current_status == "pending_facility_response"  # no auto-advance

    # Manager closes the case via status-transition
    close_resp = await client.post(
        f"/api/v1/cases/{case.id}/status-transition",
        json={"to_status": "closed", "transition_reason": "Family declined placement"},
        headers=auth_headers(manager_user.id, str(TEST_ORG_ID), "manager"),
    )
    assert close_resp.status_code == 200, close_resp.text
    body = close_resp.json()
    assert body["current_status"] == "closed"
