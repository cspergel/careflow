# @forgeplan-node: facilities-module
"""
Tests for AC1-AC4 (Facility CRUD) and AC9-AC11 (data model assertions).

AC1: GET /facilities — all roles, filters work
AC2: POST /facilities — admin only, 403 for others
AC3: GET /facilities/{id} — full profile with nested objects
AC4: PATCH /facilities/{id} — admin only, 403 for others
AC9: FacilityCapabilities has all 18 boolean flags
AC10: FacilityContact stores Phase 2 voice fields
AC11: facility_preferences support global/market/hospital scope
"""
# @forgeplan-spec: AC1
# @forgeplan-spec: AC2
# @forgeplan-spec: AC3
# @forgeplan-spec: AC4
# @forgeplan-spec: AC9
# @forgeplan-spec: AC10
# @forgeplan-spec: AC11

import pytest
from uuid import uuid4

from placementops.modules.facilities.tests.conftest import (
    TEST_ORG_ID_A,
    make_auth_header,
    seed_capabilities,
    seed_contact,
    seed_facility,
    seed_insurance_rule,
    seed_preference,
)


# ── AC1: GET /facilities ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_facilities_returns_all_for_org(async_client, admin_user, db_session, org_a):
    """AC1: all 5 seeded facilities returned for org A admin."""
    # @forgeplan-spec: AC1
    for i in range(5):
        await seed_facility(db_session, facility_name=f"Facility {i}")

    headers = make_auth_header("admin", user_id=admin_user.id, org_id=TEST_ORG_ID_A)
    resp = await async_client.get("/api/v1/facilities", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 5
    assert len(data["facilities"]) == 5


@pytest.mark.asyncio
async def test_list_facilities_intake_staff_can_read(async_client, intake_user, db_session, org_a):
    """AC1: intake_staff can read the directory."""
    # @forgeplan-spec: AC1
    await seed_facility(db_session)
    headers = make_auth_header("intake_staff", user_id=intake_user.id, org_id=TEST_ORG_ID_A)
    resp = await async_client.get("/api/v1/facilities", headers=headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_facilities_filter_by_type(async_client, admin_user, db_session, org_a):
    """AC1: facility_type filter returns only SNF facilities."""
    # @forgeplan-spec: AC1
    await seed_facility(db_session, facility_type="snf", facility_name="SNF One")
    await seed_facility(db_session, facility_type="irf", facility_name="IRF One")
    await seed_facility(db_session, facility_type="ltach", facility_name="LTACH One")

    headers = make_auth_header("admin", user_id=admin_user.id, org_id=TEST_ORG_ID_A)
    resp = await async_client.get("/api/v1/facilities?facility_type=snf", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert all(f["facility_type"] == "snf" for f in data["facilities"])


@pytest.mark.asyncio
async def test_list_facilities_filter_by_capability(async_client, admin_user, db_session, org_a):
    """AC1: accepts_trach filter returns only facilities with accepts_trach=true."""
    # @forgeplan-spec: AC1
    f1 = await seed_facility(db_session, facility_name="Trach Facility")
    f2 = await seed_facility(db_session, facility_name="No Trach Facility")
    await seed_capabilities(db_session, f1.id, accepts_trach=True)
    await seed_capabilities(db_session, f2.id, accepts_trach=False)

    headers = make_auth_header("admin", user_id=admin_user.id, org_id=TEST_ORG_ID_A)
    resp = await async_client.get("/api/v1/facilities?accepts_trach=true", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    ids = [f["id"] for f in data["facilities"]]
    assert f1.id in ids
    assert f2.id not in ids


@pytest.mark.asyncio
async def test_list_facilities_unauthenticated_401(async_client, org_a):
    """GET /facilities without token returns 401."""
    resp = await async_client.get("/api/v1/facilities")
    assert resp.status_code == 401


# ── AC2: POST /facilities ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_facility_admin_201(async_client, admin_user, org_a):
    """AC2: admin can create a facility (201)."""
    # @forgeplan-spec: AC2
    headers = make_auth_header("admin", user_id=admin_user.id, org_id=TEST_ORG_ID_A)
    payload = {"facility_name": "New SNF", "facility_type": "snf"}
    resp = await async_client.post("/api/v1/facilities", json=payload, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["facility_name"] == "New SNF"
    assert data["facility_type"] == "snf"


@pytest.mark.asyncio
async def test_create_facility_coordinator_403(async_client, coordinator_user, org_a):
    """AC2: placement_coordinator gets 403 on POST /facilities."""
    # @forgeplan-spec: AC2
    headers = make_auth_header("placement_coordinator", user_id=coordinator_user.id, org_id=TEST_ORG_ID_A)
    payload = {"facility_name": "New SNF", "facility_type": "snf"}
    resp = await async_client.post("/api/v1/facilities", json=payload, headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_facility_intake_403(async_client, intake_user, org_a):
    """AC2: intake_staff gets 403 on POST /facilities."""
    # @forgeplan-spec: AC2
    headers = make_auth_header("intake_staff", user_id=intake_user.id, org_id=TEST_ORG_ID_A)
    payload = {"facility_name": "New SNF", "facility_type": "snf"}
    resp = await async_client.post("/api/v1/facilities", json=payload, headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_facility_manager_403(async_client, manager_user, org_a):
    """AC2: manager gets 403 on POST /facilities."""
    # @forgeplan-spec: AC2
    headers = make_auth_header("manager", user_id=manager_user.id, org_id=TEST_ORG_ID_A)
    payload = {"facility_name": "New SNF", "facility_type": "snf"}
    resp = await async_client.post("/api/v1/facilities", json=payload, headers=headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_facility_invalid_type_422(async_client, admin_user, org_a):
    """POST /facilities with invalid facility_type returns 422."""
    headers = make_auth_header("admin", user_id=admin_user.id, org_id=TEST_ORG_ID_A)
    payload = {"facility_name": "Bad Facility", "facility_type": "hospital"}
    resp = await async_client.post("/api/v1/facilities", json=payload, headers=headers)
    assert resp.status_code == 422


# ── AC3: GET /facilities/{id} ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_facility_detail_all_nested_objects(
    async_client, clinical_user, db_session, org_a, payer
):
    """AC3: full profile with capabilities, 2 contacts, 1 insurance rule, 1 preference."""
    # @forgeplan-spec: AC3
    facility = await seed_facility(db_session)
    await seed_capabilities(db_session, facility.id)
    await seed_contact(db_session, facility.id, contact_name="Contact A")
    await seed_contact(db_session, facility.id, contact_name="Contact B")
    await seed_insurance_rule(db_session, facility.id)
    await seed_preference(db_session, facility.id, scope="global", preference_rank=1)

    headers = make_auth_header("clinical_reviewer", user_id=clinical_user.id, org_id=TEST_ORG_ID_A)
    resp = await async_client.get(f"/api/v1/facilities/{facility.id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["id"] == facility.id
    assert data["capabilities"] is not None
    assert len(data["contacts"]) == 2
    assert len(data["insurance_rules"]) == 1
    assert len(data["preferences"]) == 1


@pytest.mark.asyncio
async def test_get_facility_detail_read_only(async_client, read_only_user, db_session, org_a):
    """AC3: read_only role can read full facility profile."""
    # @forgeplan-spec: AC3
    facility = await seed_facility(db_session)
    headers = make_auth_header("read_only", user_id=read_only_user.id, org_id=TEST_ORG_ID_A)
    resp = await async_client.get(f"/api/v1/facilities/{facility.id}", headers=headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_facility_detail_404(async_client, admin_user, org_a):
    """AC3: 404 returned for non-existent facility_id."""
    headers = make_auth_header("admin", user_id=admin_user.id, org_id=TEST_ORG_ID_A)
    resp = await async_client.get(f"/api/v1/facilities/{uuid4()}", headers=headers)
    assert resp.status_code == 404


# ── AC4: PATCH /facilities/{id} ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_patch_facility_admin_200(async_client, admin_user, db_session, org_a):
    """AC4: admin can PATCH facility (200) and name is updated."""
    # @forgeplan-spec: AC4
    facility = await seed_facility(db_session, facility_name="Original Name")
    headers = make_auth_header("admin", user_id=admin_user.id, org_id=TEST_ORG_ID_A)
    resp = await async_client.patch(
        f"/api/v1/facilities/{facility.id}",
        json={"facility_name": "New Name"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["facility_name"] == "New Name"


@pytest.mark.asyncio
async def test_patch_facility_coordinator_403(async_client, coordinator_user, db_session, org_a):
    """AC4: placement_coordinator gets 403 on PATCH."""
    # @forgeplan-spec: AC4
    facility = await seed_facility(db_session)
    headers = make_auth_header("placement_coordinator", user_id=coordinator_user.id, org_id=TEST_ORG_ID_A)
    resp = await async_client.patch(
        f"/api/v1/facilities/{facility.id}",
        json={"facility_name": "Hacked Name"},
        headers=headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_patch_facility_manager_403(async_client, manager_user, db_session, org_a):
    """AC4: manager gets 403 on PATCH."""
    # @forgeplan-spec: AC4
    facility = await seed_facility(db_session)
    headers = make_auth_header("manager", user_id=manager_user.id, org_id=TEST_ORG_ID_A)
    resp = await async_client.patch(
        f"/api/v1/facilities/{facility.id}",
        json={"facility_name": "Hacked Name"},
        headers=headers,
    )
    assert resp.status_code == 403


# ── AC9: FacilityCapabilities has exactly 18 boolean flags ───────────────────

@pytest.mark.asyncio
async def test_capabilities_response_has_all_18_flags(async_client, admin_user, db_session, org_a):
    """AC9: GET /facilities/{id} capabilities field contains all 18 boolean flags."""
    # @forgeplan-spec: AC9
    expected_flags = {
        "accepts_snf", "accepts_irf", "accepts_ltach",
        "accepts_trach", "accepts_vent", "accepts_hd",
        "in_house_hemodialysis", "accepts_peritoneal_dialysis",
        "accepts_wound_vac", "accepts_iv_antibiotics", "accepts_tpn",
        "accepts_bariatric", "accepts_behavioral_complexity",
        "accepts_memory_care", "accepts_isolation_cases",
        "accepts_oxygen_therapy", "weekend_admissions", "after_hours_admissions",
    }
    facility = await seed_facility(db_session)
    await seed_capabilities(db_session, facility.id)

    headers = make_auth_header("admin", user_id=admin_user.id, org_id=TEST_ORG_ID_A)
    resp = await async_client.get(f"/api/v1/facilities/{facility.id}", headers=headers)
    assert resp.status_code == 200
    caps = resp.json()["capabilities"]
    assert caps is not None

    caps_keys = set(caps.keys())
    missing = expected_flags - caps_keys
    assert not missing, f"Missing capability flags in response: {missing}"


# ── AC10: FacilityContact stores Phase 2 voice fields ────────────────────────

@pytest.mark.asyncio
async def test_contact_phase2_voice_fields_persisted(async_client, admin_user, db_session, org_a):
    """AC10: POST /contacts with phone_extension, best_call_window, phone_contact_name."""
    # @forgeplan-spec: AC10
    facility = await seed_facility(db_session)
    headers = make_auth_header("admin", user_id=admin_user.id, org_id=TEST_ORG_ID_A)
    payload = {
        "contact_name": "Jane",
        "phone_extension": "101",
        "best_call_window": "9am-11am EST",
        "phone_contact_name": "Jane",
    }
    resp = await async_client.post(
        f"/api/v1/facilities/{facility.id}/contacts", json=payload, headers=headers
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["phone_extension"] == "101"
    assert data["best_call_window"] == "9am-11am EST"
    assert data["phone_contact_name"] == "Jane"


@pytest.mark.asyncio
async def test_contact_phase2_fields_returned_in_detail(async_client, admin_user, db_session, org_a):
    """AC10: Phase 2 voice fields returned in GET /facilities/{id} contacts list."""
    # @forgeplan-spec: AC10
    facility = await seed_facility(db_session)
    await seed_contact(
        db_session,
        facility.id,
        contact_name="Jane",
        phone_extension="101",
        best_call_window="9am-11am EST",
        phone_contact_name="Jane",
    )

    headers = make_auth_header("admin", user_id=admin_user.id, org_id=TEST_ORG_ID_A)
    resp = await async_client.get(f"/api/v1/facilities/{facility.id}", headers=headers)
    assert resp.status_code == 200
    contacts = resp.json()["contacts"]
    assert len(contacts) == 1
    contact = contacts[0]
    assert contact["phone_extension"] == "101"
    assert contact["best_call_window"] == "9am-11am EST"
    assert contact["phone_contact_name"] == "Jane"


# ── AC11: facility_preferences support scope and rank ────────────────────────

@pytest.mark.asyncio
async def test_preferences_global_and_hospital_scope(async_client, admin_user, db_session, org_a):
    """AC11: global and hospital scope preferences returned with correct rank."""
    # @forgeplan-spec: AC11
    facility = await seed_facility(db_session)
    hosp_ref_id = str(uuid4())
    await seed_preference(db_session, facility.id, scope="global", preference_rank=1)
    await seed_preference(
        db_session,
        facility.id,
        scope="hospital",
        preference_rank=2,
        scope_reference_id=hosp_ref_id,
    )

    headers = make_auth_header("admin", user_id=admin_user.id, org_id=TEST_ORG_ID_A)
    resp = await async_client.get(f"/api/v1/facilities/{facility.id}", headers=headers)
    assert resp.status_code == 200
    prefs = resp.json()["preferences"]
    assert len(prefs) == 2
    scopes = {p["scope"] for p in prefs}
    assert scopes == {"global", "hospital"}
    ranks = {p["preference_rank"] for p in prefs}
    assert ranks == {1, 2}
    hospital_pref = next(p for p in prefs if p["scope"] == "hospital")
    assert hospital_pref["scope_reference_id"] == hosp_ref_id
