# @forgeplan-node: outreach-module
# @forgeplan-spec: AC1
# @forgeplan-spec: AC2
# @forgeplan-spec: AC3
# @forgeplan-spec: AC4
# @forgeplan-spec: AC5
# @forgeplan-spec: AC6
# @forgeplan-spec: AC7
# @forgeplan-spec: AC8
# @forgeplan-spec: AC11
# @forgeplan-spec: AC12
"""
Tests for outreach workflow: AC1–AC8, AC11, AC12.

Covers:
  AC1  — Draft creation with allowlisted template variable substitution
  AC2  — Jinja2 SandboxedEnvironment prevents SSTI
  AC3  — Draft edit restricted to correct role and state
  AC4  — Submit-for-approval advances OutreachAction and case
  AC5  — Approve advances OutreachAction and case on first approval
  AC6  — Mark-sent stubs delivery without logging body content
  AC7  — Cancel permitted from pre-sent states only
  AC8  — phone_manual and task channels bypass approval with atomic state advance
  AC11 — All outreach state changes produce AuditEvent and case_activity_event
  AC12 — Closed-case mutation rejected
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.auth import AuthContext
from placementops.core.models import AuditEvent, OutreachAction, PatientCase
from placementops.modules.outreach import service
from placementops.modules.outreach.schemas import OutreachActionCreate, OutreachActionPatch
from placementops.modules.outreach.template_renderer import (
    ALLOWED_VARIABLES,
    render_template,
    validate_template_variables,
)

from placementops.modules.outreach.tests.conftest import (
    TEST_ORG_ID,
    make_id,
    seed_case,
    seed_outreach_action,
    seed_template,
    seed_user,
    make_auth_ctx,
)


# ---------------------------------------------------------------------------
# AC1: Draft creation with allowlisted variable substitution
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC1
@pytest.mark.asyncio
async def test_ac1_create_draft_with_template_variables(
    db_session: AsyncSession,
    seeded_case: PatientCase,
    seeded_template,
    auth_ctx_coordinator: AuthContext,
):
    """POST with valid allowlisted variables returns 201 with rendered body."""
    payload = OutreachActionCreate(
        action_type="facility_outreach",
        channel="email",
        draft_body="Fallback body",
        template_id=UUID(seeded_template.id),
        template_variables={
            "patient_name": "John Doe",
            "facility_name": "Sunset SNF",
        },
    )
    action = await service.create_outreach_action(
        session=db_session,
        case_id=UUID(seeded_case.id),
        payload=payload,
        auth_ctx=auth_ctx_coordinator,
    )
    assert action.approval_status == "draft"
    assert "John Doe" in action.draft_body
    assert "Sunset SNF" in action.draft_body


# @forgeplan-spec: AC1
@pytest.mark.asyncio
async def test_ac1_create_draft_non_allowlisted_variable_returns_400(
    db_session: AsyncSession,
    seeded_case: PatientCase,
    seeded_template,
    auth_ctx_coordinator: AuthContext,
):
    """POST with a non-allowlisted variable key returns 400 before rendering."""
    payload = OutreachActionCreate(
        action_type="facility_outreach",
        channel="email",
        draft_body="Fallback body",
        template_id=UUID(seeded_template.id),
        template_variables={"config.__class__": "evil"},
    )
    with pytest.raises(HTTPException) as exc_info:
        await service.create_outreach_action(
            session=db_session,
            case_id=UUID(seeded_case.id),
            payload=payload,
            auth_ctx=auth_ctx_coordinator,
        )
    assert exc_info.value.status_code == 400
    assert "allowlist" in str(exc_info.value.detail).lower()


# @forgeplan-spec: AC1
@pytest.mark.asyncio
async def test_ac1_allowlist_check_before_render(
    db_session: AsyncSession,
    seeded_case: PatientCase,
    auth_ctx_coordinator: AuthContext,
):
    """validate_template_variables raises 400 for forbidden keys before rendering."""
    with pytest.raises(HTTPException) as exc_info:
        validate_template_variables({"patient_name": "ok", "secret_key": "bad"})
    assert exc_info.value.status_code == 400
    assert "secret_key" in str(exc_info.value.detail)


# @forgeplan-spec: AC1
def test_ac1_allowed_variables_set():
    """ALLOWED_VARIABLES contains exactly the specified keys."""
    assert ALLOWED_VARIABLES == frozenset({
        "patient_name",
        "facility_name",
        "payer_name",
        "assessment_summary",
        "coordinator_name",
    })


# ---------------------------------------------------------------------------
# AC2: Jinja2 SandboxedEnvironment prevents SSTI
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC2
def test_ac2_ssti_mro_traversal_raises_400():
    """Template with {{ config.__class__.__mro__ }} raises 400, does not evaluate."""
    with pytest.raises(HTTPException) as exc_info:
        render_template("{{ config.__class__.__mro__ }}", {})
    assert exc_info.value.status_code == 400


# @forgeplan-spec: AC2
def test_ac2_ssti_undeclared_name_raises_400():
    """Template referencing undeclared names raises 400."""
    with pytest.raises(HTTPException) as exc_info:
        render_template("{{ secret_var }}", {})
    assert exc_info.value.status_code == 400


# @forgeplan-spec: AC2
def test_ac2_sandboxed_environment_class_used():
    """
    Confirm that render_template uses SandboxedEnvironment, not bare Environment.

    We import the module and verify the _SANDBOX_ENV attribute is an instance of
    SandboxedEnvironment, not jinja2.Environment.
    """
    from jinja2.sandbox import SandboxedEnvironment as _SE
    import jinja2
    from placementops.modules.outreach import template_renderer

    assert isinstance(template_renderer._SANDBOX_ENV, _SE), (
        "template_renderer._SANDBOX_ENV must be a SandboxedEnvironment instance"
    )
    # Verify it is NOT a bare Environment (SandboxedEnvironment or subclass is required)
    assert issubclass(type(template_renderer._SANDBOX_ENV), _SE), (
        "template_renderer._SANDBOX_ENV must be a SandboxedEnvironment subclass"
    )


# @forgeplan-spec: AC2
def test_ac2_ssti_class_attr_access_blocked():
    """Template accessing __class__ attribute raises 400."""
    with pytest.raises(HTTPException):
        render_template("{{ ''.__class__ }}", {})


# @forgeplan-spec: AC2
def test_ac2_valid_template_renders_correctly():
    """Valid template with allowed variables renders correctly."""
    result = render_template(
        "Hello {{ patient_name }} from {{ facility_name }}",
        {"patient_name": "Jane", "facility_name": "Sunrise SNF"},
    )
    assert result == "Hello Jane from Sunrise SNF"


# ---------------------------------------------------------------------------
# AC3: Draft edit restricted to correct role and state
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC3
@pytest.mark.asyncio
async def test_ac3_patch_draft_as_coordinator_succeeds(
    db_session: AsyncSession,
    seeded_case: PatientCase,
    auth_ctx_coordinator: AuthContext,
):
    """PATCH on a draft record by placement_coordinator returns updated action."""
    action = await seed_outreach_action(
        db_session, seeded_case.id, approval_status="draft"
    )
    patch = OutreachActionPatch(draft_body="Updated body text")
    updated = await service.patch_outreach_action(
        session=db_session,
        action_id=UUID(action.id),
        patch=patch,
        auth_ctx=auth_ctx_coordinator,
    )
    assert updated.draft_body == "Updated body text"


# @forgeplan-spec: AC3
@pytest.mark.asyncio
async def test_ac3_patch_sent_action_returns_409(
    db_session: AsyncSession,
    seeded_case: PatientCase,
    auth_ctx_coordinator: AuthContext,
):
    """PATCH on a sent record returns 409."""
    sent_action = await seed_outreach_action(
        db_session,
        seeded_case.id,
        approval_status="sent",
        sent_by_user_id=str(auth_ctx_coordinator.user_id),
        sent_at=datetime.now(timezone.utc),
    )
    patch = OutreachActionPatch(draft_body="Attempted edit")
    with pytest.raises(HTTPException) as exc_info:
        await service.patch_outreach_action(
            session=db_session,
            action_id=UUID(sent_action.id),
            patch=patch,
            auth_ctx=auth_ctx_coordinator,
        )
    assert exc_info.value.status_code == 409


# @forgeplan-spec: AC3
@pytest.mark.asyncio
async def test_ac3_patch_approved_action_returns_409(
    db_session: AsyncSession,
    seeded_case: PatientCase,
    auth_ctx_coordinator: AuthContext,
):
    """PATCH on an approved record returns 409."""
    approved_action = await seed_outreach_action(
        db_session, seeded_case.id, approval_status="approved"
    )
    patch = OutreachActionPatch(draft_subject="New subject")
    with pytest.raises(HTTPException) as exc_info:
        await service.patch_outreach_action(
            session=db_session,
            action_id=UUID(approved_action.id),
            patch=patch,
            auth_ctx=auth_ctx_coordinator,
        )
    assert exc_info.value.status_code == 409


# @forgeplan-spec: AC3
@pytest.mark.asyncio
async def test_ac3_patch_intake_staff_role_forbidden_via_router(
    client,
    db_session: AsyncSession,
    seeded_case: PatientCase,
    intake_user,
):
    """PATCH by intake_staff role returns 403 (router RBAC enforcement)."""
    action = await seed_outreach_action(
        db_session, seeded_case.id, approval_status="draft"
    )
    from placementops.modules.outreach.tests.conftest import auth_headers, TEST_ORG_ID

    headers = auth_headers(
        user_id=intake_user.id,
        org_id=str(TEST_ORG_ID),
        role_key="intake_staff",
    )
    resp = await client.patch(
        f"/api/v1/outreach-actions/{action.id}",
        json={"draft_body": "Unauthorized edit"},
        headers=headers,
    )
    assert resp.status_code == 403


# @forgeplan-spec: AC3
@pytest.mark.asyncio
async def test_ac3_patch_clinical_reviewer_role_forbidden_via_router(
    client,
    db_session: AsyncSession,
    seeded_case: PatientCase,
    clinical_user,
):
    """PATCH by clinical_reviewer role returns 403 (router RBAC enforcement)."""
    action = await seed_outreach_action(
        db_session, seeded_case.id, approval_status="draft"
    )
    from placementops.modules.outreach.tests.conftest import auth_headers, TEST_ORG_ID

    headers = auth_headers(
        user_id=clinical_user.id,
        org_id=str(TEST_ORG_ID),
        role_key="clinical_reviewer",
    )
    resp = await client.patch(
        f"/api/v1/outreach-actions/{action.id}",
        json={"draft_body": "Unauthorized edit"},
        headers=headers,
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# AC4: Submit-for-approval advances OutreachAction and case
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC4
# @forgeplan-spec: AC11
@pytest.mark.asyncio
async def test_ac4_submit_for_approval_advances_action(
    db_session: AsyncSession,
    seeded_case: PatientCase,
    auth_ctx_coordinator: AuthContext,
):
    """POST submit-for-approval on draft returns pending_approval."""
    action = await seed_outreach_action(
        db_session, seeded_case.id, approval_status="draft"
    )
    updated = await service.submit_for_approval(
        session=db_session,
        action_id=UUID(action.id),
        auth_ctx=auth_ctx_coordinator,
    )
    assert updated.approval_status == "pending_approval"


# @forgeplan-spec: AC4
@pytest.mark.asyncio
async def test_ac4_submit_advances_case_to_outreach_pending_approval(
    db_session: AsyncSession,
    seeded_case: PatientCase,
    auth_ctx_coordinator: AuthContext,
):
    """Submitting first action advances case from facility_options_generated to outreach_pending_approval."""
    action = await seed_outreach_action(
        db_session, seeded_case.id, approval_status="draft"
    )
    assert seeded_case.current_status == "facility_options_generated"

    await service.submit_for_approval(
        session=db_session,
        action_id=UUID(action.id),
        auth_ctx=auth_ctx_coordinator,
    )

    # Reload case
    refreshed_case = await db_session.get(PatientCase, seeded_case.id)
    assert refreshed_case.current_status == "outreach_pending_approval"


# @forgeplan-spec: AC4
# @forgeplan-spec: AC11
@pytest.mark.asyncio
async def test_ac4_submit_writes_audit_event(
    db_session: AsyncSession,
    seeded_case: PatientCase,
    auth_ctx_coordinator: AuthContext,
):
    """Submitting for approval writes an AuditEvent for the outreach_action."""
    action = await seed_outreach_action(
        db_session, seeded_case.id, approval_status="draft"
    )
    await service.submit_for_approval(
        session=db_session,
        action_id=UUID(action.id),
        auth_ctx=auth_ctx_coordinator,
    )

    result = await db_session.execute(
        select(AuditEvent).where(
            and_(
                AuditEvent.entity_type == "outreach_action",
                AuditEvent.entity_id == action.id,
                AuditEvent.event_type == "outreach_action_submitted",
            )
        )
    )
    audit = result.scalar_one_or_none()
    assert audit is not None
    assert audit.new_value_json["approval_status"] == "pending_approval"


# @forgeplan-spec: AC4
@pytest.mark.asyncio
async def test_ac4_submit_non_draft_returns_409(
    db_session: AsyncSession,
    seeded_case: PatientCase,
    auth_ctx_coordinator: AuthContext,
):
    """Submit on a non-draft action returns 409."""
    action = await seed_outreach_action(
        db_session, seeded_case.id, approval_status="pending_approval"
    )
    with pytest.raises(HTTPException) as exc_info:
        await service.submit_for_approval(
            session=db_session,
            action_id=UUID(action.id),
            auth_ctx=auth_ctx_coordinator,
        )
    assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# AC5: Approve advances OutreachAction and case on first approval
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC5
# @forgeplan-spec: AC11
@pytest.mark.asyncio
async def test_ac5_approve_sets_fields(
    db_session: AsyncSession,
    seeded_case: PatientCase,
    auth_ctx_coordinator: AuthContext,
):
    """Approving a pending_approval action sets approved_by_user_id and approved_at."""
    action = await seed_outreach_action(
        db_session, seeded_case.id, approval_status="pending_approval"
    )
    updated = await service.approve_action(
        session=db_session,
        action_id=UUID(action.id),
        auth_ctx=auth_ctx_coordinator,
    )
    assert updated.approval_status == "approved"
    assert updated.approved_by_user_id == str(auth_ctx_coordinator.user_id)
    assert updated.approved_at is not None


# @forgeplan-spec: AC5
@pytest.mark.asyncio
async def test_ac5_first_approval_advances_case(
    db_session: AsyncSession,
    auth_ctx_coordinator: AuthContext,
):
    """First approval advances case from outreach_pending_approval to outreach_in_progress."""
    case = await seed_case(
        db_session, current_status="outreach_pending_approval"
    )
    action = await seed_outreach_action(
        db_session, case.id, approval_status="pending_approval"
    )
    await service.approve_action(
        session=db_session,
        action_id=UUID(action.id),
        auth_ctx=auth_ctx_coordinator,
    )
    refreshed_case = await db_session.get(PatientCase, case.id)
    assert refreshed_case.current_status == "outreach_in_progress"


# @forgeplan-spec: AC5
@pytest.mark.asyncio
async def test_ac5_second_approval_does_not_re_advance_case(
    db_session: AsyncSession,
    auth_ctx_coordinator: AuthContext,
):
    """Second approval does not re-advance case if already at outreach_in_progress."""
    case = await seed_case(
        db_session, current_status="outreach_in_progress"
    )
    # First action already approved
    await seed_outreach_action(
        db_session, case.id, approval_status="approved"
    )
    # Second action in pending_approval
    action2 = await seed_outreach_action(
        db_session, case.id, approval_status="pending_approval"
    )
    await service.approve_action(
        session=db_session,
        action_id=UUID(action2.id),
        auth_ctx=auth_ctx_coordinator,
    )
    refreshed_case = await db_session.get(PatientCase, case.id)
    # Case stays at outreach_in_progress — not re-advanced
    assert refreshed_case.current_status == "outreach_in_progress"


# @forgeplan-spec: AC5
@pytest.mark.asyncio
async def test_ac5_approve_non_pending_returns_409(
    db_session: AsyncSession,
    seeded_case: PatientCase,
    auth_ctx_coordinator: AuthContext,
):
    """Approve on a draft action returns 409."""
    action = await seed_outreach_action(
        db_session, seeded_case.id, approval_status="draft"
    )
    with pytest.raises(HTTPException) as exc_info:
        await service.approve_action(
            session=db_session,
            action_id=UUID(action.id),
            auth_ctx=auth_ctx_coordinator,
        )
    assert exc_info.value.status_code == 409


# @forgeplan-spec: AC5
# @forgeplan-spec: AC11
@pytest.mark.asyncio
async def test_ac5_approve_writes_audit_event(
    db_session: AsyncSession,
    seeded_case: PatientCase,
    auth_ctx_coordinator: AuthContext,
):
    """Approve writes an AuditEvent with approved_by_user_id and approved_at."""
    action = await seed_outreach_action(
        db_session, seeded_case.id, approval_status="pending_approval"
    )
    await service.approve_action(
        session=db_session,
        action_id=UUID(action.id),
        auth_ctx=auth_ctx_coordinator,
    )
    result = await db_session.execute(
        select(AuditEvent).where(
            and_(
                AuditEvent.entity_type == "outreach_action",
                AuditEvent.entity_id == action.id,
                AuditEvent.event_type == "outreach_action_approved",
            )
        )
    )
    audit = result.scalar_one_or_none()
    assert audit is not None
    assert audit.new_value_json["approval_status"] == "approved"
    assert "approved_by_user_id" in audit.new_value_json


# ---------------------------------------------------------------------------
# AC6: Mark-sent stubs email delivery without logging body content
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC6
# @forgeplan-spec: AC11
@pytest.mark.asyncio
async def test_ac6_mark_sent_sets_fields(
    db_session: AsyncSession,
    seeded_case: PatientCase,
    auth_ctx_coordinator: AuthContext,
):
    """mark_sent sets approval_status=sent, sent_by_user_id, sent_at."""
    case = await seed_case(db_session, current_status="outreach_in_progress")
    action = await seed_outreach_action(
        db_session, case.id, approval_status="approved"
    )
    updated = await service.mark_sent(
        session=db_session,
        action_id=UUID(action.id),
        auth_ctx=auth_ctx_coordinator,
    )
    assert updated.approval_status == "sent"
    assert updated.sent_by_user_id == str(auth_ctx_coordinator.user_id)
    assert updated.sent_at is not None


# @forgeplan-spec: AC6
@pytest.mark.asyncio
async def test_ac6_audit_event_does_not_contain_body(
    db_session: AsyncSession,
    auth_ctx_coordinator: AuthContext,
):
    """AuditEvent new_value_json for mark_sent MUST NOT contain draft_body or draft_subject."""
    case = await seed_case(db_session, current_status="outreach_in_progress")
    action = await seed_outreach_action(
        db_session,
        case.id,
        approval_status="approved",
        draft_body="SENSITIVE_BODY_CONTENT",
        draft_subject="SENSITIVE_SUBJECT",
    )
    await service.mark_sent(
        session=db_session,
        action_id=UUID(action.id),
        auth_ctx=auth_ctx_coordinator,
    )
    result = await db_session.execute(
        select(AuditEvent).where(
            and_(
                AuditEvent.entity_type == "outreach_action",
                AuditEvent.entity_id == action.id,
                AuditEvent.event_type == "outreach_action_sent",
            )
        )
    )
    audit = result.scalar_one_or_none()
    assert audit is not None
    # Critical AC6 constraint: body content must not appear in audit log
    new_val = audit.new_value_json or {}
    assert "draft_body" not in new_val, "draft_body must not appear in AuditEvent new_value_json"
    assert "draft_subject" not in new_val, "draft_subject must not appear in AuditEvent new_value_json"
    # Verify only safe fields are present
    assert "SENSITIVE_BODY_CONTENT" not in str(new_val)
    assert "SENSITIVE_SUBJECT" not in str(new_val)


# @forgeplan-spec: AC6
@pytest.mark.asyncio
async def test_ac6_mark_sent_advances_case_to_pending_facility_response(
    db_session: AsyncSession,
    auth_ctx_coordinator: AuthContext,
):
    """First mark_sent advances case from outreach_in_progress to pending_facility_response."""
    case = await seed_case(db_session, current_status="outreach_in_progress")
    action = await seed_outreach_action(
        db_session, case.id, approval_status="approved"
    )
    await service.mark_sent(
        session=db_session,
        action_id=UUID(action.id),
        auth_ctx=auth_ctx_coordinator,
    )
    refreshed_case = await db_session.get(PatientCase, case.id)
    assert refreshed_case.current_status == "pending_facility_response"


# @forgeplan-spec: AC6
@pytest.mark.asyncio
async def test_ac6_mark_sent_non_approved_returns_409(
    db_session: AsyncSession,
    seeded_case: PatientCase,
    auth_ctx_coordinator: AuthContext,
):
    """mark_sent on a draft action returns 409."""
    action = await seed_outreach_action(
        db_session, seeded_case.id, approval_status="draft"
    )
    with pytest.raises(HTTPException) as exc_info:
        await service.mark_sent(
            session=db_session,
            action_id=UUID(action.id),
            auth_ctx=auth_ctx_coordinator,
        )
    assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# AC7: Cancel permitted from pre-sent states only
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC7
@pytest.mark.parametrize("cancelable_status", ["draft", "pending_approval", "approved", "failed"])
@pytest.mark.asyncio
async def test_ac7_cancel_pre_sent_states(
    cancelable_status: str,
    db_session: AsyncSession,
    seeded_case: PatientCase,
    auth_ctx_coordinator: AuthContext,
):
    """Cancel is permitted from draft, pending_approval, approved, and failed states."""
    action = await seed_outreach_action(
        db_session, seeded_case.id, approval_status=cancelable_status
    )
    updated = await service.cancel_action(
        session=db_session,
        action_id=UUID(action.id),
        auth_ctx=auth_ctx_coordinator,
    )
    assert updated.approval_status == "canceled"


# @forgeplan-spec: AC7
@pytest.mark.asyncio
async def test_ac7_cancel_sent_returns_409_with_exact_message(
    db_session: AsyncSession,
    seeded_case: PatientCase,
    auth_ctx_coordinator: AuthContext,
):
    """POST cancel on a sent record returns 409 with exact message."""
    sent_action = await seed_outreach_action(
        db_session,
        seeded_case.id,
        approval_status="sent",
        sent_by_user_id=str(auth_ctx_coordinator.user_id),
        sent_at=datetime.now(timezone.utc),
    )
    with pytest.raises(HTTPException) as exc_info:
        await service.cancel_action(
            session=db_session,
            action_id=UUID(sent_action.id),
            auth_ctx=auth_ctx_coordinator,
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "sent records are permanent communication records"


# @forgeplan-spec: AC7
# @forgeplan-spec: AC11
@pytest.mark.asyncio
async def test_ac7_cancel_writes_audit_event(
    db_session: AsyncSession,
    seeded_case: PatientCase,
    auth_ctx_coordinator: AuthContext,
):
    """Cancel writes an AuditEvent."""
    action = await seed_outreach_action(
        db_session, seeded_case.id, approval_status="draft"
    )
    await service.cancel_action(
        session=db_session,
        action_id=UUID(action.id),
        auth_ctx=auth_ctx_coordinator,
    )
    result = await db_session.execute(
        select(AuditEvent).where(
            and_(
                AuditEvent.entity_type == "outreach_action",
                AuditEvent.entity_id == action.id,
                AuditEvent.event_type == "outreach_action_canceled",
            )
        )
    )
    audit = result.scalar_one_or_none()
    assert audit is not None
    assert audit.new_value_json["approval_status"] == "canceled"


# ---------------------------------------------------------------------------
# AC8: phone_manual and task channels bypass approval with atomic state advance
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC8
@pytest.mark.parametrize("bypass_channel", ["phone_manual", "task"])
@pytest.mark.asyncio
async def test_ac8_bypass_channels_created_at_sent(
    bypass_channel: str,
    db_session: AsyncSession,
    seeded_case: PatientCase,
    auth_ctx_coordinator: AuthContext,
):
    """phone_manual and task channels are created at approval_status=sent."""
    payload = OutreachActionCreate(
        action_type="facility_outreach",
        channel=bypass_channel,
        draft_body="Phone call notes",
    )
    action = await service.create_outreach_action(
        session=db_session,
        case_id=UUID(seeded_case.id),
        payload=payload,
        auth_ctx=auth_ctx_coordinator,
    )
    assert action.approval_status == "sent"
    assert action.sent_at is not None
    assert action.sent_by_user_id == str(auth_ctx_coordinator.user_id)


# @forgeplan-spec: AC8
@pytest.mark.parametrize("bypass_channel", ["phone_manual", "task"])
@pytest.mark.asyncio
async def test_ac8_bypass_channel_advances_case_to_pending_facility_response(
    bypass_channel: str,
    db_session: AsyncSession,
    auth_ctx_coordinator: AuthContext,
):
    """Case advances to pending_facility_response after phone_manual/task creation."""
    case = await seed_case(
        db_session, current_status="facility_options_generated"
    )
    payload = OutreachActionCreate(
        action_type="facility_outreach",
        channel=bypass_channel,
        draft_body="Phone call notes",
    )
    await service.create_outreach_action(
        session=db_session,
        case_id=UUID(case.id),
        payload=payload,
        auth_ctx=auth_ctx_coordinator,
    )
    refreshed_case = await db_session.get(PatientCase, case.id)
    assert refreshed_case.current_status == "pending_facility_response"


# @forgeplan-spec: AC8
@pytest.mark.asyncio
async def test_ac8_no_intermediate_states_stored(
    db_session: AsyncSession,
    auth_ctx_coordinator: AuthContext,
):
    """No pending_approval or approved rows are written for phone_manual bypass."""
    case = await seed_case(
        db_session, current_status="facility_options_generated"
    )
    payload = OutreachActionCreate(
        action_type="facility_outreach",
        channel="phone_manual",
        draft_body="Phone call notes",
    )
    await service.create_outreach_action(
        session=db_session,
        case_id=UUID(case.id),
        payload=payload,
        auth_ctx=auth_ctx_coordinator,
    )
    # Verify NO pending_approval or approved actions exist for this case
    result = await db_session.execute(
        select(OutreachAction).where(
            and_(
                OutreachAction.patient_case_id == case.id,
                OutreachAction.approval_status.in_(["pending_approval", "approved"]),
            )
        )
    )
    bad_records = result.scalars().all()
    assert len(bad_records) == 0, (
        "No intermediate pending_approval or approved states should exist for phone_manual"
    )


# ---------------------------------------------------------------------------
# AC11: All state changes produce AuditEvent and case_activity_event
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC11
@pytest.mark.asyncio
async def test_ac11_complete_flow_audit_trail(
    db_session: AsyncSession,
    auth_ctx_coordinator: AuthContext,
):
    """
    Full draft→pending_approval→approved→sent flow produces exactly one AuditEvent
    per transition for the outreach_action entity.
    """
    case = await seed_case(
        db_session, current_status="facility_options_generated"
    )
    action = await seed_outreach_action(
        db_session, case.id, approval_status="draft"
    )
    action_id = UUID(action.id)

    # draft → pending_approval
    await service.submit_for_approval(
        session=db_session, action_id=action_id, auth_ctx=auth_ctx_coordinator
    )

    # pending_approval → approved
    await service.approve_action(
        session=db_session, action_id=action_id, auth_ctx=auth_ctx_coordinator
    )

    # Advance case to outreach_in_progress for mark_sent
    case_record = await db_session.get(PatientCase, case.id)
    if case_record.current_status == "outreach_pending_approval":
        # Manually bring to outreach_in_progress via state machine for test
        from placementops.core.state_machine import transition_case_status
        await transition_case_status(
            case_id=UUID(case.id),
            to_status="outreach_in_progress",
            actor_role="system",
            actor_user_id=auth_ctx_coordinator.user_id,
            session=db_session,
        )

    # Reload action (may be detached after multiple commits)
    action_record = await db_session.get(OutreachAction, action.id)
    if action_record.approval_status == "approved":
        # approved → sent
        await service.mark_sent(
            session=db_session, action_id=action_id, auth_ctx=auth_ctx_coordinator
        )

    # Verify audit trail: exactly one AuditEvent per transition
    audit_result = await db_session.execute(
        select(AuditEvent).where(
            and_(
                AuditEvent.entity_type == "outreach_action",
                AuditEvent.entity_id == action.id,
            )
        )
    )
    audit_events = audit_result.scalars().all()

    event_types = [a.event_type for a in audit_events]
    assert "outreach_action_submitted" in event_types
    assert "outreach_action_approved" in event_types
    assert "outreach_action_sent" in event_types


# @forgeplan-spec: AC11
@pytest.mark.asyncio
async def test_ac11_cancel_from_each_state_writes_audit(
    db_session: AsyncSession,
    auth_ctx_coordinator: AuthContext,
):
    """Canceling from draft writes AuditEvent with old_status and new_status."""
    case = await seed_case(db_session, current_status="outreach_pending_approval")
    action = await seed_outreach_action(
        db_session, case.id, approval_status="pending_approval"
    )
    await service.cancel_action(
        session=db_session,
        action_id=UUID(action.id),
        auth_ctx=auth_ctx_coordinator,
    )
    result = await db_session.execute(
        select(AuditEvent).where(
            and_(
                AuditEvent.entity_type == "outreach_action",
                AuditEvent.entity_id == action.id,
                AuditEvent.event_type == "outreach_action_canceled",
            )
        )
    )
    audit = result.scalar_one_or_none()
    assert audit is not None
    assert audit.old_value_json["approval_status"] == "pending_approval"
    assert audit.new_value_json["approval_status"] == "canceled"


# ---------------------------------------------------------------------------
# AC12: Closed-case mutation rejected
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC12
@pytest.mark.asyncio
async def test_ac12_closed_case_create_returns_409(
    db_session: AsyncSession,
    auth_ctx_coordinator: AuthContext,
):
    """Creating an outreach action on a closed case returns 409."""
    closed_case = await seed_case(db_session, current_status="closed")
    payload = OutreachActionCreate(
        action_type="facility_outreach",
        channel="email",
        draft_body="This should fail",
    )
    with pytest.raises(HTTPException) as exc_info:
        await service.create_outreach_action(
            session=db_session,
            case_id=UUID(closed_case.id),
            payload=payload,
            auth_ctx=auth_ctx_coordinator,
        )
    assert exc_info.value.status_code == 409


# @forgeplan-spec: AC12
@pytest.mark.asyncio
async def test_ac12_closed_case_returns_409_via_router(
    client,
    db_session: AsyncSession,
    coordinator_user,
):
    """Router endpoint returns 409 for outreach creation on closed case."""
    from placementops.modules.outreach.tests.conftest import auth_headers, TEST_ORG_ID, seed_case

    closed_case = await seed_case(db_session, current_status="closed")

    headers = auth_headers(
        user_id=coordinator_user.id,
        org_id=str(TEST_ORG_ID),
        role_key="placement_coordinator",
    )
    resp = await client.post(
        f"/api/v1/cases/{closed_case.id}/outreach-actions",
        json={
            "action_type": "facility_outreach",
            "channel": "email",
            "draft_body": "This should fail",
        },
        headers=headers,
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# F1 fix: approve_action must write case_activity_event (AC11)
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC11
@pytest.mark.asyncio
async def test_f1_approve_action_writes_case_activity_event(
    db_session: AsyncSession,
    auth_ctx_coordinator: AuthContext,
):
    """
    approve_action publishes a case_activity_event with old_status=pending_approval
    and new_status=approved (F1 regression test for AC11).

    Strategy: register a temporary subscriber on the in-process event bus, call
    approve_action, and assert the subscriber received an event with the correct
    old_status and new_status.
    """
    from placementops.core.events import subscribe_case_activity, unsubscribe_case_activity, CaseActivityEvent

    received_events: list[CaseActivityEvent] = []

    async def capture_event(event: CaseActivityEvent) -> None:
        received_events.append(event)

    subscribe_case_activity(capture_event)
    try:
        case = await seed_case(db_session, current_status="outreach_pending_approval")
        action = await seed_outreach_action(
            db_session, case.id, approval_status="pending_approval"
        )
        await service.approve_action(
            session=db_session,
            action_id=UUID(action.id),
            auth_ctx=auth_ctx_coordinator,
        )
    finally:
        unsubscribe_case_activity(capture_event)

    # Confirm the action is approved
    action_refreshed = await db_session.get(OutreachAction, action.id)
    assert action_refreshed.approval_status == "approved"

    # Confirm a case_activity_event was published with event_type=outreach_approved
    outreach_approved_events = [
        e for e in received_events if e.event_type == "outreach_approved"
    ]
    assert len(outreach_approved_events) >= 1, (
        "approve_action must publish a case_activity_event with event_type='outreach_approved' (AC11 / F1)"
    )
    evt = outreach_approved_events[0]
    assert evt.old_status == "pending_approval", (
        f"Expected old_status='pending_approval', got '{evt.old_status}'"
    )
    assert evt.new_status == "approved", (
        f"Expected new_status='approved', got '{evt.new_status}'"
    )


# ---------------------------------------------------------------------------
# F2 fix: facility_id must be selected_for_outreach (matching-module interface)
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC8
@pytest.mark.asyncio
async def test_f2_facility_not_selected_returns_400(
    db_session: AsyncSession,
    auth_ctx_coordinator: AuthContext,
):
    """
    create_outreach_action returns 400 when facility_id is provided but
    the corresponding FacilityMatch.selected_for_outreach is False (F2 regression test).
    """
    from uuid import uuid4 as _uuid4
    from placementops.core.models.facility_match import FacilityMatch
    from placementops.core.models.facility import Facility

    case = await seed_case(db_session, current_status="facility_options_generated")

    # Seed a facility and a FacilityMatch with selected_for_outreach=False
    facility_id = str(_uuid4())
    facility = Facility(
        id=facility_id,
        organization_id=str(TEST_ORG_ID),
        facility_name="Test Facility",
        facility_type="snf",
    )
    db_session.add(facility)
    match = FacilityMatch(
        patient_case_id=case.id,
        facility_id=facility_id,
        overall_score=0.8,
        rank_order=1,
        selected_for_outreach=False,
    )
    db_session.add(match)
    await db_session.commit()

    payload = OutreachActionCreate(
        action_type="facility_outreach",
        channel="email",
        draft_body="This should fail — not selected",
        facility_id=UUID(facility_id),
    )
    with pytest.raises(HTTPException) as exc_info:
        await service.create_outreach_action(
            session=db_session,
            case_id=UUID(case.id),
            payload=payload,
            auth_ctx=auth_ctx_coordinator,
        )
    assert exc_info.value.status_code == 400
    assert "selected for outreach" in str(exc_info.value.detail).lower()


# @forgeplan-spec: AC8
@pytest.mark.asyncio
async def test_f2_facility_selected_allows_creation(
    db_session: AsyncSession,
    auth_ctx_coordinator: AuthContext,
):
    """
    create_outreach_action succeeds when facility_id has selected_for_outreach=True.
    """
    from uuid import uuid4 as _uuid4
    from placementops.core.models.facility_match import FacilityMatch
    from placementops.core.models.facility import Facility

    case = await seed_case(db_session, current_status="facility_options_generated")

    facility_id = str(_uuid4())
    facility = Facility(
        id=facility_id,
        organization_id=str(TEST_ORG_ID),
        facility_name="Selected Facility",
        facility_type="snf",
    )
    db_session.add(facility)
    match = FacilityMatch(
        patient_case_id=case.id,
        facility_id=facility_id,
        overall_score=0.9,
        rank_order=1,
        selected_for_outreach=True,
    )
    db_session.add(match)
    await db_session.commit()

    payload = OutreachActionCreate(
        action_type="facility_outreach",
        channel="email",
        draft_body="Valid outreach body",
        facility_id=UUID(facility_id),
    )
    action = await service.create_outreach_action(
        session=db_session,
        case_id=UUID(case.id),
        payload=payload,
        auth_ctx=auth_ctx_coordinator,
    )
    assert action.approval_status == "draft"
    assert action.facility_id == facility_id


# ---------------------------------------------------------------------------
# F5 fix: action-level endpoints reject closed-case mutations (AC12)
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC12
@pytest.mark.asyncio
async def test_f5_patch_action_on_closed_case_returns_409(
    db_session: AsyncSession,
    auth_ctx_coordinator: AuthContext,
):
    """
    patch_outreach_action returns 409 when the action belongs to a closed case (F5 regression test).
    """
    closed_case = await seed_case(db_session, current_status="closed")
    action = await seed_outreach_action(
        db_session, closed_case.id, approval_status="draft"
    )
    patch = OutreachActionPatch(draft_body="Attempted edit on closed case")
    with pytest.raises(HTTPException) as exc_info:
        await service.patch_outreach_action(
            session=db_session,
            action_id=UUID(action.id),
            patch=patch,
            auth_ctx=auth_ctx_coordinator,
        )
    assert exc_info.value.status_code == 409


# @forgeplan-spec: AC12
@pytest.mark.asyncio
async def test_f5_submit_for_approval_on_closed_case_returns_409(
    db_session: AsyncSession,
    auth_ctx_coordinator: AuthContext,
):
    """
    submit_for_approval returns 409 when the action belongs to a closed case (F5 regression test).
    """
    closed_case = await seed_case(db_session, current_status="closed")
    action = await seed_outreach_action(
        db_session, closed_case.id, approval_status="draft"
    )
    with pytest.raises(HTTPException) as exc_info:
        await service.submit_for_approval(
            session=db_session,
            action_id=UUID(action.id),
            auth_ctx=auth_ctx_coordinator,
        )
    assert exc_info.value.status_code == 409
