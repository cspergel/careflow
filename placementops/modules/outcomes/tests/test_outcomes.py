# @forgeplan-node: outcomes-module
# @forgeplan-spec: AC1, AC2, AC3, AC4, AC5, AC6, AC7, AC8, AC10, AC14, AC15, AC16
"""
Tests for outcomes recording: AC1-AC10, AC14-AC16.

Test coverage:
  AC1  — Role gate (403 for disallowed roles, 201 for coordinator/admin)
  AC2  — Accepted requires sent outreach for facility_id
  AC3  — Accepted advances case + writes PlacementOutcome + AuditEvent
  AC4  — Declined requires facility_id + sent outreach + valid decline_reason_code
  AC5  — Declined advances case to declined_retry_needed + audits
  AC6  — Rescinded acceptance (accepted→declined_retry_needed)
  AC7  — family_declined/withdrawn permit null facility_id; no auto-advance
  AC8  — Auto-cancel of draft/pending_approval/approved outreach on accepted/placed
  AC10 — Placed outcome records facility, advances to placed, triggers auto-cancel
  AC14 — All outcome types produce an AuditEvent
  AC15 — Closed case returns 409
  AC16 — Decline reason codes validated against reference table
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from placementops.core.models import (
    AuditEvent,
    OutreachAction,
    PatientCase,
    PlacementOutcome,
)
from placementops.modules.outcomes.tests.conftest import (
    TEST_ORG_ID,
    TEST_FACILITY_ID,
    auth_headers,
    make_id,
    seed_case,
    seed_decline_reasons,
    seed_facility,
    seed_org,
    seed_outreach_action,
    seed_user,
)


# ── AC1 — Role gate ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ac1_intake_staff_returns_403(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    intake_user,
) -> None:
    """intake_staff role → 403 on POST outcomes."""
    case = await seed_case(db_session, current_status="pending_facility_response")
    facility_id = str(TEST_FACILITY_ID)
    await seed_facility(db_session)
    await seed_outreach_action(db_session, case_id=case.id, facility_id=facility_id, approval_status="sent")
    await seed_decline_reasons(db_session)

    resp = await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={"outcome_type": "family_declined"},
        headers=auth_headers(intake_user.id, str(TEST_ORG_ID), "intake_staff"),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_ac1_clinical_reviewer_returns_403(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    clinical_user,
) -> None:
    """clinical_reviewer role → 403 on POST outcomes."""
    case = await seed_case(db_session, current_status="pending_facility_response")

    resp = await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={"outcome_type": "family_declined"},
        headers=auth_headers(clinical_user.id, str(TEST_ORG_ID), "clinical_reviewer"),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_ac1_read_only_returns_403(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    read_only_user,
) -> None:
    """read_only role → 403 on POST outcomes."""
    case = await seed_case(db_session, current_status="pending_facility_response")

    resp = await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={"outcome_type": "family_declined"},
        headers=auth_headers(read_only_user.id, str(TEST_ORG_ID), "read_only"),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_ac1_manager_returns_403(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    manager_user,
) -> None:
    """manager role → 403 on POST outcomes (AC1: coordinator-only endpoint)."""
    case = await seed_case(db_session, current_status="pending_facility_response")

    resp = await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={"outcome_type": "family_declined"},
        headers=auth_headers(manager_user.id, str(TEST_ORG_ID), "manager"),
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_ac1_coordinator_family_declined_returns_201(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """placement_coordinator can record family_declined outcome → 201."""
    case = await seed_case(db_session, current_status="pending_facility_response")

    resp = await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={"outcome_type": "family_declined"},
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_ac1_admin_family_declined_returns_201(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    admin_user,
) -> None:
    """admin can record family_declined outcome → 201."""
    case = await seed_case(db_session, current_status="pending_facility_response")

    resp = await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={"outcome_type": "family_declined"},
        headers=auth_headers(admin_user.id, str(TEST_ORG_ID), "admin"),
    )
    assert resp.status_code == 201, resp.text


# ── AC2 — Accepted requires sent outreach ──────────────────────────────────────


@pytest.mark.asyncio
async def test_ac2_accepted_with_sent_outreach_returns_201(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """Accepted outcome with valid sent outreach → 201 and case advances."""
    await seed_facility(db_session)
    case = await seed_case(db_session, current_status="pending_facility_response")
    await seed_outreach_action(
        db_session, case_id=case.id, facility_id=str(TEST_FACILITY_ID), approval_status="sent"
    )

    resp = await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={"outcome_type": "accepted", "facility_id": str(TEST_FACILITY_ID)},
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["outcome_type"] == "accepted"
    assert body["facility_id"] == str(TEST_FACILITY_ID)


@pytest.mark.asyncio
async def test_ac2_accepted_without_sent_outreach_returns_400(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """Accepted outcome without sent outreach for facility → 400."""
    await seed_facility(db_session)
    case = await seed_case(db_session, current_status="pending_facility_response")
    # Outreach exists but only in draft state, not sent
    await seed_outreach_action(
        db_session, case_id=case.id, facility_id=str(TEST_FACILITY_ID), approval_status="draft"
    )

    resp = await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={"outcome_type": "accepted", "facility_id": str(TEST_FACILITY_ID)},
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "no_sent_outreach" in str(detail)


@pytest.mark.asyncio
async def test_ac2_accepted_no_outreach_at_all_returns_400(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """Accepted outcome with no outreach records for facility → 400."""
    await seed_facility(db_session)
    case = await seed_case(db_session, current_status="pending_facility_response")

    resp = await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={"outcome_type": "accepted", "facility_id": str(TEST_FACILITY_ID)},
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 400


# ── AC3 — Accepted advances case and writes records ───────────────────────────


@pytest.mark.asyncio
async def test_ac3_accepted_advances_case_and_writes_records(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """After accepted outcome: case=accepted, PlacementOutcome written, AuditEvent written."""
    await seed_facility(db_session)
    case = await seed_case(db_session, current_status="pending_facility_response")
    await seed_outreach_action(
        db_session, case_id=case.id, facility_id=str(TEST_FACILITY_ID), approval_status="sent"
    )

    resp = await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={"outcome_type": "accepted", "facility_id": str(TEST_FACILITY_ID)},
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 201, resp.text

    # Verify PlacementOutcome row
    outcome_result = await db_session.execute(
        select(PlacementOutcome).where(PlacementOutcome.patient_case_id == case.id)
    )
    outcome = outcome_result.scalar_one()
    assert outcome.outcome_type == "accepted"
    assert outcome.facility_id == str(TEST_FACILITY_ID)
    assert outcome.recorded_by_user_id == coordinator_user.id

    # Verify case status advanced
    await db_session.refresh(case)
    assert case.current_status == "accepted"

    # Verify AuditEvent written for the outcome
    audit_result = await db_session.execute(
        select(AuditEvent).where(
            AuditEvent.entity_type == "placement_outcome",
            AuditEvent.entity_id == outcome.id,
        )
    )
    audit = audit_result.scalar_one()
    assert audit.event_type == "outcome_recorded"
    assert audit.actor_user_id == coordinator_user.id


# ── AC4 — Declined requires facility_id + sent outreach + valid reason code ───


@pytest.mark.asyncio
async def test_ac4_declined_null_facility_returns_400(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """Declined outcome with null facility_id → 400 (schema validation)."""
    case = await seed_case(db_session, current_status="pending_facility_response")
    await seed_decline_reasons(db_session)

    resp = await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={
            "outcome_type": "declined",
            "facility_id": None,
            "decline_reason_code": "no_response",
        },
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 422  # Pydantic validation error


@pytest.mark.asyncio
async def test_ac4_declined_no_sent_outreach_returns_400(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """Declined outcome with no sent outreach for facility → 400."""
    await seed_facility(db_session)
    case = await seed_case(db_session, current_status="pending_facility_response")
    await seed_decline_reasons(db_session)
    # Outreach only in approved state, not sent
    await seed_outreach_action(
        db_session, case_id=case.id, facility_id=str(TEST_FACILITY_ID), approval_status="approved"
    )

    resp = await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={
            "outcome_type": "declined",
            "facility_id": str(TEST_FACILITY_ID),
            "decline_reason_code": "no_response",
        },
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_ac4_declined_invalid_reason_code_returns_400(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """Declined outcome with unknown decline_reason_code → 400 (AC16)."""
    await seed_facility(db_session)
    case = await seed_case(db_session, current_status="pending_facility_response")
    await seed_decline_reasons(db_session)
    await seed_outreach_action(
        db_session, case_id=case.id, facility_id=str(TEST_FACILITY_ID), approval_status="sent"
    )

    resp = await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={
            "outcome_type": "declined",
            "facility_id": str(TEST_FACILITY_ID),
            "decline_reason_code": "not_a_real_code",
        },
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "invalid_decline_reason_code" in str(detail)


@pytest.mark.asyncio
async def test_ac4_declined_missing_reason_code_returns_422(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """Declined outcome without decline_reason_code → 422 (schema validation)."""
    await seed_facility(db_session)
    case = await seed_case(db_session, current_status="pending_facility_response")

    resp = await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={
            "outcome_type": "declined",
            "facility_id": str(TEST_FACILITY_ID),
        },
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ac4_declined_valid_returns_201(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """Declined outcome with valid facility + sent outreach + valid code → 201."""
    await seed_facility(db_session)
    case = await seed_case(db_session, current_status="pending_facility_response")
    await seed_decline_reasons(db_session)
    await seed_outreach_action(
        db_session, case_id=case.id, facility_id=str(TEST_FACILITY_ID), approval_status="sent"
    )

    resp = await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={
            "outcome_type": "declined",
            "facility_id": str(TEST_FACILITY_ID),
            "decline_reason_code": "no_response",
            "decline_reason_text": "Called 3 times, no response",
        },
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["decline_reason_code"] == "no_response"
    assert body["decline_reason_text"] == "Called 3 times, no response"


# ── AC5 — Declined advances to declined_retry_needed ─────────────────────────


@pytest.mark.asyncio
async def test_ac5_declined_advances_case_and_writes_records(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """After declined outcome: case=declined_retry_needed, records written."""
    await seed_facility(db_session)
    case = await seed_case(db_session, current_status="pending_facility_response")
    await seed_decline_reasons(db_session)
    await seed_outreach_action(
        db_session, case_id=case.id, facility_id=str(TEST_FACILITY_ID), approval_status="sent"
    )

    resp = await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={
            "outcome_type": "declined",
            "facility_id": str(TEST_FACILITY_ID),
            "decline_reason_code": "bed_no_longer_available",
            "decline_reason_text": "Bed was given to another patient",
        },
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 201, resp.text

    # Verify case advanced
    await db_session.refresh(case)
    assert case.current_status == "declined_retry_needed"

    # Verify PlacementOutcome with reason
    outcome_result = await db_session.execute(
        select(PlacementOutcome).where(PlacementOutcome.patient_case_id == case.id)
    )
    outcome = outcome_result.scalar_one()
    assert outcome.decline_reason_code == "bed_no_longer_available"
    assert outcome.decline_reason_text == "Bed was given to another patient"

    # Verify AuditEvent for outcome
    audit_result = await db_session.execute(
        select(AuditEvent).where(
            AuditEvent.entity_type == "placement_outcome",
            AuditEvent.entity_id == outcome.id,
        )
    )
    audit_result.scalar_one()  # exactly one AuditEvent


# ── AC6 — Rescinded acceptance (accepted → declined_retry_needed) ─────────────


@pytest.mark.asyncio
async def test_ac6_rescinded_acceptance_advances_to_declined_retry_needed(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """Case at accepted + declined outcome → case transitions to declined_retry_needed."""
    await seed_facility(db_session)
    case = await seed_case(db_session, current_status="accepted")
    await seed_decline_reasons(db_session)
    await seed_outreach_action(
        db_session, case_id=case.id, facility_id=str(TEST_FACILITY_ID), approval_status="sent"
    )

    resp = await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={
            "outcome_type": "declined",
            "facility_id": str(TEST_FACILITY_ID),
            "decline_reason_code": "insurance_issue_post_acceptance",
        },
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 201, resp.text

    await db_session.refresh(case)
    assert case.current_status == "declined_retry_needed"


# ── AC7 — family_declined/withdrawn: null facility_id, no auto-advance ────────


@pytest.mark.asyncio
async def test_ac7_family_declined_null_facility_returns_201(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """family_declined with null facility_id → 201, case status unchanged."""
    case = await seed_case(db_session, current_status="pending_facility_response")

    resp = await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={"outcome_type": "family_declined"},
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["outcome_type"] == "family_declined"
    assert body["facility_id"] is None

    # Premature auto-close guard: family_declined must NOT advance or close the case;
    # the manager must confirm closure separately via POST /status-transition (AC7, AC11).
    await db_session.refresh(case)
    assert case.current_status == "pending_facility_response", (
        f"family_declined must not auto-advance case status; got {case.current_status!r}"
    )


@pytest.mark.asyncio
async def test_ac7_withdrawn_null_facility_returns_201(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """withdrawn with null facility_id → 201, case status unchanged."""
    case = await seed_case(db_session, current_status="pending_facility_response")

    resp = await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={"outcome_type": "withdrawn"},
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 201, resp.text

    await db_session.refresh(case)
    assert case.current_status == "pending_facility_response"


@pytest.mark.asyncio
async def test_ac7_family_declined_with_facility_id_still_no_advance(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """family_declined with optional facility_id → still no status advance."""
    await seed_facility(db_session)
    case = await seed_case(db_session, current_status="pending_facility_response")

    resp = await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={"outcome_type": "family_declined", "facility_id": str(TEST_FACILITY_ID)},
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 201, resp.text
    await db_session.refresh(case)
    assert case.current_status == "pending_facility_response"


# ── AC8 — Auto-cancel of open outreach on accepted/placed ─────────────────────


@pytest.mark.asyncio
async def test_ac8_accepted_auto_cancels_draft_and_approved_not_sent(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """accepted outcome: draft/pending_approval/approved outreach canceled; sent not modified."""
    await seed_facility(db_session)
    case = await seed_case(db_session, current_status="pending_facility_response")
    await seed_outreach_action(
        db_session, case_id=case.id, facility_id=str(TEST_FACILITY_ID), approval_status="sent"
    )

    # Open outreach actions that should be canceled
    draft_action = await seed_outreach_action(
        db_session, case_id=case.id, facility_id=str(TEST_FACILITY_ID), approval_status="draft"
    )
    approved_action = await seed_outreach_action(
        db_session, case_id=case.id, facility_id=str(TEST_FACILITY_ID), approval_status="approved"
    )
    pending_action = await seed_outreach_action(
        db_session, case_id=case.id, facility_id=str(TEST_FACILITY_ID), approval_status="pending_approval"
    )

    resp = await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={"outcome_type": "accepted", "facility_id": str(TEST_FACILITY_ID)},
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 201, resp.text

    # draft, pending_approval, approved → should now be canceled
    await db_session.refresh(draft_action)
    await db_session.refresh(approved_action)
    await db_session.refresh(pending_action)
    assert draft_action.approval_status == "canceled"
    assert approved_action.approval_status == "canceled"
    assert pending_action.approval_status == "canceled"

    # The original sent action must remain sent
    sent_result = await db_session.execute(
        select(OutreachAction).where(
            OutreachAction.patient_case_id == case.id,
            OutreachAction.approval_status == "sent",
        )
    )
    sent_actions = sent_result.scalars().all()
    assert len(sent_actions) == 1, "Sent outreach must not be canceled"


@pytest.mark.asyncio
async def test_ac8_family_declined_does_not_cancel_outreach(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """family_declined does NOT trigger auto-cancel of outreach."""
    await seed_facility(db_session)
    case = await seed_case(db_session, current_status="pending_facility_response")
    draft_action = await seed_outreach_action(
        db_session, case_id=case.id, facility_id=str(TEST_FACILITY_ID), approval_status="draft"
    )

    resp = await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={"outcome_type": "family_declined"},
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 201, resp.text

    # Draft outreach must remain unchanged
    await db_session.refresh(draft_action)
    assert draft_action.approval_status == "draft"


# ── AC10 — Placed outcome ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ac10_placed_advances_case_and_auto_cancels(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """placed outcome: case=placed, auto-cancel triggered, records written."""
    await seed_facility(db_session)
    case = await seed_case(db_session, current_status="accepted")
    await seed_outreach_action(
        db_session, case_id=case.id, facility_id=str(TEST_FACILITY_ID), approval_status="sent"
    )
    draft_action = await seed_outreach_action(
        db_session, case_id=case.id, facility_id=str(TEST_FACILITY_ID), approval_status="draft"
    )

    resp = await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={"outcome_type": "placed", "facility_id": str(TEST_FACILITY_ID)},
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 201, resp.text

    # Verify case advanced to placed
    await db_session.refresh(case)
    assert case.current_status == "placed"

    # Verify PlacementOutcome written
    outcome_result = await db_session.execute(
        select(PlacementOutcome).where(PlacementOutcome.patient_case_id == case.id)
    )
    outcome = outcome_result.scalar_one()
    assert outcome.outcome_type == "placed"
    assert outcome.facility_id == str(TEST_FACILITY_ID)

    # Verify auto-cancel
    await db_session.refresh(draft_action)
    assert draft_action.approval_status == "canceled"


# ── AC14 — All outcome types produce AuditEvent ───────────────────────────────


@pytest.mark.asyncio
async def test_ac14_all_outcome_types_produce_audit_event(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """Every outcome type generates exactly one AuditEvent with entity_type=placement_outcome."""
    await seed_facility(db_session)
    await seed_decline_reasons(db_session)

    outcomes_to_test = [
        # (outcome_type, case_status, extra_fields, needs_sent_outreach)
        ("family_declined", "pending_facility_response", {}, False),
        ("withdrawn", "pending_facility_response", {}, False),
        ("placed", "accepted", {"facility_id": str(TEST_FACILITY_ID)}, True),
    ]

    for outcome_type, case_status, extra, needs_outreach in outcomes_to_test:
        case = await seed_case(db_session, current_status=case_status)

        if needs_outreach:
            await seed_outreach_action(
                db_session, case_id=case.id, facility_id=str(TEST_FACILITY_ID), approval_status="sent"
            )

        resp = await client.post(
            f"/api/v1/cases/{case.id}/outcomes",
            json={"outcome_type": outcome_type, **extra},
            headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
        )
        assert resp.status_code == 201, f"Failed for {outcome_type}: {resp.text}"
        body = resp.json()
        outcome_id = body["id"]

        audit_result = await db_session.execute(
            select(AuditEvent).where(
                AuditEvent.entity_type == "placement_outcome",
                AuditEvent.entity_id == outcome_id,
            )
        )
        audit = audit_result.scalar_one_or_none()
        assert audit is not None, f"No AuditEvent found for outcome_type={outcome_type}"
        assert audit.event_type == "outcome_recorded"


@pytest.mark.asyncio
async def test_ac14_accepted_produces_audit_event(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """accepted outcome produces AuditEvent."""
    await seed_facility(db_session)
    case = await seed_case(db_session, current_status="pending_facility_response")
    await seed_outreach_action(
        db_session, case_id=case.id, facility_id=str(TEST_FACILITY_ID), approval_status="sent"
    )

    resp = await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={"outcome_type": "accepted", "facility_id": str(TEST_FACILITY_ID)},
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    outcome_id = body["id"]

    audit_result = await db_session.execute(
        select(AuditEvent).where(
            AuditEvent.entity_type == "placement_outcome",
            AuditEvent.entity_id == outcome_id,
        )
    )
    audit = audit_result.scalar_one_or_none()
    assert audit is not None
    assert audit.event_type == "outcome_recorded"


@pytest.mark.asyncio
async def test_ac14_declined_produces_audit_event(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """declined outcome produces AuditEvent."""
    await seed_facility(db_session)
    case = await seed_case(db_session, current_status="pending_facility_response")
    await seed_decline_reasons(db_session)
    await seed_outreach_action(
        db_session, case_id=case.id, facility_id=str(TEST_FACILITY_ID), approval_status="sent"
    )

    resp = await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={
            "outcome_type": "declined",
            "facility_id": str(TEST_FACILITY_ID),
            "decline_reason_code": "no_response",
        },
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    outcome_id = body["id"]

    audit_result = await db_session.execute(
        select(AuditEvent).where(
            AuditEvent.entity_type == "placement_outcome",
            AuditEvent.entity_id == outcome_id,
        )
    )
    audit = audit_result.scalar_one_or_none()
    assert audit is not None


# ── AC15 — Closed case returns 409 ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ac15_closed_case_returns_409(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """POST outcomes on a closed case → 409 Conflict."""
    case = await seed_case(db_session, current_status="closed")

    resp = await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={"outcome_type": "family_declined"},
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 409


# ── AC16 — Decline reason seed codes ──────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [
    "bed_no_longer_available",
    "insurance_issue_post_acceptance",
    "clinical_criteria_not_met",
    "no_response",
])
async def test_ac16_valid_seed_codes_return_201(
    code: str,
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """All four seeded decline reason codes return 201."""
    await seed_facility(db_session)
    case = await seed_case(db_session, current_status="pending_facility_response")
    await seed_decline_reasons(db_session)
    await seed_outreach_action(
        db_session, case_id=case.id, facility_id=str(TEST_FACILITY_ID), approval_status="sent"
    )

    resp = await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={
            "outcome_type": "declined",
            "facility_id": str(TEST_FACILITY_ID),
            "decline_reason_code": code,
        },
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 201, f"Code '{code}' should be valid but returned {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_ac16_unlisted_code_returns_400(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org_fixture,
    coordinator_user,
) -> None:
    """Unlisted decline reason code → 400."""
    await seed_facility(db_session)
    case = await seed_case(db_session, current_status="pending_facility_response")
    await seed_decline_reasons(db_session)
    await seed_outreach_action(
        db_session, case_id=case.id, facility_id=str(TEST_FACILITY_ID), approval_status="sent"
    )

    resp = await client.post(
        f"/api/v1/cases/{case.id}/outcomes",
        json={
            "outcome_type": "declined",
            "facility_id": str(TEST_FACILITY_ID),
            "decline_reason_code": "made_up_code_xyz",
        },
        headers=auth_headers(coordinator_user.id, str(TEST_ORG_ID), "placement_coordinator"),
    )
    assert resp.status_code == 400
