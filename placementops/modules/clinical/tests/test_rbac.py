# @forgeplan-node: clinical-module
"""
AC10, AC12 — RBAC and closed-case tests.

AC10: intake_staff and placement_coordinator cannot create or finalize assessments
AC12: closed cases reject all write operations with 409
"""
# @forgeplan-spec: AC10
# @forgeplan-spec: AC12

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.models import PatientCase
from placementops.modules.clinical.tests.conftest import (
    _seed_assessment,
    auth_headers,
)


# ---------------------------------------------------------------------------
# AC10 — Role enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_intake_staff_cannot_create_assessment(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org: str,
    intake_user: dict,
    under_review_case: PatientCase,
):
    """
    AC10: POST /assessments as intake_staff → HTTP 403.
    """
    headers = auth_headers(intake_user["user_id"], intake_user["org_id"], "intake_staff")
    resp = await client.post(
        f"/api/v1/cases/{under_review_case.id}/assessments",
        json={"recommended_level_of_care": "snf"},
        headers=headers,
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_coordinator_cannot_finalize_assessment(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org: str,
    coordinator_user: dict,
    clinical_reviewer: dict,
    under_review_case: PatientCase,
):
    """
    AC10: PATCH assessment review_status=finalized as placement_coordinator → HTTP 403.
    """
    # Create a draft as clinical_reviewer
    cr_headers = auth_headers(
        clinical_reviewer["user_id"], clinical_reviewer["org_id"], "clinical_reviewer"
    )
    draft_resp = await client.post(
        f"/api/v1/cases/{under_review_case.id}/assessments",
        json={"recommended_level_of_care": "snf"},
        headers=cr_headers,
    )
    assert draft_resp.status_code == 201
    draft_id = draft_resp.json()["id"]

    # Attempt to finalize as placement_coordinator
    coord_headers = auth_headers(
        coordinator_user["user_id"], coordinator_user["org_id"], "placement_coordinator"
    )
    resp = await client.patch(
        f"/api/v1/assessments/{draft_id}",
        json={"review_status": "finalized", "recommended_level_of_care": "snf"},
        headers=coord_headers,
    )
    assert resp.status_code == 403, resp.text


# ---------------------------------------------------------------------------
# AC12 — Closed case rejects all assessment write operations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_closed_case_rejects_create_assessment(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org: str,
    clinical_reviewer: dict,
    closed_case: PatientCase,
):
    """
    AC12: POST /assessments on a closed case → 409.
    """
    headers = auth_headers(
        clinical_reviewer["user_id"], clinical_reviewer["org_id"], "clinical_reviewer"
    )
    resp = await client.post(
        f"/api/v1/cases/{closed_case.id}/assessments",
        json={"recommended_level_of_care": "snf"},
        headers=headers,
    )
    assert resp.status_code == 409, resp.text


@pytest.mark.asyncio
async def test_closed_case_rejects_patch_assessment(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org: str,
    clinical_reviewer: dict,
    closed_case: PatientCase,
):
    """
    AC12: PATCH /assessments/{id} where the case is closed → 409.
    Seeds assessment directly in DB to bypass the create-check.
    """
    # Seed an assessment directly for the closed case
    assessment = await _seed_assessment(
        db_session,
        closed_case.id,
        clinical_reviewer["user_id"],
        review_status="draft",
    )

    headers = auth_headers(
        clinical_reviewer["user_id"], clinical_reviewer["org_id"], "clinical_reviewer"
    )
    resp = await client.patch(
        f"/api/v1/assessments/{assessment.id}",
        json={"clinical_summary": "Attempting update on closed case"},
        headers=headers,
    )
    assert resp.status_code == 409, resp.text
