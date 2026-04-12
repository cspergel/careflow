# @forgeplan-node: core-infrastructure
"""
Tests for AC12 — org_id must come from app_metadata, NOT user_metadata.

Verifies that a JWT with organization_id in user_metadata (not app_metadata)
is rejected with 401, and that the AuthContext is not populated with that org_id.
"""
# @forgeplan-spec: AC12

import pytest

from .conftest import make_jwt, TEST_ORG_ID

pytestmark = pytest.mark.asyncio


async def test_org_in_user_metadata_only_returns_401(async_client):
    """AC12: JWT with org_id only in user_metadata is rejected with 401."""
    token = make_jwt(put_org_in_user_metadata=True)

    response = await async_client.get(
        "/protected", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 401
    # Must not leak the org ID in the response
    assert str(TEST_ORG_ID) not in response.text


async def test_org_in_app_metadata_is_accepted(async_client):
    """AC12: JWT with org_id in app_metadata is accepted and AuthContext populated."""
    token = make_jwt(put_org_in_user_metadata=False)

    response = await async_client.get(
        "/protected", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["organization_id"] == str(TEST_ORG_ID)


async def test_auth_context_not_populated_from_user_metadata(async_client):
    """AC12: Even if user_metadata has org_id, AuthContext uses app_metadata."""
    # Token has org B in user_metadata but no app_metadata org — should fail
    token = make_jwt(put_org_in_user_metadata=True)

    response = await async_client.get(
        "/protected", headers={"Authorization": f"Bearer {token}"}
    )
    # Must NOT succeed — no app_metadata org_id means 401
    assert response.status_code == 401
