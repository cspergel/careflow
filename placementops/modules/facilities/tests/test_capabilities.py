# @forgeplan-node: facilities-module
"""
Tests for AC5 (capabilities upsert), AC9 (18 flags), AC12 (last_verified_at).
"""
# @forgeplan-spec: AC5
# @forgeplan-spec: AC9
# @forgeplan-spec: AC12

import pytest
from datetime import datetime, timezone, timedelta

from placementops.modules.facilities.tests.conftest import (
    TEST_ORG_ID_A,
    make_auth_header,
    seed_facility,
)

# All 18 capability flags with their values
ALL_18_FLAGS_TRUE = {
    "accepts_snf": True,
    "accepts_irf": True,
    "accepts_ltach": True,
    "accepts_trach": True,
    "accepts_vent": True,
    "accepts_hd": True,
    "in_house_hemodialysis": True,
    "accepts_peritoneal_dialysis": True,
    "accepts_wound_vac": True,
    "accepts_iv_antibiotics": True,
    "accepts_tpn": True,
    "accepts_bariatric": True,
    "accepts_behavioral_complexity": True,
    "accepts_memory_care": True,
    "accepts_isolation_cases": True,
    "accepts_oxygen_therapy": True,
    "weekend_admissions": True,
    "after_hours_admissions": True,
}

ALL_18_FLAGS_FALSE = {k: False for k in ALL_18_FLAGS_TRUE}


# ── AC5: PUT capabilities ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_put_capabilities_admin_200(async_client, admin_user, db_session, org_a):
    """AC5: admin can PUT capabilities (200) with all 18 flags."""
    # @forgeplan-spec: AC5
    facility = await seed_facility(db_session)
    headers = make_auth_header("admin", user_id=admin_user.id, org_id=TEST_ORG_ID_A)
    resp = await async_client.put(
        f"/api/v1/facilities/{facility.id}/capabilities",
        json=ALL_18_FLAGS_TRUE,
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepts_trach"] is True
    assert data["accepts_vent"] is True
    assert data["facility_id"] == facility.id


@pytest.mark.asyncio
async def test_put_capabilities_coordinator_200(async_client, coordinator_user, db_session, org_a):
    """AC5: placement_coordinator can PUT capabilities (200)."""
    # @forgeplan-spec: AC5
    facility = await seed_facility(db_session)
    headers = make_auth_header("placement_coordinator", user_id=coordinator_user.id, org_id=TEST_ORG_ID_A)
    resp = await async_client.put(
        f"/api/v1/facilities/{facility.id}/capabilities",
        json=ALL_18_FLAGS_FALSE,
        headers=headers,
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_put_capabilities_clinical_reviewer_403(async_client, clinical_user, db_session, org_a):
    """AC5: clinical_reviewer gets 403 on PUT capabilities."""
    # @forgeplan-spec: AC5
    facility = await seed_facility(db_session)
    headers = make_auth_header("clinical_reviewer", user_id=clinical_user.id, org_id=TEST_ORG_ID_A)
    resp = await async_client.put(
        f"/api/v1/facilities/{facility.id}/capabilities",
        json=ALL_18_FLAGS_FALSE,
        headers=headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_put_capabilities_intake_staff_403(async_client, intake_user, db_session, org_a):
    """AC5: intake_staff gets 403 on PUT capabilities."""
    # @forgeplan-spec: AC5
    facility = await seed_facility(db_session)
    headers = make_auth_header("intake_staff", user_id=intake_user.id, org_id=TEST_ORG_ID_A)
    resp = await async_client.put(
        f"/api/v1/facilities/{facility.id}/capabilities",
        json=ALL_18_FLAGS_FALSE,
        headers=headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_put_capabilities_read_only_403(async_client, read_only_user, db_session, org_a):
    """AC5: read_only gets 403 on PUT capabilities."""
    # @forgeplan-spec: AC5
    facility = await seed_facility(db_session)
    headers = make_auth_header("read_only", user_id=read_only_user.id, org_id=TEST_ORG_ID_A)
    resp = await async_client.put(
        f"/api/v1/facilities/{facility.id}/capabilities",
        json=ALL_18_FLAGS_FALSE,
        headers=headers,
    )
    assert resp.status_code == 403


# ── AC9: All 18 flags stored ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_put_capabilities_stores_all_18_flags(async_client, admin_user, db_session, org_a):
    """AC9: PUT capabilities response contains all 18 boolean flags."""
    # @forgeplan-spec: AC9
    facility = await seed_facility(db_session)
    headers = make_auth_header("admin", user_id=admin_user.id, org_id=TEST_ORG_ID_A)
    resp = await async_client.put(
        f"/api/v1/facilities/{facility.id}/capabilities",
        json=ALL_18_FLAGS_TRUE,
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    for flag in ALL_18_FLAGS_TRUE:
        assert flag in data, f"Missing flag: {flag}"
        assert data[flag] is True, f"Flag {flag} should be True"


# ── AC12: last_verified_at updated on PUT capabilities ───────────────────────

@pytest.mark.asyncio
async def test_put_capabilities_sets_last_verified_at(async_client, admin_user, db_session, org_a):
    """AC12: last_verified_at set to within 2 seconds of now on PUT capabilities."""
    # @forgeplan-spec: AC12
    facility = await seed_facility(db_session)
    before = datetime.now(timezone.utc)

    headers = make_auth_header("admin", user_id=admin_user.id, org_id=TEST_ORG_ID_A)
    resp = await async_client.put(
        f"/api/v1/facilities/{facility.id}/capabilities",
        json=ALL_18_FLAGS_TRUE,
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["last_verified_at"] is not None

    lva = datetime.fromisoformat(data["last_verified_at"].replace("Z", "+00:00"))
    if lva.tzinfo is None:
        lva = lva.replace(tzinfo=timezone.utc)
    after = datetime.now(timezone.utc)
    assert before - timedelta(seconds=2) <= lva <= after + timedelta(seconds=2), (
        f"last_verified_at {lva} should be close to now ({before}–{after})"
    )


@pytest.mark.asyncio
async def test_put_capabilities_upsert_overwrites(async_client, admin_user, db_session, org_a):
    """AC12: second PUT upserts and overwrites first values; no unique constraint error."""
    # @forgeplan-spec: AC12
    facility = await seed_facility(db_session)
    headers = make_auth_header("admin", user_id=admin_user.id, org_id=TEST_ORG_ID_A)

    # First PUT — all True
    resp1 = await async_client.put(
        f"/api/v1/facilities/{facility.id}/capabilities",
        json=ALL_18_FLAGS_TRUE,
        headers=headers,
    )
    assert resp1.status_code == 200
    assert resp1.json()["accepts_trach"] is True

    # Second PUT — all False
    resp2 = await async_client.put(
        f"/api/v1/facilities/{facility.id}/capabilities",
        json=ALL_18_FLAGS_FALSE,
        headers=headers,
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["accepts_trach"] is False
    # IDs should be the same (upsert, not new row)
    assert resp1.json()["id"] == data2["id"]
