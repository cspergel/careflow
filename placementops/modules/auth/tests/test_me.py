# @forgeplan-node: auth-module
"""
Tests for GET /api/v1/auth/me.

AC4: Valid JWT → 200 with user_id, organization_id, role_key, email, full_name.
     Role_key must come from the DB User row, not JWT claims (AC12).
"""
# @forgeplan-spec: AC4
# @forgeplan-spec: AC12

import pytest

from placementops.modules.auth.tests.helpers import (
    TEST_ORG_ID,
    TEST_USER_ID,
    make_jwt,
)


@pytest.mark.asyncio
async def test_me_returns_full_profile(async_client, base_user):
    """
    AC4: GET /api/v1/auth/me with a valid Bearer token returns HTTP 200
    with user_id, organization_id, role_key, email, full_name.
    """
    # @forgeplan-spec: AC4
    token = make_jwt(user_id=base_user.id, org_id=TEST_ORG_ID, role_key=base_user.role_key)

    response = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    body = response.json()

    assert "user_id" in body
    assert "organization_id" in body
    assert "role_key" in body
    assert "email" in body
    assert "full_name" in body

    from uuid import UUID
    assert UUID(body["user_id"]) == UUID(str(base_user.id))
    assert UUID(body["organization_id"]) == UUID(str(base_user.organization_id))
    assert body["role_key"] == base_user.role_key
    assert body["email"] == base_user.email
    assert body["full_name"] == base_user.full_name


@pytest.mark.asyncio
async def test_me_role_key_from_db_not_jwt(async_client, db_session, org):
    """
    AC12: role_key in the response must come from the DB User row.

    Scenario: JWT claims role_key='admin' but DB row has role_key='read_only'.
    Response must return 'read_only' (from DB), not 'admin' (from JWT).
    """
    # @forgeplan-spec: AC12
    from uuid import uuid4
    from placementops.core.models import User

    # Create a user with role_key='read_only' in the DB
    user_id = uuid4()
    user = User(
        id=str(user_id),
        organization_id=str(TEST_ORG_ID),
        email=f"readonly_{str(user_id)[:8]}@example.com",
        full_name="Read Only User",
        role_key="read_only",
        status="active",
    )
    db_session.add(user)
    await db_session.commit()

    # Mint a JWT that claims role_key='admin' (simulating stale claim)
    token = make_jwt(user_id=user_id, org_id=TEST_ORG_ID, role_key="admin")

    response = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    # Must return the DB role_key, not the JWT claim
    assert body["role_key"] == "read_only"


@pytest.mark.asyncio
async def test_me_no_token_returns_401(async_client):
    """GET /api/v1/auth/me without Authorization header returns HTTP 401."""
    response = await async_client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_expired_token_returns_401(async_client, base_user):
    """GET /api/v1/auth/me with an expired token returns HTTP 401."""
    expired_token = make_jwt(
        user_id=base_user.id,
        org_id=TEST_ORG_ID,
        role_key=base_user.role_key,
        expired=True,
    )

    response = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_me_invalid_token_returns_401(async_client):
    """GET /api/v1/auth/me with a malformed token returns HTTP 401."""
    response = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer not.a.real.token"},
    )
    assert response.status_code == 401
