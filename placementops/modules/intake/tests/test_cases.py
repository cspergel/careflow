# @forgeplan-node: intake-module
"""
Tests for case CRUD, mark-intake-complete, assignment, status-transition,
duplicate detection, intake field issues, and role enforcement.

Covers: AC1, AC2, AC3, AC4, AC5, AC6, AC7, AC14, AC15, AC16
"""
# @forgeplan-spec: AC1
# @forgeplan-spec: AC2
# @forgeplan-spec: AC3
# @forgeplan-spec: AC4
# @forgeplan-spec: AC5
# @forgeplan-spec: AC6
# @forgeplan-spec: AC7
# @forgeplan-spec: AC14
# @forgeplan-spec: AC15
# @forgeplan-spec: AC16

from __future__ import annotations

import os
import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.models import CaseStatusHistory, PatientCase
from placementops.modules.intake.models import CaseAssignment, IntakeFieldIssue
from placementops.modules.intake.tests.conftest import auth_headers

# Set test JWT secret before any imports that use it
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret-key-minimum-32-chars-long")

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _full_case_payload(hospital_id: str) -> dict:
    """Return a case payload with all required fields for mark-intake-complete."""
    return {
        "patient_name": "Jane Doe",
        "hospital_id": hospital_id,
        "dob": "1970-05-15",
        "hospital_unit": "ICU",
        "room_number": "101",
        "admission_date": "2026-04-01",
        "primary_diagnosis_text": "Hip fracture",
        "insurance_primary": "Medicare",
    }


# ---------------------------------------------------------------------------
# AC1: POST /cases creates case with status=intake_in_progress
# ---------------------------------------------------------------------------


async def test_create_case_returns_201_and_intake_in_progress(
    client, db_session, seed_org, seed_hospital, seed_intake_user
):
    """AC1: POST /cases → 201, body.current_status==intake_in_progress."""
    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )
    payload = {
        "patient_name": "John Smith",
        "hospital_id": seed_hospital,
    }

    resp = await client.post("/api/v1/cases", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text

    body = resp.json()
    assert body["case"]["current_status"] == "intake_in_progress"
    assert body["case"]["patient_name"] == "John Smith"


async def test_create_case_writes_two_status_history_rows(
    client, db_session, seed_org, seed_hospital, seed_intake_user
):
    """AC1: case_status_history has two rows (None→new and new→intake_in_progress)."""
    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )
    payload = {"patient_name": "History Test", "hospital_id": seed_hospital}

    resp = await client.post("/api/v1/cases", json=payload, headers=headers)
    assert resp.status_code == 201
    case_id = resp.json()["case"]["id"]

    result = await db_session.execute(
        select(CaseStatusHistory).where(
            CaseStatusHistory.patient_case_id == case_id
        )
    )
    rows = result.scalars().all()
    # Expect at least 2 rows: initial (None→new) + transition (new→intake_in_progress)
    assert len(rows) >= 2

    statuses = {(r.from_status, r.to_status) for r in rows}
    assert (None, "new") in statuses
    assert ("new", "intake_in_progress") in statuses


# ---------------------------------------------------------------------------
# AC2: GET /cases — paginated + filtered
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def five_cases(db_session: AsyncSession, seed_org: str, seed_hospital: str, seed_intake_user: dict):
    """Seed 5 cases: 3 in intake_in_progress, 2 in needs_clinical_review."""
    cases = []
    for i in range(3):
        c = PatientCase(
            organization_id=seed_org,
            hospital_id=seed_hospital,
            patient_name=f"Patient {i}",
            current_status="intake_in_progress",
            created_by_user_id=seed_intake_user["user_id"],
            updated_by_user_id=seed_intake_user["user_id"],
        )
        db_session.add(c)
        cases.append(c)
    for i in range(2):
        c = PatientCase(
            organization_id=seed_org,
            hospital_id=seed_hospital,
            patient_name="Smith Baker",
            current_status="needs_clinical_review",
            created_by_user_id=seed_intake_user["user_id"],
            updated_by_user_id=seed_intake_user["user_id"],
        )
        db_session.add(c)
        cases.append(c)
    await db_session.commit()
    return cases


async def test_list_cases_status_filter(
    client, five_cases, seed_intake_user
):
    """AC2: GET /cases?status=intake_in_progress → only matching cases."""
    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )
    resp = await client.get(
        "/api/v1/cases?status=intake_in_progress", headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert all(c["current_status"] == "intake_in_progress" for c in body["cases"])


async def test_list_cases_search_filter(
    client, five_cases, seed_intake_user
):
    """AC2: GET /cases?search=Smith → name-match filtering works."""
    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )
    resp = await client.get("/api/v1/cases?search=Smith", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert all("Smith" in c["patient_name"] for c in body["cases"])


async def test_list_cases_pagination_fields_present(
    client, five_cases, seed_intake_user
):
    """AC2: pagination fields (total, page, page_size) present in response."""
    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )
    resp = await client.get("/api/v1/cases?page=1&page_size=2", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "total" in body
    assert "page" in body
    assert "page_size" in body
    assert body["page"] == 1
    assert body["page_size"] == 2
    assert len(body["cases"]) <= 2


# ---------------------------------------------------------------------------
# AC3: GET /cases/{id} returns case with intake_field_issues
# ---------------------------------------------------------------------------


async def test_get_case_detail_with_field_issues(
    client, db_session, seed_org, seed_hospital, seed_intake_user
):
    """AC3: GET /cases/{id} → intake_field_issues list has correct length and resolved_flag."""
    # Create case
    case = PatientCase(
        organization_id=seed_org,
        hospital_id=seed_hospital,
        patient_name="Detail Test",
        current_status="intake_in_progress",
        created_by_user_id=seed_intake_user["user_id"],
        updated_by_user_id=seed_intake_user["user_id"],
    )
    db_session.add(case)
    await db_session.flush()

    # Add 2 field issues
    issue1 = IntakeFieldIssue(
        patient_case_id=case.id,
        field_name="insurance_primary",
        issue_description="Insurance info missing",
        resolved_flag=False,
    )
    issue2 = IntakeFieldIssue(
        patient_case_id=case.id,
        field_name="room_number",
        issue_description="Room number not provided",
        resolved_flag=True,
    )
    db_session.add(issue1)
    db_session.add(issue2)
    await db_session.commit()

    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )
    resp = await client.get(f"/api/v1/cases/{case.id}", headers=headers)
    assert resp.status_code == 200
    body = resp.json()

    assert len(body["intake_field_issues"]) == 2
    flags = {i["field_name"]: i["resolved_flag"] for i in body["intake_field_issues"]}
    assert flags["insurance_primary"] == False
    assert flags["room_number"] == True


# ---------------------------------------------------------------------------
# AC4: PATCH /cases/{id} — role-based field allowlists
# ---------------------------------------------------------------------------


async def test_patch_intake_staff_allowed_field(
    client, db_session, seed_org, seed_hospital, seed_intake_user
):
    """AC4: intake_staff can update primary_diagnosis_text → 200."""
    case = PatientCase(
        organization_id=seed_org,
        hospital_id=seed_hospital,
        patient_name="Patch Test",
        current_status="intake_in_progress",
        created_by_user_id=seed_intake_user["user_id"],
        updated_by_user_id=seed_intake_user["user_id"],
    )
    db_session.add(case)
    await db_session.commit()

    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )
    resp = await client.patch(
        f"/api/v1/cases/{case.id}",
        json={"primary_diagnosis_text": "Updated diagnosis"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["updated_by_user_id"] == seed_intake_user["user_id"]


async def test_patch_intake_staff_coordinator_field_forbidden(
    client, db_session, seed_org, seed_hospital, seed_intake_user, seed_coordinator_user
):
    """AC4: intake_staff PATCH with assigned_coordinator_user_id → 403."""
    case = PatientCase(
        organization_id=seed_org,
        hospital_id=seed_hospital,
        patient_name="Patch Role Test",
        current_status="intake_in_progress",
        created_by_user_id=seed_intake_user["user_id"],
        updated_by_user_id=seed_intake_user["user_id"],
    )
    db_session.add(case)
    await db_session.commit()

    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )
    resp = await client.patch(
        f"/api/v1/cases/{case.id}",
        json={"assigned_coordinator_user_id": seed_coordinator_user["user_id"]},
        headers=headers,
    )
    assert resp.status_code == 403


async def test_patch_coordinator_allowed_field(
    client, db_session, seed_org, seed_hospital, seed_coordinator_user, seed_intake_user
):
    """AC4: placement_coordinator can update priority_level → 200."""
    case = PatientCase(
        organization_id=seed_org,
        hospital_id=seed_hospital,
        patient_name="Coordinator Patch",
        current_status="intake_in_progress",
        created_by_user_id=seed_intake_user["user_id"],
        updated_by_user_id=seed_intake_user["user_id"],
    )
    db_session.add(case)
    await db_session.commit()

    headers = auth_headers(
        seed_coordinator_user["user_id"], seed_coordinator_user["org_id"], "placement_coordinator"
    )
    resp = await client.patch(
        f"/api/v1/cases/{case.id}",
        json={"priority_level": "urgent"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["priority_level"] == "urgent"


async def test_patch_unknown_role_forbidden(
    client, db_session, seed_org, seed_hospital, seed_clinical_reviewer, seed_intake_user
):
    """AC4: clinical_reviewer on PATCH → 403 (not in allowed roles for PATCH)."""
    case = PatientCase(
        organization_id=seed_org,
        hospital_id=seed_hospital,
        patient_name="Clinical Patch",
        current_status="under_clinical_review",
        created_by_user_id=seed_intake_user["user_id"],
        updated_by_user_id=seed_intake_user["user_id"],
    )
    db_session.add(case)
    await db_session.commit()

    headers = auth_headers(
        seed_clinical_reviewer["user_id"], seed_clinical_reviewer["org_id"], "clinical_reviewer"
    )
    resp = await client.patch(
        f"/api/v1/cases/{case.id}",
        json={"priority_level": "urgent"},
        headers=headers,
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# AC5: POST /cases/{id}/mark-intake-complete
# ---------------------------------------------------------------------------


async def test_mark_intake_complete_valid(
    client, db_session, seed_org, seed_hospital, seed_intake_user
):
    """AC5: case with all required fields → mark-intake-complete → needs_clinical_review."""
    # Create a case with all required fields populated
    case = PatientCase(
        organization_id=seed_org,
        hospital_id=seed_hospital,
        patient_name="Full Case",
        hospital_unit="ICU",
        room_number="101",
        admission_date=date(2026, 4, 1),
        primary_diagnosis_text="Hip fracture",
        insurance_primary="Medicare",
        current_status="intake_in_progress",
        created_by_user_id=seed_intake_user["user_id"],
        updated_by_user_id=seed_intake_user["user_id"],
    )
    db_session.add(case)
    await db_session.commit()

    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )
    resp = await client.post(
        f"/api/v1/cases/{case.id}/mark-intake-complete", headers=headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["final_status"] == "needs_clinical_review"


async def test_mark_intake_complete_writes_two_history_rows(
    client, db_session, seed_org, seed_hospital, seed_intake_user
):
    """AC5: two CaseStatusHistory rows: intake_in_progress→intake_complete and intake_complete→needs_clinical_review."""
    case = PatientCase(
        organization_id=seed_org,
        hospital_id=seed_hospital,
        patient_name="History Two",
        hospital_unit="ICU",
        room_number="102",
        admission_date=date(2026, 4, 1),
        primary_diagnosis_text="Fracture",
        insurance_primary="Medicaid",
        current_status="intake_in_progress",
        created_by_user_id=seed_intake_user["user_id"],
        updated_by_user_id=seed_intake_user["user_id"],
    )
    db_session.add(case)
    await db_session.commit()

    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )
    await client.post(
        f"/api/v1/cases/{case.id}/mark-intake-complete", headers=headers
    )

    result = await db_session.execute(
        select(CaseStatusHistory).where(
            CaseStatusHistory.patient_case_id == case.id
        )
    )
    rows = result.scalars().all()
    transitions = {(r.from_status, r.to_status) for r in rows}
    assert ("intake_in_progress", "intake_complete") in transitions
    assert ("intake_complete", "needs_clinical_review") in transitions


async def test_mark_intake_complete_missing_required_field_422(
    client, db_session, seed_org, seed_hospital, seed_intake_user
):
    """AC5: missing required field → 422."""
    # Case without hospital_unit (required)
    case = PatientCase(
        organization_id=seed_org,
        hospital_id=seed_hospital,
        patient_name="Incomplete Case",
        # hospital_unit intentionally omitted
        room_number="101",
        admission_date=date(2026, 4, 1),
        primary_diagnosis_text="Fracture",
        insurance_primary="Medicare",
        current_status="intake_in_progress",
        created_by_user_id=seed_intake_user["user_id"],
        updated_by_user_id=seed_intake_user["user_id"],
    )
    db_session.add(case)
    await db_session.commit()

    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )
    resp = await client.post(
        f"/api/v1/cases/{case.id}/mark-intake-complete", headers=headers
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# AC6: POST /cases/{id}/assign
# ---------------------------------------------------------------------------


async def test_assign_coordinator_updates_case_field(
    client, db_session, seed_org, seed_hospital, seed_intake_user, seed_coordinator_user
):
    """AC6: assign placement_coordinator → case_assignments created + assigned_coordinator_user_id updated."""
    case = PatientCase(
        organization_id=seed_org,
        hospital_id=seed_hospital,
        patient_name="Assign Test",
        current_status="intake_in_progress",
        created_by_user_id=seed_intake_user["user_id"],
        updated_by_user_id=seed_intake_user["user_id"],
    )
    db_session.add(case)
    await db_session.commit()

    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )
    resp = await client.post(
        f"/api/v1/cases/{case.id}/assign",
        json={"user_id": seed_coordinator_user["user_id"], "role": "placement_coordinator"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["assigned_user_id"] == seed_coordinator_user["user_id"]

    # Verify CaseAssignment record
    result = await db_session.execute(
        select(CaseAssignment).where(CaseAssignment.patient_case_id == case.id)
    )
    assignment = result.scalar_one()
    assert assignment.assigned_user_id == seed_coordinator_user["user_id"]

    # Verify PatientCase.assigned_coordinator_user_id updated
    await db_session.refresh(case)
    assert case.assigned_coordinator_user_id == seed_coordinator_user["user_id"]


async def test_assign_clinical_reviewer_does_not_update_coordinator_field(
    client, db_session, seed_org, seed_hospital, seed_intake_user, seed_clinical_reviewer
):
    """AC6: assign clinical_reviewer → case_assignments created, assigned_coordinator_user_id unchanged."""
    case = PatientCase(
        organization_id=seed_org,
        hospital_id=seed_hospital,
        patient_name="Clinical Assign Test",
        current_status="under_clinical_review",
        created_by_user_id=seed_intake_user["user_id"],
        updated_by_user_id=seed_intake_user["user_id"],
    )
    db_session.add(case)
    await db_session.commit()

    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )
    resp = await client.post(
        f"/api/v1/cases/{case.id}/assign",
        json={"user_id": seed_clinical_reviewer["user_id"], "role": "clinical_reviewer"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["assigned_role"] == "clinical_reviewer"

    # assigned_coordinator_user_id should remain None
    await db_session.refresh(case)
    assert case.assigned_coordinator_user_id is None


# ---------------------------------------------------------------------------
# AC7: POST /cases/{id}/status-transition
# ---------------------------------------------------------------------------


async def test_invalid_transition_returns_400_with_allowed_transitions(
    client, db_session, seed_org, seed_hospital, seed_coordinator_user, seed_intake_user
):
    """AC7: transition from intake_in_progress to placed (invalid) → 400 with allowed_transitions."""
    case = PatientCase(
        organization_id=seed_org,
        hospital_id=seed_hospital,
        patient_name="Transition Test",
        current_status="intake_in_progress",
        created_by_user_id=seed_intake_user["user_id"],
        updated_by_user_id=seed_intake_user["user_id"],
    )
    db_session.add(case)
    await db_session.commit()

    headers = auth_headers(
        seed_coordinator_user["user_id"], seed_coordinator_user["org_id"], "placement_coordinator"
    )
    resp = await client.post(
        f"/api/v1/cases/{case.id}/status-transition",
        json={"to_status": "placed"},
        headers=headers,
    )
    assert resp.status_code == 400
    body = resp.json()
    assert "allowed_transitions" in body["detail"]


async def test_transition_wrong_role_returns_403(
    client, db_session, seed_org, seed_hospital, seed_clinical_reviewer, seed_intake_user
):
    """AC7: valid transition as role not in permitted_roles → 403."""
    # intake_in_progress → closed requires manager or admin
    case = PatientCase(
        organization_id=seed_org,
        hospital_id=seed_hospital,
        patient_name="Role Transition Test",
        current_status="intake_in_progress",
        created_by_user_id=seed_intake_user["user_id"],
        updated_by_user_id=seed_intake_user["user_id"],
    )
    db_session.add(case)
    await db_session.commit()

    # clinical_reviewer cannot close from intake_in_progress
    headers = auth_headers(
        seed_clinical_reviewer["user_id"], seed_clinical_reviewer["org_id"], "clinical_reviewer"
    )
    resp = await client.post(
        f"/api/v1/cases/{case.id}/status-transition",
        json={"to_status": "closed"},
        headers=headers,
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# AC14: Duplicate detection
# ---------------------------------------------------------------------------


async def test_duplicate_detection_same_patient_hospital(
    client, db_session, seed_org, seed_hospital, seed_intake_user
):
    """AC14: POST /cases with identical patient_name+dob+hospital_id → duplicate_warning."""
    # Create first case
    existing = PatientCase(
        organization_id=seed_org,
        hospital_id=seed_hospital,
        patient_name="John Duplicate",
        dob=date(1950, 1, 1),
        current_status="intake_in_progress",
        active_case_flag=True,
        created_by_user_id=seed_intake_user["user_id"],
        updated_by_user_id=seed_intake_user["user_id"],
    )
    db_session.add(existing)
    await db_session.commit()

    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )
    resp = await client.post(
        "/api/v1/cases",
        json={
            "patient_name": "John Duplicate",
            "hospital_id": seed_hospital,
            "dob": "1950-01-01",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["duplicate_warning"] is not None
    assert body["duplicate_warning"]["existing_case_id"] == existing.id


async def test_no_duplicate_warning_for_terminal_case(
    client, db_session, seed_org, seed_hospital, seed_intake_user
):
    """AC14: no duplicate_warning when existing case is in terminal status (placed)."""
    terminal_case = PatientCase(
        organization_id=seed_org,
        hospital_id=seed_hospital,
        patient_name="Terminal Patient",
        dob=date(1960, 6, 15),
        current_status="placed",
        active_case_flag=False,
        created_by_user_id=seed_intake_user["user_id"],
        updated_by_user_id=seed_intake_user["user_id"],
    )
    db_session.add(terminal_case)
    await db_session.commit()

    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )
    resp = await client.post(
        "/api/v1/cases",
        json={
            "patient_name": "Terminal Patient",
            "hospital_id": seed_hospital,
            "dob": "1960-06-15",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["duplicate_warning"] is None


# ---------------------------------------------------------------------------
# AC15: Intake field issues — created and resolved
# ---------------------------------------------------------------------------


async def test_intake_field_issue_resolved_on_patch(
    client, db_session, seed_org, seed_hospital, seed_intake_user
):
    """AC15: re-submit with valid value → resolved_flag=True."""
    case = PatientCase(
        organization_id=seed_org,
        hospital_id=seed_hospital,
        patient_name="Field Issue Test",
        current_status="intake_in_progress",
        created_by_user_id=seed_intake_user["user_id"],
        updated_by_user_id=seed_intake_user["user_id"],
    )
    db_session.add(case)
    await db_session.flush()

    # Create an unresolved issue for room_number
    issue = IntakeFieldIssue(
        patient_case_id=case.id,
        field_name="room_number",
        issue_description="Room number missing",
        resolved_flag=False,
    )
    db_session.add(issue)
    await db_session.commit()

    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )
    # PATCH with valid room_number → should resolve the issue
    resp = await client.patch(
        f"/api/v1/cases/{case.id}",
        json={"room_number": "202"},
        headers=headers,
    )
    assert resp.status_code == 200

    # Verify resolved_flag is now True
    await db_session.refresh(issue)
    assert issue.resolved_flag == True


async def test_intake_field_issue_created_via_patch_clear_required_field(
    client, db_session, seed_org, seed_hospital, seed_intake_user
):
    """AC15: Clearing a required field via PATCH creates an IntakeFieldIssue (HTTP path)."""
    from placementops.modules.intake.models import IntakeFieldIssue as IFI

    case = PatientCase(
        organization_id=seed_org,
        hospital_id=seed_hospital,
        patient_name="AC15 Creation Test",
        current_status="intake_in_progress",
        primary_diagnosis_text="Heart failure",
        created_by_user_id=seed_intake_user["user_id"],
        updated_by_user_id=seed_intake_user["user_id"],
    )
    db_session.add(case)
    await db_session.commit()

    headers = auth_headers(
        seed_intake_user["user_id"], seed_intake_user["org_id"], "intake_staff"
    )
    # Clear a required field — should trigger issue creation
    resp = await client.patch(
        f"/api/v1/cases/{case.id}",
        json={"primary_diagnosis_text": ""},
        headers=headers,
    )
    assert resp.status_code == 200

    # Assert IntakeFieldIssue was created with resolved_flag=False
    await db_session.refresh(case)
    result = await db_session.execute(
        select(IFI).where(
            IFI.patient_case_id == case.id,
            IFI.field_name == "primary_diagnosis_text",
            IFI.resolved_flag == False,  # noqa: E712
        )
    )
    issue = result.scalar_one_or_none()
    assert issue is not None, "IntakeFieldIssue should have been created when required field was cleared"

    # Re-submit with a valid value — should resolve the issue
    resp2 = await client.patch(
        f"/api/v1/cases/{case.id}",
        json={"primary_diagnosis_text": "Congestive heart failure"},
        headers=headers,
    )
    assert resp2.status_code == 200

    await db_session.refresh(issue)
    assert issue.resolved_flag is True


async def test_intake_field_issue_created_on_service_validation_call(
    db_session, seed_org, seed_hospital, seed_intake_user
):
    """AC15: IntakeFieldIssue created via service call with resolved_flag=False."""
    from placementops.modules.intake import service

    case = PatientCase(
        organization_id=seed_org,
        hospital_id=seed_hospital,
        patient_name="Issue Create Test",
        current_status="intake_in_progress",
        created_by_user_id=seed_intake_user["user_id"],
        updated_by_user_id=seed_intake_user["user_id"],
    )
    db_session.add(case)
    await db_session.flush()

    issue = await service.create_intake_field_issue(
        session=db_session,
        patient_case_id=case.id,
        field_name="insurance_primary",
        issue_description="Insurance info missing",
    )
    await db_session.commit()

    assert issue.resolved_flag == False
    assert issue.field_name == "insurance_primary"


# ---------------------------------------------------------------------------
# AC16: Role enforcement on create and mark-intake-complete
# ---------------------------------------------------------------------------


async def test_create_case_as_clinical_reviewer_forbidden(
    client, db_session, seed_org, seed_hospital, seed_clinical_reviewer
):
    """AC16: POST /cases as clinical_reviewer → 403."""
    headers = auth_headers(
        seed_clinical_reviewer["user_id"], seed_clinical_reviewer["org_id"], "clinical_reviewer"
    )
    resp = await client.post(
        "/api/v1/cases",
        json={"patient_name": "Should Fail", "hospital_id": seed_hospital},
        headers=headers,
    )
    assert resp.status_code == 403


async def test_create_case_as_admin_succeeds(
    client, db_session, seed_org, seed_hospital, seed_admin_user
):
    """AC16: POST /cases as admin → 201."""
    headers = auth_headers(
        seed_admin_user["user_id"], seed_admin_user["org_id"], "admin"
    )
    resp = await client.post(
        "/api/v1/cases",
        json={"patient_name": "Admin Case", "hospital_id": seed_hospital},
        headers=headers,
    )
    assert resp.status_code == 201


async def test_mark_intake_complete_as_coordinator_forbidden(
    client, db_session, seed_org, seed_hospital, seed_intake_user, seed_coordinator_user
):
    """AC16: POST /cases/{id}/mark-intake-complete as placement_coordinator → 403."""
    case = PatientCase(
        organization_id=seed_org,
        hospital_id=seed_hospital,
        patient_name="Coordinator Cannot Complete",
        hospital_unit="ICU",
        room_number="101",
        admission_date=date(2026, 4, 1),
        primary_diagnosis_text="Test",
        insurance_primary="Medicare",
        current_status="intake_in_progress",
        created_by_user_id=seed_intake_user["user_id"],
        updated_by_user_id=seed_intake_user["user_id"],
    )
    db_session.add(case)
    await db_session.commit()

    headers = auth_headers(
        seed_coordinator_user["user_id"], seed_coordinator_user["org_id"], "placement_coordinator"
    )
    resp = await client.post(
        f"/api/v1/cases/{case.id}/mark-intake-complete", headers=headers
    )
    assert resp.status_code == 403
