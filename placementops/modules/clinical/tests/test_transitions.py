# @forgeplan-node: clinical-module
"""
AC9 — Backward transition tests.

POST /api/v1/cases/{case_id}/clinical-transition
under_clinical_review → needs_clinical_review requires transition_reason.
"""
# @forgeplan-spec: AC9

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.models import AuditEvent, CaseStatusHistory, PatientCase
from placementops.modules.clinical.tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_backward_transition_requires_reason(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org: str,
    clinical_reviewer: dict,
    under_review_case: PatientCase,
):
    """
    AC9: POST without transition_reason → 400.
    """
    headers = auth_headers(
        clinical_reviewer["user_id"], clinical_reviewer["org_id"], "clinical_reviewer"
    )
    resp = await client.post(
        f"/api/v1/cases/{under_review_case.id}/clinical-transition",
        json={"to_status": "needs_clinical_review"},
        headers=headers,
    )
    assert resp.status_code in (400, 422), resp.text


@pytest.mark.asyncio
async def test_backward_transition_with_reason_succeeds(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org: str,
    clinical_reviewer: dict,
    under_review_case: PatientCase,
):
    """
    AC9: POST with valid transition_reason → 200;
    assert case_status_history and AuditEvent written.
    """
    headers = auth_headers(
        clinical_reviewer["user_id"], clinical_reviewer["org_id"], "clinical_reviewer"
    )
    resp = await client.post(
        f"/api/v1/cases/{under_review_case.id}/clinical-transition",
        json={
            "to_status": "needs_clinical_review",
            "transition_reason": "Missing clinical information; returned for intake completion.",
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["new_status"] == "needs_clinical_review"

    # Verify DB
    await db_session.refresh(under_review_case)
    assert under_review_case.current_status == "needs_clinical_review"

    # CaseStatusHistory row
    history_result = await db_session.execute(
        select(CaseStatusHistory).where(
            CaseStatusHistory.patient_case_id == under_review_case.id,
            CaseStatusHistory.to_status == "needs_clinical_review",
        )
    )
    rows = history_result.scalars().all()
    assert len(rows) >= 1, "CaseStatusHistory row must be written for backward transition"
    # transition_reason should be recorded
    assert any(r.transition_reason for r in rows), "transition_reason must be persisted in history"

    # AuditEvent for status_changed
    audit_result = await db_session.execute(
        select(AuditEvent).where(
            AuditEvent.entity_type == "patient_case",
            AuditEvent.entity_id == under_review_case.id,
            AuditEvent.event_type == "status_changed",
        )
    )
    audit_rows = audit_result.scalars().all()
    assert len(audit_rows) >= 1, "AuditEvent for status_changed must be written"


@pytest.mark.asyncio
async def test_backward_transition_reason_max_length(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org: str,
    clinical_reviewer: dict,
    under_review_case: PatientCase,
):
    """
    AC9 constraint: transition_reason max 1000 characters.
    """
    headers = auth_headers(
        clinical_reviewer["user_id"], clinical_reviewer["org_id"], "clinical_reviewer"
    )
    too_long = "x" * 1001
    resp = await client.post(
        f"/api/v1/cases/{under_review_case.id}/clinical-transition",
        json={"to_status": "needs_clinical_review", "transition_reason": too_long},
        headers=headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_coordinator_cannot_execute_clinical_transition(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org: str,
    coordinator_user: dict,
    under_review_case: PatientCase,
):
    """
    AC9: placement_coordinator is not permitted for backward clinical transitions.
    """
    headers = auth_headers(
        coordinator_user["user_id"], coordinator_user["org_id"], "placement_coordinator"
    )
    resp = await client.post(
        f"/api/v1/cases/{under_review_case.id}/clinical-transition",
        json={
            "to_status": "needs_clinical_review",
            "transition_reason": "Testing role enforcement",
        },
        headers=headers,
    )
    assert resp.status_code == 403
