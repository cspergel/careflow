# @forgeplan-node: clinical-module
"""
AC6, AC7 — Assessment finalization tests.

AC6: finalizing advances case to ready_for_matching and writes AuditEvent
AC7: finalizing without recommended_level_of_care returns 422
"""
# @forgeplan-spec: AC6
# @forgeplan-spec: AC7

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.models import AuditEvent, CaseStatusHistory, PatientCase
from placementops.modules.clinical.tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_finalize_assessment_advances_case_to_ready_for_matching(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org: str,
    clinical_reviewer: dict,
    under_review_case: PatientCase,
):
    """
    AC6: finalize assessment with recommended_level_of_care=snf;
    assert PatientCase.current_status=ready_for_matching,
    AuditEvent written with event_type=assessment_finalized,
    case_status_history row created.
    """
    headers = auth_headers(
        clinical_reviewer["user_id"],
        clinical_reviewer["org_id"],
        "clinical_reviewer",
    )

    # Create draft
    draft_resp = await client.post(
        f"/api/v1/cases/{under_review_case.id}/assessments",
        json={"recommended_level_of_care": "snf"},
        headers=headers,
    )
    assert draft_resp.status_code == 201
    draft_id = draft_resp.json()["id"]

    # Finalize
    final_resp = await client.patch(
        f"/api/v1/assessments/{draft_id}",
        json={"review_status": "finalized", "recommended_level_of_care": "snf"},
        headers=headers,
    )
    assert final_resp.status_code == 200, final_resp.text
    assert final_resp.json()["review_status"] == "finalized"

    # Case must be ready_for_matching
    await db_session.refresh(under_review_case)
    assert under_review_case.current_status == "ready_for_matching"

    # AuditEvent with assessment_finalized
    audit_result = await db_session.execute(
        select(AuditEvent).where(
            AuditEvent.event_type == "assessment_finalized"
        )
    )
    audit_rows = audit_result.scalars().all()
    assert len(audit_rows) >= 1, "AuditEvent with event_type=assessment_finalized must be written"

    # case_status_history row for ready_for_matching transition
    history_result = await db_session.execute(
        select(CaseStatusHistory).where(
            CaseStatusHistory.patient_case_id == under_review_case.id,
            CaseStatusHistory.to_status == "ready_for_matching",
        )
    )
    history_rows = history_result.scalars().all()
    assert len(history_rows) >= 1, "CaseStatusHistory row for ready_for_matching must exist"


@pytest.mark.asyncio
async def test_finalize_without_loc_returns_422(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org: str,
    clinical_reviewer: dict,
    under_review_case: PatientCase,
):
    """
    AC7: PATCH with review_status=finalized but no recommended_level_of_care → 422.
    Case status must remain unchanged.
    """
    headers = auth_headers(
        clinical_reviewer["user_id"],
        clinical_reviewer["org_id"],
        "clinical_reviewer",
    )

    # Create draft without loc
    draft_resp = await client.post(
        f"/api/v1/cases/{under_review_case.id}/assessments",
        json={},
        headers=headers,
    )
    assert draft_resp.status_code == 201
    draft_id = draft_resp.json()["id"]

    # Try to finalize without loc
    final_resp = await client.patch(
        f"/api/v1/assessments/{draft_id}",
        json={"review_status": "finalized"},
        headers=headers,
    )
    assert final_resp.status_code == 422, final_resp.text

    # Case status unchanged
    await db_session.refresh(under_review_case)
    assert under_review_case.current_status == "under_clinical_review"


@pytest.mark.asyncio
async def test_finalize_with_empty_loc_returns_422(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org: str,
    clinical_reviewer: dict,
    under_review_case: PatientCase,
):
    """
    AC7: empty string recommended_level_of_care on finalization also returns 422.
    """
    headers = auth_headers(
        clinical_reviewer["user_id"],
        clinical_reviewer["org_id"],
        "clinical_reviewer",
    )
    draft_resp = await client.post(
        f"/api/v1/cases/{under_review_case.id}/assessments",
        json={"recommended_level_of_care": ""},
        headers=headers,
    )
    assert draft_resp.status_code == 201
    draft_id = draft_resp.json()["id"]

    final_resp = await client.patch(
        f"/api/v1/assessments/{draft_id}",
        json={"review_status": "finalized", "recommended_level_of_care": ""},
        headers=headers,
    )
    assert final_resp.status_code == 422, final_resp.text
