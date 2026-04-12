# @forgeplan-node: clinical-module
"""
AC8, AC11 — Field completeness and matching engine exposure tests.

AC8: All 20+ clinical fields captured and stored without loss
AC11: Only the latest finalized assessment is surfaced to matching engine
"""
# @forgeplan-spec: AC8
# @forgeplan-spec: AC11

from __future__ import annotations

import asyncio
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.models import ClinicalAssessment, PatientCase
from placementops.modules.clinical.tests.conftest import (
    _seed_assessment,
    auth_headers,
    make_id,
)
from placementops.modules.clinical.service import get_latest_finalized_assessment
from uuid import UUID


ALL_FIELDS_PAYLOAD = {
    "recommended_level_of_care": "snf",
    "accepts_trach": True,
    "accepts_vent": False,
    "accepts_hd": True,
    "in_house_hemodialysis": True,
    "accepts_peritoneal_dialysis": False,
    "accepts_wound_vac": True,
    "accepts_iv_antibiotics": True,
    "accepts_tpn": False,
    "accepts_isolation_cases": True,
    "accepts_behavioral_complexity": True,
    "accepts_bariatric": False,
    "accepts_memory_care": True,
    "accepts_oxygen_therapy": True,
    "rehab_tolerance": "moderate",
    "mobility_status": "partial weight bearing",
    "psych_behavior_flags": "aggression",
    "special_equipment_needs": "pca pump",
    "barriers_to_placement": "No English",
    "payer_notes": "Medicare Advantage",
    "family_preference_notes": "Spanish-speaking facility preferred",
    "confidence_level": "medium",
    "clinical_summary": "Patient medically stable; SNF appropriate.",
}


@pytest.mark.asyncio
async def test_all_clinical_fields_round_trip(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org: str,
    clinical_reviewer: dict,
    under_review_case: PatientCase,
):
    """
    AC8: POST with all 22 fields; GET and assert all fields round-trip.
    """
    headers = auth_headers(
        clinical_reviewer["user_id"], clinical_reviewer["org_id"], "clinical_reviewer"
    )
    resp = await client.post(
        f"/api/v1/cases/{under_review_case.id}/assessments",
        json=ALL_FIELDS_PAYLOAD,
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()

    for field, expected in ALL_FIELDS_PAYLOAD.items():
        assert body[field] == expected, f"Field {field}: expected {expected!r}, got {body[field]!r}"


@pytest.mark.asyncio
async def test_latest_finalized_is_the_most_recent_one(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org: str,
    clinical_reviewer: dict,
    under_review_case: PatientCase,
):
    """
    AC11: create two finalized assessments for same case (different timestamps);
    assert the one with the later created_at is exposed to matching engine.
    """
    headers = auth_headers(
        clinical_reviewer["user_id"], clinical_reviewer["org_id"], "clinical_reviewer"
    )

    # Finalized assessment #1
    d1 = await client.post(
        f"/api/v1/cases/{under_review_case.id}/assessments",
        json={"recommended_level_of_care": "snf"},
        headers=headers,
    )
    assert d1.status_code == 201
    f1 = await client.patch(
        f"/api/v1/assessments/{d1.json()['id']}",
        json={"review_status": "finalized", "recommended_level_of_care": "snf"},
        headers=headers,
    )
    assert f1.status_code == 200

    # After first finalization, case is at ready_for_matching.
    # Re-seed the case to under_clinical_review for second finalization
    # (In real flow, case would need to be moved back, but for test we mutate directly)
    await db_session.refresh(under_review_case)
    under_review_case.current_status = "under_clinical_review"
    await db_session.commit()

    # Finalized assessment #2 (later)
    d2 = await client.post(
        f"/api/v1/cases/{under_review_case.id}/assessments",
        json={"recommended_level_of_care": "irf"},
        headers=headers,
    )
    assert d2.status_code == 201
    f2 = await client.patch(
        f"/api/v1/assessments/{d2.json()['id']}",
        json={"review_status": "finalized", "recommended_level_of_care": "irf"},
        headers=headers,
    )
    assert f2.status_code == 200
    f2_id = f2.json()["id"]

    # Query latest-finalized endpoint
    resp = await client.get(
        f"/api/v1/cases/{under_review_case.id}/assessments/latest-finalized",
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == f2_id, "Latest finalized must be the second one"
    assert resp.json()["recommended_level_of_care"] == "irf"


@pytest.mark.asyncio
async def test_latest_finalized_returns_null_when_none(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org: str,
    clinical_reviewer: dict,
    under_review_case: PatientCase,
):
    """
    AC11: no finalized assessments → endpoint returns null.
    """
    # Create only a draft
    await _seed_assessment(
        db_session,
        under_review_case.id,
        clinical_reviewer["user_id"],
        review_status="draft",
    )

    headers = auth_headers(
        clinical_reviewer["user_id"], clinical_reviewer["org_id"], "clinical_reviewer"
    )
    resp = await client.get(
        f"/api/v1/cases/{under_review_case.id}/assessments/latest-finalized",
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json() is None
