# @forgeplan-node: auth-module
"""
Tests for POST /api/v1/auth/logout.

AC5: Logout returns HTTP 204 and the server-side Supabase session is invalidated.
     Logout calls POST /auth/v1/logout on the Supabase Auth endpoint.
"""
# @forgeplan-spec: AC5

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from placementops.modules.auth.tests.helpers import (
    TEST_ORG_ID,
    make_jwt,
)


def _mock_httpx_post(status_code: int = 204):
    """Build a mock httpx AsyncClient context manager that returns a given status."""
    mock_response = MagicMock()
    mock_response.status_code = status_code

    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    mock_context = MagicMock()
    mock_context.__aenter__ = AsyncMock(return_value=mock_client)
    mock_context.__aexit__ = AsyncMock(return_value=None)

    return mock_context, mock_client


@pytest.mark.asyncio
async def test_logout_returns_204(async_client, base_user):
    """
    AC5: POST /api/v1/auth/logout with a valid token returns HTTP 204.
    """
    # @forgeplan-spec: AC5
    token = make_jwt(user_id=base_user.id, org_id=TEST_ORG_ID, role_key=base_user.role_key)

    mock_ctx, mock_client = _mock_httpx_post(204)

    with patch("httpx.AsyncClient", return_value=mock_ctx):
        response = await async_client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 204, response.text


@pytest.mark.asyncio
async def test_logout_calls_supabase_signout_endpoint(async_client, base_user):
    """
    AC5: Logout must call Supabase server-side signOut — client-side token
    deletion alone is insufficient. Verify POST /auth/v1/logout is called
    with the user's access_token in the Authorization header.
    """
    # @forgeplan-spec: AC5
    token = make_jwt(user_id=base_user.id, org_id=TEST_ORG_ID, role_key=base_user.role_key)

    mock_ctx, mock_client = _mock_httpx_post(204)

    with patch("httpx.AsyncClient", return_value=mock_ctx):
        await async_client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )

    # Verify the POST was called to the Supabase logout endpoint
    mock_client.post.assert_called_once()
    call_args = mock_client.post.call_args

    # URL should be the Supabase logout endpoint
    assert "logout" in call_args[0][0], f"Expected logout URL, got: {call_args[0][0]}"

    # Authorization header must contain the user's access token
    headers = call_args[1].get("headers", {})
    assert headers.get("Authorization") == f"Bearer {token}"


@pytest.mark.asyncio
async def test_logout_no_token_returns_401(async_client):
    """POST /api/v1/auth/logout without Authorization header returns 401."""
    response = await async_client.post("/api/v1/auth/logout")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_expired_token_returns_401(async_client, base_user):
    """POST /api/v1/auth/logout with an expired token returns 401."""
    expired_token = make_jwt(
        user_id=base_user.id,
        org_id=TEST_ORG_ID,
        role_key=base_user.role_key,
        expired=True,
    )
    response = await async_client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_returns_204_even_if_supabase_unreachable(async_client, base_user):
    """
    AC5 edge case: If the Supabase endpoint is unreachable, logout still
    returns HTTP 204. The client discards the token; session expiry handles
    the rest. This prevents UX degradation on Supabase downtime.
    """
    # @forgeplan-spec: AC5
    token = make_jwt(user_id=base_user.id, org_id=TEST_ORG_ID, role_key=base_user.role_key)

    # Simulate network error
    mock_ctx = MagicMock()
    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))
    mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
    mock_ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_ctx):
        response = await async_client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_logout_then_me_with_expired_token_returns_401(async_client, base_user):
    """
    AC5: After logout, a subsequent GET /api/v1/auth/me with the same
    (now revoked) token must return HTTP 401.

    Unit test simulation: use an expired token to verify the /me endpoint
    enforces 401. In production, Supabase rejects revoked tokens via its
    own invalidation mechanism.
    """
    # @forgeplan-spec: AC5
    token = make_jwt(user_id=base_user.id, org_id=TEST_ORG_ID, role_key=base_user.role_key)

    mock_ctx, _ = _mock_httpx_post(204)

    with patch("httpx.AsyncClient", return_value=mock_ctx):
        logout_resp = await async_client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert logout_resp.status_code == 204

    # Use an expired token to simulate token rejection post-logout
    expired_token = make_jwt(
        user_id=base_user.id,
        org_id=TEST_ORG_ID,
        role_key=base_user.role_key,
        expired=True,
    )
    me_resp = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert me_resp.status_code == 401
