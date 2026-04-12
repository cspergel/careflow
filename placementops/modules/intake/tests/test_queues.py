# @forgeplan-node: intake-module
"""
Tests for the intake queue endpoint.

Covers: AC13
"""
# @forgeplan-spec: AC13

from __future__ import annotations

import os

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.models import PatientCase
from placementops.modules.intake.tests.conftest import auth_headers

os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret-key-minimum-32-chars-long")

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# AC13: GET /queues/intake
# ---------------------------------------------------------------------------


async def test_intake_queue_returns_intake_in_progress_cases(
    client, db_session: AsyncSession, seed_org, seed_hospital, seed_intake_user
):
    """AC13: seed 3 cases in intake_in_progress; GET /queues/intake → all 3 returned."""
    # Seed 3 intake_in_progress cases
    for i in range(3):
        case = PatientCase(
            organization_id=seed_org,
            hospital_id=seed_hospital,
            patient_name=f"Queue Patient {i}",
            current_status="intake_in_progress",
            active_case_flag=True,
            created_by_user_id=seed_intake_user["user_id"],
            updated_by_user_id=seed_intake_user["user_id"],
        )
        db_session.add(case)

    # Also seed 1 case in needs_clinical_review (should NOT appear in intake queue)
    other_case = PatientCase(
        organization_id=seed_org,
        hospital_id=seed_hospital,
        patient_name="Not In Queue",
        current_status="needs_clinical_review",
        active_case_flag=True,
        created_by_user_id=seed_intake_user["user_id"],
        updated_by_user_id=seed_intake_user["user_id"],
    )
    db_session.add(other_case)
    await db_session.commit()

    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )
    resp = await client.get("/api/v1/queues/intake", headers=headers)
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["total"] == 3
    assert len(body["cases"]) == 3
    assert all(c["current_status"] == "intake_in_progress" for c in body["cases"])


async def test_intake_queue_restricted_to_intake_staff_and_admin(
    client, db_session: AsyncSession, seed_org, seed_hospital, seed_coordinator_user
):
    """AC13: GET /queues/intake as placement_coordinator → 403."""
    headers = auth_headers(
        seed_coordinator_user["user_id"], seed_coordinator_user["org_id"], "placement_coordinator"
    )
    resp = await client.get("/api/v1/queues/intake", headers=headers)
    assert resp.status_code == 403


async def test_intake_queue_pagination_fields_present(
    client, db_session: AsyncSession, seed_org, seed_hospital, seed_intake_user
):
    """AC13: GET /queues/intake → pagination fields (total, page, page_size) present."""
    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )
    resp = await client.get("/api/v1/queues/intake?page=1&page_size=5", headers=headers)
    assert resp.status_code == 200

    body = resp.json()
    assert "total" in body
    assert "page" in body
    assert "page_size" in body
    assert body["page"] == 1
    assert body["page_size"] == 5


async def test_intake_queue_empty_when_no_cases(
    client, db_session: AsyncSession, seed_org, seed_intake_user
):
    """AC13: empty org → GET /queues/intake → total==0, cases==[]."""
    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )
    resp = await client.get("/api/v1/queues/intake", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["cases"] == []


async def test_intake_queue_org_isolation(
    client, db_session: AsyncSession, seed_intake_user
):
    """AC13: cases from a different org do not appear in the intake queue."""
    from placementops.core.models import Organization, HospitalReference
    import uuid as _uuid

    # Create a second org and case
    other_org_id = str(_uuid.uuid4())
    other_org = Organization(id=other_org_id, name="Other Org")
    db_session.add(other_org)

    other_hospital_id = str(_uuid.uuid4())
    other_hospital = HospitalReference(
        id=other_hospital_id,
        organization_id=other_org_id,
        hospital_name="Other Hospital",
    )
    db_session.add(other_hospital)

    other_case = PatientCase(
        organization_id=other_org_id,
        hospital_id=other_hospital_id,
        patient_name="Other Org Patient",
        current_status="intake_in_progress",
        active_case_flag=True,
        created_by_user_id=seed_intake_user["user_id"],
        updated_by_user_id=seed_intake_user["user_id"],
    )
    db_session.add(other_case)
    await db_session.commit()

    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )
    resp = await client.get("/api/v1/queues/intake", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    # The test user's org has no cases — should see 0
    assert body["total"] == 0
    case_ids = [c["id"] for c in body["cases"]]
    assert other_case.id not in case_ids
