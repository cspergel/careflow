# @forgeplan-node: core-infrastructure
"""
Tests for closed-case guard — AC11.

Tests that the check_case_not_closed dependency returns 409 for closed cases
before any handler logic executes.
"""
# @forgeplan-spec: AC11

import pytest
from uuid import uuid4, UUID
from fastapi import FastAPI, Depends
from fastapi import HTTPException
from httpx import AsyncClient, ASGITransport

from placementops.core.database import get_db
from placementops.core.middleware import check_case_not_closed

pytestmark = pytest.mark.asyncio


@pytest.fixture
def app_with_closed_guard(db_session):
    """FastAPI app with check_case_not_closed dependency on write endpoints."""
    app = FastAPI()

    async def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    handler_call_count = {"count": 0}

    @app.patch("/api/v1/cases/{case_id}")
    async def update_case(
        case_id: UUID,
        _: None = Depends(check_case_not_closed()),
    ):
        handler_call_count["count"] += 1
        return {"ok": True}

    @app.post("/api/v1/cases/{case_id}/assessments")
    async def create_assessment(
        case_id: UUID,
        _: None = Depends(check_case_not_closed()),
    ):
        handler_call_count["count"] += 1
        return {"ok": True}

    app.state.handler_call_count = handler_call_count
    return app


async def test_closed_case_returns_409_on_patch(app_with_closed_guard, closed_case):
    """AC11: PATCH on closed case returns HTTP 409."""
    case_id = closed_case.id

    async with AsyncClient(
        transport=ASGITransport(app=app_with_closed_guard), base_url="http://test"
    ) as client:
        response = await client.patch(f"/api/v1/cases/{case_id}", json={})

    assert response.status_code == 409
    assert "closed" in response.json()["detail"].lower()


async def test_closed_case_returns_409_on_post_assessment(
    app_with_closed_guard, closed_case
):
    """AC11: POST on closed case child entity returns HTTP 409."""
    case_id = closed_case.id

    async with AsyncClient(
        transport=ASGITransport(app=app_with_closed_guard), base_url="http://test"
    ) as client:
        response = await client.post(f"/api/v1/cases/{case_id}/assessments", json={})

    assert response.status_code == 409


async def test_handler_not_called_for_closed_case(app_with_closed_guard, closed_case):
    """AC11: Handler body is never entered when case is closed."""
    case_id = closed_case.id
    initial_count = app_with_closed_guard.state.handler_call_count["count"]

    async with AsyncClient(
        transport=ASGITransport(app=app_with_closed_guard), base_url="http://test"
    ) as client:
        await client.patch(f"/api/v1/cases/{case_id}", json={})

    # Handler count must not have incremented — guard raised before handler ran
    assert app_with_closed_guard.state.handler_call_count["count"] == initial_count


async def test_open_case_allows_write(app_with_closed_guard, patient_case):
    """Open case (status=new) passes the guard and hits the handler."""
    case_id = patient_case.id

    async with AsyncClient(
        transport=ASGITransport(app=app_with_closed_guard), base_url="http://test"
    ) as client:
        response = await client.patch(f"/api/v1/cases/{case_id}", json={})

    assert response.status_code == 200


async def test_nonexistent_case_returns_404(app_with_closed_guard):
    """Non-existent case_id returns 404 from the guard."""
    fake_id = uuid4()

    async with AsyncClient(
        transport=ASGITransport(app=app_with_closed_guard), base_url="http://test"
    ) as client:
        response = await client.patch(f"/api/v1/cases/{fake_id}", json={})

    assert response.status_code == 404
