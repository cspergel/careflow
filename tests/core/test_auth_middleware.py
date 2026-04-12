# @forgeplan-node: core-infrastructure
"""
Tests for JWT auth middleware — AC3.

Tests:
  (a) Valid HS256 JWT accepted; AuthContext populated correctly
  (b) Expired JWT → 401
  (c) Missing Authorization header → 401
  (d) org_id extracted from app_metadata (not user_metadata)
"""
# @forgeplan-spec: AC3

import os
import pytest
from uuid import uuid4

from .conftest import make_jwt, TEST_ORG_ID, TEST_USER_ID, TEST_SECRET

pytestmark = pytest.mark.asyncio


async def test_valid_hs256_jwt_accepted(async_client):
    """AC3a: Valid HS256 JWT is accepted; AuthContext populated."""
    token = make_jwt(algorithm="HS256")
    response = await async_client.get(
        "/protected", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == str(TEST_USER_ID)
    assert data["organization_id"] == str(TEST_ORG_ID)
    assert data["role_key"] == "intake_staff"


async def test_expired_jwt_returns_401(async_client):
    """AC3b: Expired JWT returns 401 Unauthorized."""
    token = make_jwt(expired=True)
    response = await async_client.get(
        "/protected", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


async def test_missing_authorization_header_returns_401(async_client):
    """AC3c: No Authorization header returns 401."""
    response = await async_client.get("/protected")
    assert response.status_code == 401


async def test_invalid_token_returns_401(async_client):
    """Invalid/malformed token returns 401."""
    response = await async_client.get(
        "/protected", headers={"Authorization": "Bearer not.a.valid.jwt"}
    )
    assert response.status_code == 401


async def test_wrong_secret_returns_401(async_client):
    """Token signed with wrong secret returns 401."""
    token = make_jwt(secret="wrong-secret-that-is-long-enough-to-be-used")
    response = await async_client.get(
        "/protected", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401


async def test_valid_es256_token_populates_auth_context(async_client, mocker):
    """AC3(d): if SUPABASE_JWKS_URL set, valid ES256 JWT → AuthContext populated."""
    from .conftest import TEST_ORG_ID, TEST_USER_ID
    from datetime import datetime, timedelta, timezone

    # Payload that the mocked jwt.decode will return — mimics a real ES256 token payload
    payload = {
        "sub": str(TEST_USER_ID),
        "aud": "authenticated",
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
        "app_metadata": {
            "organization_id": str(TEST_ORG_ID),
            "role_key": "manager",
        },
    }

    # Patch the module-level _jwks_client so the ES256 branch is reachable even though
    # SUPABASE_JWKS_URL is not set in the test environment.
    mock_signing_key = mocker.MagicMock()
    mock_signing_key.key = "mock-ec-key"
    mock_jwks_client = mocker.MagicMock()
    mock_jwks_client.get_signing_key_from_jwt.return_value = mock_signing_key
    mocker.patch("placementops.core.auth._jwks_client", mock_jwks_client)

    # Patch jwt.get_unverified_header so the middleware sees alg=ES256 in the token header
    mocker.patch(
        "placementops.core.auth.jwt.get_unverified_header",
        return_value={"alg": "ES256"},
    )

    # Patch jwt.decode so we don't need a real EC key pair — the JWKS path is exercised
    mocker.patch("placementops.core.auth.jwt.decode", return_value=payload)

    response = await async_client.get(
        "/protected", headers={"Authorization": "Bearer fake.es256.token"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == str(TEST_USER_ID)
    assert data["organization_id"] == str(TEST_ORG_ID)
    assert data["role_key"] == "manager"


async def test_auth_context_attached_to_request_state(async_client):
    """AuthContext is attached to request.state and accessible in the route."""
    from fastapi import Depends, Request
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    from placementops.core.auth import get_auth_context, AuthContext
    from httpx import AsyncClient, ASGITransport

    app = FastAPI()

    @app.get("/check-state")
    async def check_state(
        request: Request,
        auth: AuthContext = Depends(get_auth_context),
    ):
        # request.state.auth should be set by get_auth_context
        return {"state_auth_user_id": str(request.state.auth.user_id)}

    token = make_jwt()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/check-state", headers={"Authorization": f"Bearer {token}"}
        )
    assert response.status_code == 200
    assert response.json()["state_auth_user_id"] == str(TEST_USER_ID)
