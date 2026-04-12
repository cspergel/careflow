# @forgeplan-node: auth-module
"""
Tests for POST /api/v1/auth/login.

AC1: Valid credentials → 200 LoginResponse with all required fields
AC2: Invalid credentials → 401
AC13: Successful login writes AuditEvent(entity_type=user, event_type=login, actor_user_id=user.id)
"""
# @forgeplan-spec: AC1
# @forgeplan-spec: AC2
# @forgeplan-spec: AC13

from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest
from sqlalchemy import select

from placementops.core.models import AuditEvent
from placementops.modules.auth.tests.helpers import TEST_ORG_ID, TEST_USER_ID


# ── Supabase mock helpers ─────────────────────────────────────────────────────

def _make_supabase_success_response(user_id: str, org_id: str = None) -> MagicMock:
    """Build a mock Supabase auth response for a successful sign-in."""
    mock_resp = MagicMock()
    mock_resp.session = MagicMock()
    mock_resp.session.access_token = "test.jwt.token"
    mock_resp.session.expires_in = 3600
    mock_resp.user = MagicMock()
    mock_resp.user.id = user_id
    return mock_resp


# ── AC1: Successful login ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_success(async_client, base_user):
    """
    AC1: POST /api/v1/auth/login with valid credentials returns 200
    with LoginResponse containing all required fields.
    """
    # @forgeplan-spec: AC1
    mock_resp = _make_supabase_success_response(str(base_user.id))

    with patch("placementops.modules.auth.service._get_supabase_client") as mock_factory:
        mock_supabase = MagicMock()
        mock_supabase.auth.sign_in_with_password.return_value = mock_resp
        mock_factory.return_value = mock_supabase

        response = await async_client.post(
            "/api/v1/auth/login",
            json={"email": base_user.email, "password": "ValidPassword1!"},
        )

    assert response.status_code == 200, response.text
    body = response.json()

    # All LoginResponse fields must be present
    assert "access_token" in body
    assert body["access_token"] == "test.jwt.token"
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 3600
    assert "user_id" in body
    assert UUID(body["user_id"]) == UUID(str(base_user.id))
    assert "organization_id" in body
    assert UUID(body["organization_id"]) == UUID(str(base_user.organization_id))
    assert "role_key" in body
    assert body["role_key"] == base_user.role_key


@pytest.mark.asyncio
async def test_login_response_token_is_non_empty(async_client, base_user):
    """AC1: access_token must be a non-empty string."""
    # @forgeplan-spec: AC1
    mock_resp = _make_supabase_success_response(str(base_user.id))

    with patch("placementops.modules.auth.service._get_supabase_client") as mock_factory:
        mock_supabase = MagicMock()
        mock_supabase.auth.sign_in_with_password.return_value = mock_resp
        mock_factory.return_value = mock_supabase

        response = await async_client.post(
            "/api/v1/auth/login",
            json={"email": base_user.email, "password": "ValidPassword1!"},
        )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["access_token"], str)
    assert len(body["access_token"]) > 0


# ── AC2: Invalid credentials → 401 ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_invalid_credentials(async_client, base_user):
    """
    AC2: POST /api/v1/auth/login with wrong password returns HTTP 401.
    Response body must NOT contain an access_token.
    """
    # @forgeplan-spec: AC2
    with patch("placementops.modules.auth.service._get_supabase_client") as mock_factory:
        mock_supabase = MagicMock()
        mock_supabase.auth.sign_in_with_password.side_effect = Exception(
            "Invalid login credentials"
        )
        mock_factory.return_value = mock_supabase

        response = await async_client.post(
            "/api/v1/auth/login",
            json={"email": base_user.email, "password": "WrongPassword!"},
        )

    assert response.status_code == 401
    body = response.json()
    assert "access_token" not in body


@pytest.mark.asyncio
async def test_login_null_session_returns_401(async_client, base_user):
    """AC2: If Supabase returns a response with None session, return 401."""
    # @forgeplan-spec: AC2
    mock_resp = MagicMock()
    mock_resp.session = None

    with patch("placementops.modules.auth.service._get_supabase_client") as mock_factory:
        mock_supabase = MagicMock()
        mock_supabase.auth.sign_in_with_password.return_value = mock_resp
        mock_factory.return_value = mock_supabase

        response = await async_client.post(
            "/api/v1/auth/login",
            json={"email": base_user.email, "password": "SomePassword1!"},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_missing_password_returns_422(async_client):
    """Input validation: missing password field returns 422 Unprocessable Entity."""
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_invalid_email_returns_422(async_client):
    """Input validation: invalid email format returns 422."""
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "not-an-email", "password": "Password1!"},
    )
    assert response.status_code == 422


# ── AC13: Login writes AuditEvent ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_writes_audit_event(async_client, db_session, base_user):
    """
    AC13: After a successful login, an AuditEvent row must exist with:
      - entity_type = 'user'
      - event_type = 'login'
      - actor_user_id = authenticated user's id
      - organization_id = user's organization_id
    """
    # @forgeplan-spec: AC13
    mock_resp = _make_supabase_success_response(str(base_user.id))

    with patch("placementops.modules.auth.service._get_supabase_client") as mock_factory:
        mock_supabase = MagicMock()
        mock_supabase.auth.sign_in_with_password.return_value = mock_resp
        mock_factory.return_value = mock_supabase

        response = await async_client.post(
            "/api/v1/auth/login",
            json={"email": base_user.email, "password": "ValidPassword1!"},
        )

    assert response.status_code == 200

    # Query the AuditEvent table
    result = await db_session.execute(
        select(AuditEvent).where(
            AuditEvent.event_type == "login",
            AuditEvent.actor_user_id == str(base_user.id),
        )
    )
    audit_rows = result.scalars().all()

    assert len(audit_rows) == 1, f"Expected 1 audit row, found {len(audit_rows)}"
    audit_row = audit_rows[0]
    assert audit_row.entity_type == "user"
    assert audit_row.event_type == "login"
    assert audit_row.actor_user_id == str(base_user.id)
    assert audit_row.entity_id == str(base_user.id)
    assert audit_row.organization_id == str(base_user.organization_id)
