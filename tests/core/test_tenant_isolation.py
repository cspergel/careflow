# @forgeplan-node: core-infrastructure
"""
Tests for organization_id tenant isolation — AC4.

Tests that require_org_match raises 403 when org IDs don't match.
Also verifies no data leakage in the 403 response.
"""
# @forgeplan-spec: AC4

import pytest
from uuid import uuid4
from fastapi import HTTPException

from placementops.core.auth import AuthContext, require_org_match
from .conftest import TEST_ORG_ID, TEST_ORG_ID_B, TEST_USER_ID


def test_require_org_match_same_org_passes():
    """Same org — no exception raised."""
    auth = AuthContext(
        user_id=TEST_USER_ID,
        organization_id=TEST_ORG_ID,
        role_key="intake_staff",
    )
    # Should not raise
    require_org_match(str(TEST_ORG_ID), auth)


def test_require_org_match_different_org_raises_403():
    """Different org — raises HTTP 403."""
    auth = AuthContext(
        user_id=TEST_USER_ID,
        organization_id=TEST_ORG_ID,
        role_key="intake_staff",
    )
    with pytest.raises(HTTPException) as exc_info:
        require_org_match(str(TEST_ORG_ID_B), auth)
    assert exc_info.value.status_code == 403


def test_403_response_contains_no_org_b_data():
    """403 response detail does not leak org B data."""
    auth = AuthContext(
        user_id=TEST_USER_ID,
        organization_id=TEST_ORG_ID,
        role_key="intake_staff",
    )
    sensitive_org_b_id = str(TEST_ORG_ID_B)
    with pytest.raises(HTTPException) as exc_info:
        require_org_match(sensitive_org_b_id, auth)
    # The detail must not expose the org B UUID
    detail = str(exc_info.value.detail)
    assert sensitive_org_b_id not in detail


def test_require_org_match_accepts_uuid_or_string():
    """require_org_match accepts both UUID objects and str UUIDs."""
    auth = AuthContext(
        user_id=TEST_USER_ID,
        organization_id=TEST_ORG_ID,
        role_key="admin",
    )
    # Should not raise for either form
    require_org_match(TEST_ORG_ID, auth)
    require_org_match(str(TEST_ORG_ID), auth)


@pytest.mark.asyncio
async def test_tenant_isolation_via_api(async_client, org, org_b, patient_case):
    """
    AC4 integration: authenticated as org_a user; no access to org_b data.
    This test validates the require_org_match behavior at the HTTP level.
    """
    from fastapi import Depends, FastAPI
    from fastapi.exceptions import HTTPException
    from httpx import AsyncClient, ASGITransport
    from uuid import UUID

    from placementops.core.auth import AuthContext, get_auth_context, require_org_match
    from .conftest import make_jwt, TEST_ORG_ID, TEST_ORG_ID_B

    app = FastAPI()

    @app.get("/cases/{resource_org_id}/check")
    async def check_org(
        resource_org_id: UUID,
        auth: AuthContext = Depends(get_auth_context),
    ):
        require_org_match(resource_org_id, auth)
        return {"ok": True}

    # Token for org A user
    token_org_a = make_jwt(org_id=TEST_ORG_ID)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Access org A resource — should succeed
        r = await client.get(
            f"/cases/{TEST_ORG_ID}/check",
            headers={"Authorization": f"Bearer {token_org_a}"},
        )
        assert r.status_code == 200

        # Access org B resource — should fail with 403
        r = await client.get(
            f"/cases/{TEST_ORG_ID_B}/check",
            headers={"Authorization": f"Bearer {token_org_a}"},
        )
        assert r.status_code == 403
        # No org B ID in the response body
        assert str(TEST_ORG_ID_B) not in r.text
