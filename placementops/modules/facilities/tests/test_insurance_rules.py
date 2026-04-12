# @forgeplan-node: facilities-module
"""
Tests for AC6-AC8 (insurance rule CRUD) and AC12 (last_verified_at).

AC6: GET /facilities/{id}/insurance-rules — all roles
AC7: POST /facilities/{id}/insurance-rules — admin only, sets last_verified_at
AC8: PATCH /insurance-rules/{id} — admin or coordinator, updates last_verified_at
AC12: last_verified_at updated on POST/PATCH insurance-rules
"""
# @forgeplan-spec: AC6
# @forgeplan-spec: AC7
# @forgeplan-spec: AC8
# @forgeplan-spec: AC12

import pytest
from datetime import datetime, timezone, timedelta

from placementops.modules.facilities.tests.conftest import (
    TEST_ORG_ID_A,
    TEST_PAYER_ID,
    make_auth_header,
    seed_facility,
    seed_insurance_rule,
)


# ── AC6: GET /facilities/{id}/insurance-rules ─────────────────────────────────

@pytest.mark.asyncio
async def test_list_insurance_rules_read_only_200(async_client, read_only_user, db_session, org_a, payer):
    """AC6: read_only can list insurance rules (200)."""
    # @forgeplan-spec: AC6
    facility = await seed_facility(db_session)
    await seed_insurance_rule(db_session, facility.id)
    await seed_insurance_rule(db_session, facility.id, accepted_status="conditional")
    await seed_insurance_rule(db_session, facility.id, accepted_status="not_accepted")

    headers = make_auth_header("read_only", user_id=read_only_user.id, org_id=TEST_ORG_ID_A)
    resp = await async_client.get(f"/api/v1/facilities/{facility.id}/insurance-rules", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 3


@pytest.mark.asyncio
async def test_list_insurance_rules_all_roles(async_client, db_session, org_a, payer):
    """AC6: all authenticated roles can read insurance rules."""
    # @forgeplan-spec: AC6
    from placementops.modules.facilities.tests.conftest import seed_user
    from uuid import uuid4

    facility = await seed_facility(db_session)
    await seed_insurance_rule(db_session, facility.id)

    for role in ["admin", "intake_staff", "clinical_reviewer", "placement_coordinator", "manager", "read_only"]:
        user = await seed_user(db_session, role)
        headers = make_auth_header(role, user_id=user.id, org_id=TEST_ORG_ID_A)
        resp = await async_client.get(
            f"/api/v1/facilities/{facility.id}/insurance-rules", headers=headers
        )
        assert resp.status_code == 200, f"Role {role} expected 200, got {resp.status_code}"


# ── AC7: POST /facilities/{id}/insurance-rules ────────────────────────────────

@pytest.mark.asyncio
async def test_create_insurance_rule_admin_201(async_client, admin_user, db_session, org_a, payer):
    """AC7: admin can create insurance rule (201); last_verified_at is set."""
    # @forgeplan-spec: AC7
    # @forgeplan-spec: AC12
    facility = await seed_facility(db_session)
    headers = make_auth_header("admin", user_id=admin_user.id, org_id=TEST_ORG_ID_A)
    payload = {
        "payer_id": str(TEST_PAYER_ID),
        "payer_name": "Medicare",
        "accepted_status": "accepted",
    }
    before = datetime.now(timezone.utc)
    resp = await async_client.post(
        f"/api/v1/facilities/{facility.id}/insurance-rules", json=payload, headers=headers
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["accepted_status"] == "accepted"
    assert data["last_verified_at"] is not None

    lva = datetime.fromisoformat(data["last_verified_at"].replace("Z", "+00:00"))
    if lva.tzinfo is None:
        lva = lva.replace(tzinfo=timezone.utc)
    after = datetime.now(timezone.utc)
    assert before - timedelta(seconds=2) <= lva <= after + timedelta(seconds=2)


@pytest.mark.asyncio
async def test_create_insurance_rule_coordinator_403(
    async_client, coordinator_user, db_session, org_a, payer
):
    """AC7: placement_coordinator gets 403 on POST insurance-rules."""
    # @forgeplan-spec: AC7
    facility = await seed_facility(db_session)
    headers = make_auth_header(
        "placement_coordinator", user_id=coordinator_user.id, org_id=TEST_ORG_ID_A
    )
    payload = {
        "payer_id": str(TEST_PAYER_ID),
        "payer_name": "Medicare",
        "accepted_status": "accepted",
    }
    resp = await async_client.post(
        f"/api/v1/facilities/{facility.id}/insurance-rules", json=payload, headers=headers
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_insurance_rule_intake_403(async_client, intake_user, db_session, org_a, payer):
    """AC7: intake_staff gets 403 on POST insurance-rules."""
    # @forgeplan-spec: AC7
    facility = await seed_facility(db_session)
    headers = make_auth_header("intake_staff", user_id=intake_user.id, org_id=TEST_ORG_ID_A)
    payload = {
        "payer_id": str(TEST_PAYER_ID),
        "payer_name": "Medicare",
        "accepted_status": "accepted",
    }
    resp = await async_client.post(
        f"/api/v1/facilities/{facility.id}/insurance-rules", json=payload, headers=headers
    )
    assert resp.status_code == 403


# ── AC8: PATCH /insurance-rules/{id} ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_patch_insurance_rule_coordinator_200(
    async_client, coordinator_user, db_session, org_a, payer
):
    """AC8: placement_coordinator can PATCH; last_verified_at refreshed."""
    # @forgeplan-spec: AC8
    # @forgeplan-spec: AC12
    facility = await seed_facility(db_session)
    rule = await seed_insurance_rule(db_session, facility.id, accepted_status="accepted")
    old_lva = rule.last_verified_at

    headers = make_auth_header(
        "placement_coordinator", user_id=coordinator_user.id, org_id=TEST_ORG_ID_A
    )
    before = datetime.now(timezone.utc)
    resp = await async_client.patch(
        f"/api/v1/insurance-rules/{rule.id}",
        json={"accepted_status": "conditional"},
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted_status"] == "conditional"
    assert data["last_verified_at"] is not None

    new_lva = datetime.fromisoformat(data["last_verified_at"].replace("Z", "+00:00"))
    if new_lva.tzinfo is None:
        new_lva = new_lva.replace(tzinfo=timezone.utc)
    after = datetime.now(timezone.utc)
    assert before - timedelta(seconds=2) <= new_lva <= after + timedelta(seconds=2)


@pytest.mark.asyncio
async def test_patch_insurance_rule_admin_200(async_client, admin_user, db_session, org_a, payer):
    """AC8: admin can PATCH insurance rule."""
    # @forgeplan-spec: AC8
    facility = await seed_facility(db_session)
    rule = await seed_insurance_rule(db_session, facility.id)
    headers = make_auth_header("admin", user_id=admin_user.id, org_id=TEST_ORG_ID_A)
    resp = await async_client.patch(
        f"/api/v1/insurance-rules/{rule.id}",
        json={"notes": "Preauthorization required"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["notes"] == "Preauthorization required"


@pytest.mark.asyncio
async def test_patch_insurance_rule_clinical_reviewer_403(
    async_client, clinical_user, db_session, org_a, payer
):
    """AC8: clinical_reviewer gets 403 on PATCH insurance-rules."""
    # @forgeplan-spec: AC8
    facility = await seed_facility(db_session)
    rule = await seed_insurance_rule(db_session, facility.id)
    headers = make_auth_header("clinical_reviewer", user_id=clinical_user.id, org_id=TEST_ORG_ID_A)
    resp = await async_client.patch(
        f"/api/v1/insurance-rules/{rule.id}",
        json={"accepted_status": "not_accepted"},
        headers=headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_patch_insurance_rule_intake_403(async_client, intake_user, db_session, org_a, payer):
    """AC8: intake_staff gets 403 on PATCH insurance-rules."""
    # @forgeplan-spec: AC8
    facility = await seed_facility(db_session)
    rule = await seed_insurance_rule(db_session, facility.id)
    headers = make_auth_header("intake_staff", user_id=intake_user.id, org_id=TEST_ORG_ID_A)
    resp = await async_client.patch(
        f"/api/v1/insurance-rules/{rule.id}",
        json={"accepted_status": "not_accepted"},
        headers=headers,
    )
    assert resp.status_code == 403


# ── AC12: last_verified_at refreshed on PATCH ─────────────────────────────────

@pytest.mark.asyncio
async def test_patch_insurance_rule_refreshes_last_verified_at(
    async_client, coordinator_user, db_session, org_a, payer
):
    """AC12: last_verified_at on insurance rule is refreshed after PATCH."""
    # @forgeplan-spec: AC12
    facility = await seed_facility(db_session)
    rule = await seed_insurance_rule(db_session, facility.id)

    headers = make_auth_header(
        "placement_coordinator", user_id=coordinator_user.id, org_id=TEST_ORG_ID_A
    )
    before = datetime.now(timezone.utc)
    resp = await async_client.patch(
        f"/api/v1/insurance-rules/{rule.id}",
        json={"notes": "Updated"},
        headers=headers,
    )
    assert resp.status_code == 200
    new_lva_str = resp.json()["last_verified_at"]
    new_lva = datetime.fromisoformat(new_lva_str.replace("Z", "+00:00"))
    if new_lva.tzinfo is None:
        new_lva = new_lva.replace(tzinfo=timezone.utc)
    after = datetime.now(timezone.utc)
    assert before - timedelta(seconds=2) <= new_lva <= after + timedelta(seconds=2)
