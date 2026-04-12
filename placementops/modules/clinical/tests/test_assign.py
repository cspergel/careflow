# @forgeplan-node: clinical-module
"""
AC2 — Assign clinical reviewer tests.

POST /api/v1/cases/{case_id}/assign assigns reviewer and advances
case to under_clinical_review.
"""
# @forgeplan-spec: AC2

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.models import CaseStatusHistory, PatientCase
from placementops.modules.clinical.tests.conftest import (
    _seed_case,
    _seed_user,
    auth_headers,
)


@pytest.mark.asyncio
async def test_assign_reviewer_advances_case_to_under_clinical_review(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org: str,
    clinical_reviewer: dict,
    clinical_case: PatientCase,
):
    """
    AC2: POST assign with valid clinical_reviewer user_id;
    assert PatientCase.current_status=under_clinical_review,
    case_status_history row written.
    """
    headers = auth_headers(
        clinical_reviewer["user_id"],
        clinical_reviewer["org_id"],
        "clinical_reviewer",
    )
    resp = await client.post(
        f"/api/v1/cases/{clinical_case.id}/assign",
        json={"user_id": clinical_reviewer["user_id"], "role": "clinical_reviewer"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["new_case_status"] == "under_clinical_review"
    assert body["assigned_user_id"] == clinical_reviewer["user_id"]

    # Verify DB state
    await db_session.refresh(clinical_case)
    assert clinical_case.current_status == "under_clinical_review"

    # Verify case_status_history row written
    history = await db_session.execute(
        select(CaseStatusHistory).where(
            CaseStatusHistory.patient_case_id == clinical_case.id
        )
    )
    rows = history.scalars().all()
    assert any(r.from_status == "needs_clinical_review" and r.to_status == "under_clinical_review" for r in rows), \
        "CaseStatusHistory row for the transition must exist"


@pytest.mark.asyncio
async def test_assign_non_clinical_reviewer_role_is_rejected(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org: str,
    clinical_reviewer: dict,
    intake_user: dict,
    clinical_case: PatientCase,
):
    """
    AC2: assigning a user with intake_staff role should fail with 422.
    Only clinical_reviewer or admin can be assigned via this endpoint.
    """
    headers = auth_headers(
        clinical_reviewer["user_id"],
        clinical_reviewer["org_id"],
        "clinical_reviewer",
    )
    resp = await client.post(
        f"/api/v1/cases/{clinical_case.id}/assign",
        json={"user_id": intake_user["user_id"], "role": "clinical_reviewer"},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_assign_requires_clinical_reviewer_or_admin_caller(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org: str,
    coordinator_user: dict,
    clinical_reviewer: dict,
    clinical_case: PatientCase,
):
    """
    AC2: a placement_coordinator cannot call the assign endpoint.
    """
    headers = auth_headers(
        coordinator_user["user_id"],
        coordinator_user["org_id"],
        "placement_coordinator",
    )
    resp = await client.post(
        f"/api/v1/cases/{clinical_case.id}/assign",
        json={"user_id": clinical_reviewer["user_id"], "role": "clinical_reviewer"},
        headers=headers,
    )
    assert resp.status_code == 403
