# @forgeplan-node: facilities-module
"""
Tests for AC13 — organization_id isolation (RLS enforcement at application layer).

The application layer filters all facility queries by organization_id, providing
defense-in-depth against cross-org data access even when Supabase RLS is disabled
in test environments.
"""
# @forgeplan-spec: AC13

import pytest
from uuid import uuid4

from placementops.modules.facilities.tests.conftest import (
    TEST_ORG_ID_A,
    TEST_ORG_ID_B,
    TEST_PAYER_ID,
    make_auth_header,
    seed_facility,
    seed_insurance_rule,
    seed_org,
    seed_payer,
    seed_user,
)


# ── AC13: cross-org facility reads return 404 ─────────────────────────────────

@pytest.mark.asyncio
async def test_org_a_cannot_read_org_b_facility(
    async_client, admin_user, db_session, org_a, org_b
):
    """AC13: org A user gets 404 when requesting org B facility_id."""
    # @forgeplan-spec: AC13
    # Seed a facility for org B
    org_b_facility = await seed_facility(db_session, org_id=TEST_ORG_ID_B, facility_name="Org B Facility")

    # Authenticate as org A admin and try to GET org B facility
    headers = make_auth_header("admin", user_id=admin_user.id, org_id=TEST_ORG_ID_A)
    resp = await async_client.get(f"/api/v1/facilities/{org_b_facility.id}", headers=headers)
    # Org A user cannot see org B row — 404 (row not visible)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_org_a_cannot_list_org_b_facilities(
    async_client, admin_user, db_session, org_a, org_b
):
    """AC13: org A user listing /facilities does not see org B facilities."""
    # @forgeplan-spec: AC13
    # Seed facilities for both orgs
    org_a_fac = await seed_facility(db_session, org_id=TEST_ORG_ID_A, facility_name="Org A Facility")
    org_b_fac = await seed_facility(db_session, org_id=TEST_ORG_ID_B, facility_name="Org B Facility")

    headers = make_auth_header("admin", user_id=admin_user.id, org_id=TEST_ORG_ID_A)
    resp = await async_client.get("/api/v1/facilities", headers=headers)
    assert resp.status_code == 200
    ids = [f["id"] for f in resp.json()["facilities"]]
    assert org_a_fac.id in ids
    assert org_b_fac.id not in ids


@pytest.mark.asyncio
async def test_org_a_cannot_patch_org_b_facility(
    async_client, admin_user, db_session, org_a, org_b
):
    """AC13: org A admin gets 404 attempting to PATCH org B facility."""
    # @forgeplan-spec: AC13
    org_b_facility = await seed_facility(db_session, org_id=TEST_ORG_ID_B, facility_name="Org B Facility")
    headers = make_auth_header("admin", user_id=admin_user.id, org_id=TEST_ORG_ID_A)
    resp = await async_client.patch(
        f"/api/v1/facilities/{org_b_facility.id}",
        json={"facility_name": "Hijacked Name"},
        headers=headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_org_a_cannot_upsert_capabilities_for_org_b(
    async_client, admin_user, db_session, org_a, org_b
):
    """AC13: org A admin gets 404 attempting to PUT capabilities for org B facility."""
    # @forgeplan-spec: AC13
    org_b_facility = await seed_facility(db_session, org_id=TEST_ORG_ID_B)
    headers = make_auth_header("admin", user_id=admin_user.id, org_id=TEST_ORG_ID_A)
    payload = {
        "accepts_snf": True,
        "accepts_irf": False,
        "accepts_ltach": False,
        "accepts_trach": False,
        "accepts_vent": False,
        "accepts_hd": False,
        "in_house_hemodialysis": False,
        "accepts_peritoneal_dialysis": False,
        "accepts_wound_vac": False,
        "accepts_iv_antibiotics": False,
        "accepts_tpn": False,
        "accepts_bariatric": False,
        "accepts_behavioral_complexity": False,
        "accepts_memory_care": False,
        "accepts_isolation_cases": False,
        "accepts_oxygen_therapy": False,
        "weekend_admissions": False,
        "after_hours_admissions": False,
    }
    resp = await async_client.put(
        f"/api/v1/facilities/{org_b_facility.id}/capabilities",
        json=payload,
        headers=headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_org_a_cannot_list_org_b_insurance_rules(
    async_client, admin_user, db_session, org_a, org_b
):
    """AC13: GET insurance-rules for org B facility returns 404 to org A user."""
    # @forgeplan-spec: AC13
    # Must seed payer for org_b context
    payer = await seed_payer(db_session)
    org_b_facility = await seed_facility(db_session, org_id=TEST_ORG_ID_B)
    await seed_insurance_rule(db_session, org_b_facility.id)

    headers = make_auth_header("admin", user_id=admin_user.id, org_id=TEST_ORG_ID_A)
    resp = await async_client.get(
        f"/api/v1/facilities/{org_b_facility.id}/insurance-rules",
        headers=headers,
    )
    # The facility is not visible to org A — returns 404
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_org_b_user_sees_own_facilities_only(
    async_client, db_session, org_a, org_b
):
    """AC13: org B user only sees org B facilities in the list endpoint."""
    # @forgeplan-spec: AC13
    org_b_user = await seed_user(db_session, "admin", org_id=TEST_ORG_ID_B)
    org_a_fac = await seed_facility(db_session, org_id=TEST_ORG_ID_A, facility_name="Org A Facility")
    org_b_fac = await seed_facility(db_session, org_id=TEST_ORG_ID_B, facility_name="Org B Facility")

    headers = make_auth_header("admin", user_id=org_b_user.id, org_id=TEST_ORG_ID_B)
    resp = await async_client.get("/api/v1/facilities", headers=headers)
    assert resp.status_code == 200
    ids = [f["id"] for f in resp.json()["facilities"]]
    assert org_b_fac.id in ids
    assert org_a_fac.id not in ids
