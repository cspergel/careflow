# @forgeplan-node: clinical-module
"""
AC3, AC4, AC5 — Assessment CRUD and versioning tests.

AC3: POST creates draft; no status change
AC4: PATCH creates new version; previous row preserved
AC5: GET returns all versions ordered by created_at
"""
# @forgeplan-spec: AC3
# @forgeplan-spec: AC4
# @forgeplan-spec: AC5

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.models import ClinicalAssessment, PatientCase
from placementops.modules.clinical.tests.conftest import (
    _seed_assessment,
    _seed_case,
    auth_headers,
)

ALL_CLINICAL_FIELDS = {
    "recommended_level_of_care": "snf",
    "accepts_trach": True,
    "accepts_vent": False,
    "accepts_hd": True,
    "in_house_hemodialysis": False,
    "accepts_peritoneal_dialysis": True,
    "accepts_wound_vac": True,
    "accepts_iv_antibiotics": True,
    "accepts_tpn": False,
    "accepts_isolation_cases": True,
    "accepts_behavioral_complexity": False,
    "accepts_bariatric": True,
    "accepts_memory_care": False,
    "accepts_oxygen_therapy": True,
    "rehab_tolerance": "moderate",
    "mobility_status": "ambulatory",
    "psych_behavior_flags": "agitation",
    "special_equipment_needs": "hoyer lift",
    "barriers_to_placement": "insurance issues",
    "payer_notes": "Medicare A",
    "family_preference_notes": "close to family in zip 90210",
    "confidence_level": "high",
    "clinical_summary": "Patient is stable and ready for SNF placement.",
}


# ---------------------------------------------------------------------------
# AC3 — Create draft assessment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_draft_assessment(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org: str,
    clinical_reviewer: dict,
    under_review_case: PatientCase,
):
    """
    AC3: POST /cases/{id}/assessments creates a draft with correct fields.
    No PatientCase status change occurs at draft creation.
    """
    headers = auth_headers(
        clinical_reviewer["user_id"],
        clinical_reviewer["org_id"],
        "clinical_reviewer",
    )
    resp = await client.post(
        f"/api/v1/cases/{under_review_case.id}/assessments",
        json={"recommended_level_of_care": "irf"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text

    body = resp.json()
    assert body["review_status"] == "draft"
    assert body["patient_case_id"] == under_review_case.id
    assert body["reviewer_user_id"] == clinical_reviewer["user_id"]

    # No case status change
    await db_session.refresh(under_review_case)
    assert under_review_case.current_status == "under_clinical_review"


@pytest.mark.asyncio
async def test_create_assessment_all_fields_round_trip(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org: str,
    clinical_reviewer: dict,
    under_review_case: PatientCase,
):
    """
    AC8: All 20+ clinical fields round-trip correctly.
    """
    headers = auth_headers(
        clinical_reviewer["user_id"],
        clinical_reviewer["org_id"],
        "clinical_reviewer",
    )
    resp = await client.post(
        f"/api/v1/cases/{under_review_case.id}/assessments",
        json=ALL_CLINICAL_FIELDS,
        headers=headers,
    )
    assert resp.status_code == 201, resp.text

    body = resp.json()
    for field, expected in ALL_CLINICAL_FIELDS.items():
        assert body[field] == expected, f"Field {field}: expected {expected}, got {body[field]}"


# ---------------------------------------------------------------------------
# AC4 — PATCH creates new version row
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_creates_new_version_preserves_previous(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org: str,
    clinical_reviewer: dict,
    under_review_case: PatientCase,
):
    """
    AC4: PATCH three times; assert all three versions exist in DB.
    Previous rows must remain unmodified.
    """
    headers = auth_headers(
        clinical_reviewer["user_id"],
        clinical_reviewer["org_id"],
        "clinical_reviewer",
    )

    # Create initial draft
    r1 = await client.post(
        f"/api/v1/cases/{under_review_case.id}/assessments",
        json={"recommended_level_of_care": "snf", "rehab_tolerance": "low"},
        headers=headers,
    )
    assert r1.status_code == 201
    v1_id = r1.json()["id"]

    # PATCH #1
    r2 = await client.patch(
        f"/api/v1/assessments/{v1_id}",
        json={"rehab_tolerance": "moderate"},
        headers=headers,
    )
    assert r2.status_code == 200
    v2_id = r2.json()["id"]
    assert v2_id != v1_id, "PATCH must create a NEW row, not update in place"

    # PATCH #2
    r3 = await client.patch(
        f"/api/v1/assessments/{v2_id}",
        json={"rehab_tolerance": "high", "clinical_summary": "Updated summary"},
        headers=headers,
    )
    assert r3.status_code == 200
    v3_id = r3.json()["id"]
    assert v3_id != v2_id

    # Verify all three rows exist in DB
    result = await db_session.execute(
        select(ClinicalAssessment).where(
            ClinicalAssessment.patient_case_id == under_review_case.id
        )
    )
    all_rows = result.scalars().all()
    all_ids = {row.id for row in all_rows}
    assert v1_id in all_ids, "Version 1 must still exist in DB"
    assert v2_id in all_ids, "Version 2 must still exist in DB"
    assert v3_id in all_ids, "Version 3 must still exist in DB"

    # Verify v1 row is unchanged
    v1_row = next(r for r in all_rows if r.id == v1_id)
    assert v1_row.rehab_tolerance == "low", "Original v1 row must be unmodified"


@pytest.mark.asyncio
async def test_patch_returns_new_draft_not_finalized(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org: str,
    clinical_reviewer: dict,
    under_review_case: PatientCase,
):
    """
    AC4: PATCH without finalizing returns draft, not a finalized record.
    """
    headers = auth_headers(
        clinical_reviewer["user_id"],
        clinical_reviewer["org_id"],
        "clinical_reviewer",
    )
    r1 = await client.post(
        f"/api/v1/cases/{under_review_case.id}/assessments",
        json={"recommended_level_of_care": "snf"},
        headers=headers,
    )
    v1_id = r1.json()["id"]

    r2 = await client.patch(
        f"/api/v1/assessments/{v1_id}",
        json={"clinical_summary": "Updated"},
        headers=headers,
    )
    assert r2.status_code == 200
    assert r2.json()["review_status"] == "draft"


# ---------------------------------------------------------------------------
# AC5 — List all assessment versions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_assessments_returns_all_versions_ordered(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org: str,
    clinical_reviewer: dict,
    under_review_case: PatientCase,
):
    """
    AC5: GET /cases/{id}/assessments returns all versions ordered by created_at.
    Creates 2 drafts and 1 finalized; asserts all 3 returned with correct review_status.
    """
    headers = auth_headers(
        clinical_reviewer["user_id"],
        clinical_reviewer["org_id"],
        "clinical_reviewer",
    )

    # Create draft 1
    r1 = await client.post(
        f"/api/v1/cases/{under_review_case.id}/assessments",
        json={"recommended_level_of_care": "snf"},
        headers=headers,
    )
    assert r1.status_code == 201
    v1 = r1.json()

    # Create draft 2 via PATCH
    r2 = await client.patch(
        f"/api/v1/assessments/{v1['id']}",
        json={"clinical_summary": "Updated draft"},
        headers=headers,
    )
    assert r2.status_code == 200
    v2 = r2.json()

    # Finalize via PATCH
    r3 = await client.patch(
        f"/api/v1/assessments/{v2['id']}",
        json={"review_status": "finalized", "recommended_level_of_care": "snf"},
        headers=headers,
    )
    assert r3.status_code == 200
    v3 = r3.json()
    assert v3["review_status"] == "finalized"

    # GET all versions
    list_resp = await client.get(
        f"/api/v1/cases/{under_review_case.id}/assessments",
        headers=headers,
    )
    assert list_resp.status_code == 200
    data = list_resp.json()
    assert data["total"] == 3

    returned_ids = [a["id"] for a in data["assessments"]]
    assert v1["id"] in returned_ids
    assert v2["id"] in returned_ids
    assert v3["id"] in returned_ids

    # Verify correct review_status on each
    by_id = {a["id"]: a for a in data["assessments"]}
    assert by_id[v1["id"]]["review_status"] == "draft"
    assert by_id[v2["id"]]["review_status"] == "draft"
    assert by_id[v3["id"]]["review_status"] == "finalized"

    # Verify chronological order
    created_ats = [a["created_at"] for a in data["assessments"]]
    assert created_ats == sorted(created_ats), "Assessments must be in ascending created_at order"
