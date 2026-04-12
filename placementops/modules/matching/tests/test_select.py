# @forgeplan-node: matching-module
# @forgeplan-spec: AC13
# @forgeplan-spec: AC14
# @forgeplan-spec: AC16
# @forgeplan-spec: AC17
"""
Tests for GET matches and PATCH select endpoints.

Covers: AC13, AC14, AC16, AC17
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.models import (
    AuditEvent,
    FacilityMatch,
)
from placementops.modules.matching import service
from placementops.modules.matching.tests.conftest import (
    TEST_ORG_ID,
    TEST_PAYER_ID,
    make_id,
    seed_assessment,
    seed_capabilities,
    seed_case,
    seed_facility,
    seed_insurance_rule,
    seed_payer,
    seed_preference,
    seed_user,
    auth_headers,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# AC13 — GET matches returns latest match set with full scoring breakdown
# ---------------------------------------------------------------------------


async def test_get_matches_returns_latest_generation(
    db_session: AsyncSession,
    auth_ctx_coordinator,
    seeded_case,
    seeded_facilities,
    seed_org_fixture,
    seeded_payer,
):
    """
    AC13: POST generate twice (re-score); GET matches returns second generation's
    generated_at; all component scores, blockers_json, explanation_text, rank_order,
    is_recommended present in response.
    """
    case = seeded_case

    # First generation
    first_matches = await service.generate_matches(
        session=db_session,
        case_id=UUID(case.id),
        assessment_id=None,
        auth_ctx=auth_ctx_coordinator,
    )
    first_generated_at = first_matches[0].generated_at

    # Refresh case for second generation
    await db_session.refresh(case)

    # Second generation
    second_matches = await service.generate_matches(
        session=db_session,
        case_id=UUID(case.id),
        assessment_id=None,
        auth_ctx=auth_ctx_coordinator,
    )

    # GET matches returns second generation
    retrieved = await service.get_matches(
        session=db_session,
        case_id=UUID(case.id),
        auth_ctx=auth_ctx_coordinator,
    )

    assert len(retrieved) == len(second_matches), (
        "GET matches should return the same count as the second generation"
    )

    # Verify generated_at from retrieved matches belongs to second run
    second_generated_at = second_matches[0].generated_at
    for m in retrieved:
        assert m.generated_at == second_generated_at, (
            "GET matches must return the latest generation's records"
        )

    # Verify all required fields are present on non-excluded matches
    non_excluded = [m for m in retrieved if m.rank_order > 0]
    for match in non_excluded:
        assert match.level_of_care_fit_score is not None
        assert match.payer_fit_score is not None
        assert match.clinical_fit_score is not None
        assert match.geography_score is not None
        assert match.preference_score is not None
        assert match.overall_score is not None
        assert match.rank_order is not None
        assert match.is_recommended is not None
        assert match.explanation_text is not None


async def test_get_matches_ordering_excluded_at_bottom(
    db_session: AsyncSession,
    auth_ctx_coordinator,
    seed_org_fixture,
    seeded_payer,
    coordinator_user,
):
    """
    AC13: Excluded facilities (rank_order=-1) appear after all ranked facilities in GET response.
    """
    case = await seed_case(db_session, insurance_primary="Medicare")
    await seed_assessment(
        db_session,
        case_id=case.id,
        reviewer_user_id=coordinator_user.id,
        review_status="finalized",
        recommended_loc="snf",
    )

    # Mix: 2 scored + 1 excluded
    for i in range(2):
        f = await seed_facility(db_session, facility_name=f"Scored {i}")
        await seed_capabilities(db_session, f.id, accepts_snf=True)
        await seed_insurance_rule(db_session, f.id, TEST_PAYER_ID, "Medicare", "accepted")

    excluded_f = await seed_facility(db_session, facility_name="Excluded")
    await seed_capabilities(db_session, excluded_f.id, accepts_snf=True)
    await seed_insurance_rule(db_session, excluded_f.id, TEST_PAYER_ID, "Medicare", "not_accepted")

    await service.generate_matches(
        session=db_session,
        case_id=UUID(case.id),
        assessment_id=None,
        auth_ctx=auth_ctx_coordinator,
    )

    retrieved = await service.get_matches(
        session=db_session,
        case_id=UUID(case.id),
        auth_ctx=auth_ctx_coordinator,
    )

    # Find the position of excluded and ranked matches
    ranks = [m.rank_order for m in retrieved]
    # All positive ranks must come before -1
    positive_ranks = [r for r in ranks if r > 0]
    negative_ranks = [r for r in ranks if r == -1]

    assert len(negative_ranks) >= 1
    assert len(positive_ranks) >= 1

    # Last occurrence of a positive rank must come before first occurrence of -1
    last_positive_idx = max(i for i, r in enumerate(ranks) if r > 0)
    first_excluded_idx = min(i for i, r in enumerate(ranks) if r == -1)
    assert last_positive_idx < first_excluded_idx, (
        "All ranked facilities must appear before excluded facilities in GET response"
    )


async def test_get_matches_returns_empty_when_no_generation(
    db_session: AsyncSession,
    auth_ctx_coordinator,
    seed_org_fixture,
):
    """
    AC13: GET matches before any generation returns empty list.
    """
    case = await seed_case(db_session)

    retrieved = await service.get_matches(
        session=db_session,
        case_id=UUID(case.id),
        auth_ctx=auth_ctx_coordinator,
    )
    assert retrieved == []


# ---------------------------------------------------------------------------
# AC14 — PATCH select toggles selected_for_outreach; multiple simultaneous
# ---------------------------------------------------------------------------


async def test_select_toggles_facility(
    db_session: AsyncSession,
    auth_ctx_coordinator,
    seeded_case,
    seeded_payer,
    seed_org_fixture,
):
    """
    AC14: PATCH select on facility A → selected=True; case_activity_event written.
    PATCH select on facility B → both A and B selected=True.
    PATCH select on A again → A deselected, B still selected.
    """
    f_a = await seed_facility(db_session, facility_name="Facility A")
    await seed_capabilities(db_session, f_a.id, accepts_snf=True)
    await seed_insurance_rule(db_session, f_a.id, TEST_PAYER_ID, "Medicare", "accepted")

    f_b = await seed_facility(db_session, facility_name="Facility B")
    await seed_capabilities(db_session, f_b.id, accepts_snf=True)
    await seed_insurance_rule(db_session, f_b.id, TEST_PAYER_ID, "Medicare", "accepted")

    case = seeded_case
    new_matches = await service.generate_matches(
        session=db_session,
        case_id=UUID(case.id),
        assessment_id=None,
        auth_ctx=auth_ctx_coordinator,
    )

    match_a = next(m for m in new_matches if m.facility_id == f_a.id)
    match_b = next(m for m in new_matches if m.facility_id == f_b.id)

    # PATCH select A → True
    updated_a = await service.toggle_select(
        session=db_session,
        case_id=UUID(case.id),
        match_id=UUID(match_a.id),
        auth_ctx=auth_ctx_coordinator,
    )
    assert updated_a.selected_for_outreach is True

    # PATCH select B → True
    updated_b = await service.toggle_select(
        session=db_session,
        case_id=UUID(case.id),
        match_id=UUID(match_b.id),
        auth_ctx=auth_ctx_coordinator,
    )
    assert updated_b.selected_for_outreach is True

    # Verify both are selected simultaneously
    await db_session.refresh(updated_a)
    await db_session.refresh(updated_b)
    assert updated_a.selected_for_outreach is True
    assert updated_b.selected_for_outreach is True

    # PATCH select A again → deselect
    updated_a_again = await service.toggle_select(
        session=db_session,
        case_id=UUID(case.id),
        match_id=UUID(match_a.id),
        auth_ctx=auth_ctx_coordinator,
    )
    assert updated_a_again.selected_for_outreach is False

    # B should still be selected
    await db_session.refresh(updated_b)
    assert updated_b.selected_for_outreach is True


async def test_select_writes_audit_event(
    db_session: AsyncSession,
    auth_ctx_coordinator,
    seeded_case,
    seeded_payer,
    seed_org_fixture,
):
    """
    AC14: PATCH select writes AuditEvent with event_type=facility_selected.
    PATCH select again (deselect) writes AuditEvent with event_type=facility_deselected.
    """
    f = await seed_facility(db_session)
    await seed_capabilities(db_session, f.id, accepts_snf=True)
    await seed_insurance_rule(db_session, f.id, TEST_PAYER_ID, "Medicare", "accepted")

    case = seeded_case
    new_matches = await service.generate_matches(
        session=db_session,
        case_id=UUID(case.id),
        assessment_id=None,
        auth_ctx=auth_ctx_coordinator,
    )

    match = next(m for m in new_matches if m.facility_id == f.id)

    # Select → should write facility_selected audit event
    await service.toggle_select(
        session=db_session,
        case_id=UUID(case.id),
        match_id=UUID(match.id),
        auth_ctx=auth_ctx_coordinator,
    )

    audit_result = await db_session.execute(
        select(AuditEvent).where(
            AuditEvent.event_type == "facility_selected"
        )
    )
    audit_selected = audit_result.scalars().all()
    assert len(audit_selected) >= 1

    # Deselect → should write facility_deselected
    await service.toggle_select(
        session=db_session,
        case_id=UUID(case.id),
        match_id=UUID(match.id),
        auth_ctx=auth_ctx_coordinator,
    )

    audit_deselected_result = await db_session.execute(
        select(AuditEvent).where(
            AuditEvent.event_type == "facility_deselected"
        )
    )
    audit_deselected = audit_deselected_result.scalars().all()
    assert len(audit_deselected) >= 1


async def test_select_404_wrong_case(
    db_session: AsyncSession,
    auth_ctx_coordinator,
    seeded_case,
    seeded_payer,
    seed_org_fixture,
):
    """
    AC14: Trying to select a match_id that doesn't belong to the given case_id → 404.
    """
    f = await seed_facility(db_session)
    await seed_capabilities(db_session, f.id, accepts_snf=True)
    await seed_insurance_rule(db_session, f.id, TEST_PAYER_ID, "Medicare", "accepted")

    case = seeded_case
    new_matches = await service.generate_matches(
        session=db_session,
        case_id=UUID(case.id),
        assessment_id=None,
        auth_ctx=auth_ctx_coordinator,
    )

    match = new_matches[0]

    # Create a second case (different case_id)
    other_case = await seed_case(db_session)

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc_info:
        await service.toggle_select(
            session=db_session,
            case_id=UUID(other_case.id),  # Wrong case_id
            match_id=UUID(match.id),
            auth_ctx=auth_ctx_coordinator,
        )
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# AC16 — Role enforcement via HTTP for PATCH select
# ---------------------------------------------------------------------------


async def test_patch_select_403_intake_staff_http(
    client,
    db_session: AsyncSession,
    seed_org_fixture,
    seeded_case,
    seeded_payer,
    seeded_facilities,
    intake_user,
    auth_ctx_coordinator,
):
    """
    AC16: intake_staff PATCH select → HTTP 403.
    """
    case = seeded_case
    # Generate matches first with coordinator auth
    new_matches = await service.generate_matches(
        session=db_session,
        case_id=UUID(case.id),
        assessment_id=None,
        auth_ctx=auth_ctx_coordinator,
    )
    match = new_matches[0]

    import os, jwt as _jwt
    secret = os.environ.get("SUPABASE_JWT_SECRET", "test-secret-key-minimum-32-chars-long")
    token = _jwt.encode(
        {
            "sub": intake_user.id,
            "aud": "authenticated",
            "exp": 9999999999,
            "app_metadata": {
                "organization_id": str(TEST_ORG_ID),
                "role_key": "intake_staff",
            },
        },
        secret,
        algorithm="HS256",
    )

    response = await client.patch(
        f"/api/v1/cases/{case.id}/matches/{match.id}/select",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


async def test_patch_select_403_readonly_http(
    client,
    db_session: AsyncSession,
    seed_org_fixture,
    seeded_case,
    seeded_payer,
    seeded_facilities,
    readonly_user,
    auth_ctx_coordinator,
):
    """
    AC16: read_only PATCH select → HTTP 403.
    """
    case = seeded_case
    new_matches = await service.generate_matches(
        session=db_session,
        case_id=UUID(case.id),
        assessment_id=None,
        auth_ctx=auth_ctx_coordinator,
    )
    match = new_matches[0]

    import os, jwt as _jwt
    secret = os.environ.get("SUPABASE_JWT_SECRET", "test-secret-key-minimum-32-chars-long")
    token = _jwt.encode(
        {
            "sub": readonly_user.id,
            "aud": "authenticated",
            "exp": 9999999999,
            "app_metadata": {
                "organization_id": str(TEST_ORG_ID),
                "role_key": "read_only",
            },
        },
        secret,
        algorithm="HS256",
    )

    response = await client.patch(
        f"/api/v1/cases/{case.id}/matches/{match.id}/select",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# AC17 — preference_score bonus for preferred facilities
# ---------------------------------------------------------------------------


async def test_preference_score_higher_for_preferred_facility(
    db_session: AsyncSession,
    auth_ctx_coordinator,
    seed_org_fixture,
    seeded_payer,
    coordinator_user,
):
    """
    AC17: Seed a facility in facility_preferences for the case's hospital_id.
    Seed a second facility NOT in preferences.
    POST generate; assert preferred facility has higher preference_score.
    """
    from placementops.core.models import HospitalReference

    # Seed hospital reference
    hospital_id = make_id()
    hospital = HospitalReference(
        id=hospital_id,
        organization_id=str(TEST_ORG_ID),
        hospital_name="Test Hospital",
    )
    db_session.add(hospital)
    await db_session.commit()

    # Case with hospital_id
    case = await seed_case(
        db_session,
        insurance_primary="Medicare",
        hospital_id=UUID(hospital_id),
    )
    await seed_assessment(
        db_session,
        case_id=case.id,
        reviewer_user_id=coordinator_user.id,
        review_status="finalized",
        recommended_loc="snf",
    )

    # Preferred facility — in facility_preferences for this hospital
    preferred_facility = await seed_facility(db_session, facility_name="Preferred Facility")
    await seed_capabilities(db_session, preferred_facility.id, accepts_snf=True)
    await seed_insurance_rule(
        db_session, preferred_facility.id, TEST_PAYER_ID, "Medicare", "accepted"
    )
    # Add to preferences with hospital scope
    await seed_preference(
        db_session,
        facility_id=preferred_facility.id,
        scope="hospital",
        scope_reference_id=hospital_id,
    )

    # Non-preferred facility — NOT in preferences
    non_preferred_facility = await seed_facility(db_session, facility_name="Non-Preferred Facility")
    await seed_capabilities(db_session, non_preferred_facility.id, accepts_snf=True)
    await seed_insurance_rule(
        db_session, non_preferred_facility.id, TEST_PAYER_ID, "Medicare", "accepted"
    )

    new_matches = await service.generate_matches(
        session=db_session,
        case_id=UUID(case.id),
        assessment_id=None,
        auth_ctx=auth_ctx_coordinator,
    )

    preferred_match = next(
        m for m in new_matches if m.facility_id == preferred_facility.id
    )
    non_preferred_match = next(
        m for m in new_matches if m.facility_id == non_preferred_facility.id
    )

    assert float(preferred_match.preference_score) > float(non_preferred_match.preference_score), (
        f"Preferred facility should have higher preference_score; "
        f"preferred={preferred_match.preference_score}, "
        f"non-preferred={non_preferred_match.preference_score}"
    )
    assert abs(float(preferred_match.preference_score) - 1.0) < 0.001
    assert abs(float(non_preferred_match.preference_score) - 0.0) < 0.001


async def test_global_preference_applies_across_cases(
    db_session: AsyncSession,
    auth_ctx_coordinator,
    seed_org_fixture,
    seeded_payer,
    coordinator_user,
):
    """
    AC17: Global scope preferences apply regardless of case hospital.
    """
    case = await seed_case(
        db_session,
        insurance_primary="Medicare",
        hospital_id=None,  # No hospital
    )
    await seed_assessment(
        db_session,
        case_id=case.id,
        reviewer_user_id=coordinator_user.id,
        review_status="finalized",
        recommended_loc="snf",
    )

    # Facility with global preference
    global_pref_facility = await seed_facility(
        db_session, facility_name="Global Preferred"
    )
    await seed_capabilities(db_session, global_pref_facility.id, accepts_snf=True)
    await seed_insurance_rule(
        db_session, global_pref_facility.id, TEST_PAYER_ID, "Medicare", "accepted"
    )
    await seed_preference(
        db_session,
        facility_id=global_pref_facility.id,
        scope="global",
        scope_reference_id=None,
    )

    # Regular facility
    regular_facility = await seed_facility(db_session, facility_name="Regular")
    await seed_capabilities(db_session, regular_facility.id, accepts_snf=True)
    await seed_insurance_rule(
        db_session, regular_facility.id, TEST_PAYER_ID, "Medicare", "accepted"
    )

    new_matches = await service.generate_matches(
        session=db_session,
        case_id=UUID(case.id),
        assessment_id=None,
        auth_ctx=auth_ctx_coordinator,
    )

    pref_match = next(m for m in new_matches if m.facility_id == global_pref_facility.id)
    reg_match = next(m for m in new_matches if m.facility_id == regular_facility.id)

    assert float(pref_match.preference_score) > float(reg_match.preference_score)
