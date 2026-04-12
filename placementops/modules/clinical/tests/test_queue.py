# @forgeplan-node: clinical-module
"""
AC1 — Clinical reviewer queue tests.

GET /api/v1/queues/clinical returns cases at needs_clinical_review
scoped to the authenticated user's organization.
"""
# @forgeplan-spec: AC1

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.modules.clinical.tests.conftest import (
    _seed_case,
    _seed_user,
    auth_headers,
    make_id,
)
from placementops.core.models import PatientCase, Organization


@pytest.mark.asyncio
async def test_queue_returns_only_org_scoped_cases(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org: str,
    seed_org2: str,
    clinical_reviewer: dict,
):
    """
    AC1: cases from another org must NOT appear in the reviewer queue.
    """
    # Seed two cases in seed_org at needs_clinical_review
    case1 = await _seed_case(db_session, seed_org, "needs_clinical_review")
    case2 = await _seed_case(db_session, seed_org, "needs_clinical_review")

    # Seed one case in seed_org2 — should NOT appear in org1's queue
    other_case = await _seed_case(db_session, seed_org2, "needs_clinical_review")

    headers = auth_headers(
        clinical_reviewer["user_id"],
        clinical_reviewer["org_id"],
        "clinical_reviewer",
    )
    resp = await client.get("/api/v1/queues/clinical", headers=headers)
    assert resp.status_code == 200, resp.text

    data = resp.json()
    returned_ids = {c["id"] for c in data["cases"]}

    assert case1.id in returned_ids
    assert case2.id in returned_ids
    assert other_case.id not in returned_ids, "Cross-org case must not appear in queue"


@pytest.mark.asyncio
async def test_queue_excludes_non_clinical_statuses(
    client: AsyncClient,
    db_session: AsyncSession,
    seed_org: str,
    clinical_reviewer: dict,
):
    """
    AC1: only needs_clinical_review cases appear; under_clinical_review and others excluded.
    """
    ncr_case = await _seed_case(db_session, seed_org, "needs_clinical_review")
    ucr_case = await _seed_case(db_session, seed_org, "under_clinical_review")
    ready_case = await _seed_case(db_session, seed_org, "ready_for_matching")

    headers = auth_headers(
        clinical_reviewer["user_id"],
        clinical_reviewer["org_id"],
        "clinical_reviewer",
    )
    resp = await client.get("/api/v1/queues/clinical", headers=headers)
    assert resp.status_code == 200

    returned_ids = {c["id"] for c in resp.json()["cases"]}
    assert ncr_case.id in returned_ids
    assert ucr_case.id not in returned_ids
    assert ready_case.id not in returned_ids


@pytest.mark.asyncio
async def test_queue_requires_authentication(client: AsyncClient):
    """Queue endpoint rejects unauthenticated requests."""
    resp = await client.get("/api/v1/queues/clinical")
    assert resp.status_code == 401
