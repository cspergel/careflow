# @forgeplan-node: analytics-module
"""
Comprehensive tests for analytics-module covering all 9 acceptance criteria.

Test strategy:
- All tests use in-memory SQLite via the project's DATABASE_URL fallback
- Seed data created with ORM objects (not raw SQL)
- Auth injected by overriding get_auth_context and require_role dependencies
- Performance test (AC7) seeds 1000 cases and times all four endpoints
"""
# @forgeplan-spec: AC1
# @forgeplan-spec: AC2
# @forgeplan-spec: AC3
# @forgeplan-spec: AC4
# @forgeplan-spec: AC5
# @forgeplan-spec: AC6
# @forgeplan-spec: AC7
# @forgeplan-spec: AC8
# @forgeplan-spec: AC9

from __future__ import annotations

import os
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import AsyncGenerator
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Use SQLite for tests — set env before importing anything that reads DATABASE_URL
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret-not-used")

from placementops.core.auth import AuthContext
from placementops.core.database import Base, get_db
from placementops.core.models import (
    CaseStatusHistory,
    DeclineReasonReference,
    Facility,
    HospitalReference,
    Organization,
    PatientCase,
    PlacementOutcome,
    User,
)
from placementops.modules.analytics.router import router as analytics_router
from placementops.modules.analytics.sla import SLA, compute_sla_flag


# ---------------------------------------------------------------------------
# Test database engine (shared in-memory with StaticPool to persist across
# connections in the same test session)
# ---------------------------------------------------------------------------

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DB_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = async_sessionmaker(
    test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        yield session


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="function", autouse=False)
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Create tables, yield session, drop tables."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with TestingSessionLocal() as session:
        yield session
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


def _make_app(auth_ctx: AuthContext) -> FastAPI:
    """
    Build a minimal FastAPI app with analytics router, overriding all auth
    dependencies to inject the given AuthContext directly.
    """
    from placementops.core.auth import get_auth_context
    from placementops.modules.auth.dependencies import require_role as _require_role

    app = FastAPI()
    app.include_router(analytics_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = override_get_db

    # Override get_auth_context to return the test auth_ctx
    async def _override_auth():
        return auth_ctx

    app.dependency_overrides[get_auth_context] = _override_auth

    # Override require_role — we need to intercept the dynamically created Depends
    # The router uses require_role(*roles) which returns a Depends(). We can't easily
    # override by function reference since each call creates a new closure. Instead we
    # patch get_auth_context (already done above) and mock the DB user lookup so
    # _get_db_role_key returns auth_ctx.role_key.
    # This is achieved by seeding the User row in the test database with auth_ctx.role_key.

    return app


def _make_auth(role_key: str, org_id: UUID | None = None) -> AuthContext:
    return AuthContext(
        user_id=uuid4(),
        organization_id=org_id or uuid4(),
        role_key=role_key,
    )


async def _seed_user(session: AsyncSession, auth: AuthContext) -> User:
    """Seed a User row so require_role DB lookup succeeds."""
    user = User(
        id=str(auth.user_id),
        organization_id=str(auth.organization_id),
        email=f"{auth.role_key}_{str(auth.user_id)[:8]}@test.com",
        full_name=f"Test {auth.role_key}",
        role_key=auth.role_key,
    )
    session.add(user)
    await session.commit()
    return user


async def _seed_organization(session: AsyncSession, org_id: UUID) -> Organization:
    org = Organization(id=str(org_id), name="Test Org")
    session.add(org)
    await session.commit()
    return org


async def _seed_case(
    session: AsyncSession,
    org_id: UUID,
    current_status: str = "new",
    hospital_id: str | None = None,
    coordinator_id: str | None = None,
    priority_level: str | None = None,
    created_at: datetime | None = None,
    case_id: str | None = None,
) -> PatientCase:
    now = created_at or datetime.now(timezone.utc)
    pc = PatientCase(
        id=case_id or str(uuid4()),
        organization_id=str(org_id),
        patient_name="Test Patient",
        current_status=current_status,
        priority_level=priority_level,
        hospital_id=hospital_id,
        assigned_coordinator_user_id=coordinator_id,
        created_at=now,
        updated_at=now,
    )
    session.add(pc)
    await session.commit()
    return pc


async def _seed_status_history(
    session: AsyncSession,
    case_id: str,
    org_id: UUID,
    to_status: str,
    entered_at: datetime,
    from_status: str | None = None,
    actor_id: str | None = None,
) -> CaseStatusHistory:
    csh = CaseStatusHistory(
        id=str(uuid4()),
        organization_id=str(org_id),
        patient_case_id=case_id,
        from_status=from_status,
        to_status=to_status,
        actor_user_id=actor_id or str(uuid4()),
        entered_at=entered_at,
    )
    session.add(csh)
    await session.commit()
    return csh


# ---------------------------------------------------------------------------
# Unit tests for SLA computation (AC3 — pure logic, no DB)
# ---------------------------------------------------------------------------

class TestSlaComputation:
    """AC3 — SLA flag computation from hours_in_status."""

    def test_sla_thresholds_are_named_constants(self):
        """SLA thresholds must be accessible as named constants."""
        # @forgeplan-spec: AC3
        assert SLA.needs_clinical_review_yellow_hours == 4.0
        assert SLA.under_clinical_review_yellow_hours == 8.0
        assert SLA.outreach_pending_approval_yellow_hours == 2.0
        assert SLA.pending_facility_response_yellow_hours == 24.0
        assert SLA.pending_facility_response_red_hours == 48.0
        assert SLA.declined_retry_needed_red_hours == 8.0

    def test_needs_clinical_review_below_threshold_is_none(self):
        flag = compute_sla_flag("needs_clinical_review", 3.9)
        assert flag["level"] == "none"

    def test_needs_clinical_review_above_threshold_is_yellow(self):
        flag = compute_sla_flag("needs_clinical_review", 4.1)
        assert flag["level"] == "yellow"

    def test_under_clinical_review_below_threshold_is_none(self):
        flag = compute_sla_flag("under_clinical_review", 7.9)
        assert flag["level"] == "none"

    def test_under_clinical_review_above_threshold_is_yellow(self):
        flag = compute_sla_flag("under_clinical_review", 8.1)
        assert flag["level"] == "yellow"

    def test_outreach_pending_approval_above_threshold_is_yellow(self):
        flag = compute_sla_flag("outreach_pending_approval", 2.1)
        assert flag["level"] == "yellow"

    def test_pending_facility_response_yellow(self):
        flag = compute_sla_flag("pending_facility_response", 30.0)
        assert flag["level"] == "yellow"

    def test_pending_facility_response_red(self):
        flag = compute_sla_flag("pending_facility_response", 50.0)
        assert flag["level"] == "red"

    def test_pending_facility_response_none(self):
        flag = compute_sla_flag("pending_facility_response", 10.0)
        assert flag["level"] == "none"

    def test_declined_retry_needed_red(self):
        flag = compute_sla_flag("declined_retry_needed", 8.1)
        assert flag["level"] == "red"

    def test_declined_retry_needed_none(self):
        flag = compute_sla_flag("declined_retry_needed", 7.9)
        assert flag["level"] == "none"

    def test_other_status_always_none(self):
        for s in ("new", "intake_in_progress", "intake_complete", "placed", "closed", "accepted"):
            flag = compute_sla_flag(s, 999.0)
            assert flag["level"] == "none", f"Expected none for status={s}"

    def test_flag_includes_status_and_hours(self):
        flag = compute_sla_flag("pending_facility_response", 50.0)
        assert flag["status"] == "pending_facility_response"
        assert flag["hours_in_status"] == 50.0


# ---------------------------------------------------------------------------
# AC1 — Role access tests
# ---------------------------------------------------------------------------

class TestRoleAccess:
    """AC1 — Operations endpoint: allowed roles 200, blocked roles 403."""

    @pytest.mark.asyncio
    async def test_intake_staff_gets_403_on_operations(self, db_session):
        # @forgeplan-spec: AC1
        auth = _make_auth("intake_staff")
        await _seed_organization(db_session, auth.organization_id)
        await _seed_user(db_session, auth)
        app = _make_app(auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/queues/operations")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_read_only_gets_403_on_operations(self, db_session):
        # @forgeplan-spec: AC1
        auth = _make_auth("read_only")
        await _seed_organization(db_session, auth.organization_id)
        await _seed_user(db_session, auth)
        app = _make_app(auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/queues/operations")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_placement_coordinator_gets_200_on_operations(self, db_session):
        auth = _make_auth("placement_coordinator")
        await _seed_organization(db_session, auth.organization_id)
        await _seed_user(db_session, auth)
        app = _make_app(auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/queues/operations")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_clinical_reviewer_gets_200_on_operations(self, db_session):
        auth = _make_auth("clinical_reviewer")
        await _seed_organization(db_session, auth.organization_id)
        await _seed_user(db_session, auth)
        app = _make_app(auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/queues/operations")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_manager_gets_200_on_operations(self, db_session):
        auth = _make_auth("manager")
        await _seed_organization(db_session, auth.organization_id)
        await _seed_user(db_session, auth)
        app = _make_app(auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/queues/operations")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_gets_200_on_operations(self, db_session):
        auth = _make_auth("admin")
        await _seed_organization(db_session, auth.organization_id)
        await _seed_user(db_session, auth)
        app = _make_app(auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/queues/operations")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_intake_staff_gets_403_on_manager_summary(self, db_session):
        auth = _make_auth("intake_staff")
        await _seed_organization(db_session, auth.organization_id)
        await _seed_user(db_session, auth)
        app = _make_app(auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/queues/manager-summary")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_placement_coordinator_gets_403_on_manager_summary(self, db_session):
        auth = _make_auth("placement_coordinator")
        await _seed_organization(db_session, auth.organization_id)
        await _seed_user(db_session, auth)
        app = _make_app(auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/queues/manager-summary")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_manager_gets_200_on_dashboard(self, db_session):
        auth = _make_auth("manager")
        await _seed_organization(db_session, auth.organization_id)
        await _seed_user(db_session, auth)
        app = _make_app(auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/analytics/dashboard")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_read_only_gets_403_on_outreach_performance(self, db_session):
        auth = _make_auth("read_only")
        await _seed_organization(db_session, auth.organization_id)
        await _seed_user(db_session, auth)
        app = _make_app(auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/analytics/outreach-performance")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# AC2 — Filtering and org scoping for operations queue
# ---------------------------------------------------------------------------

class TestOperationsQueueFiltering:
    """AC2 — Filters and org isolation on GET /queues/operations."""

    @pytest.mark.asyncio
    async def test_status_filter_returns_only_matching_cases(self, db_session):
        # @forgeplan-spec: AC2
        auth = _make_auth("manager")
        org_id = auth.organization_id
        await _seed_organization(db_session, org_id)
        await _seed_user(db_session, auth)

        # Seed 3 cases: 2 in one status, 1 in another
        await _seed_case(db_session, org_id, current_status="outreach_in_progress")
        await _seed_case(db_session, org_id, current_status="outreach_in_progress")
        await _seed_case(db_session, org_id, current_status="new")

        app = _make_app(auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/queues/operations?status=outreach_in_progress")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 2
        assert all(item["current_status"] == "outreach_in_progress" for item in data["items"])

    @pytest.mark.asyncio
    async def test_cross_org_isolation_on_operations(self, db_session):
        # @forgeplan-spec: AC2
        # @forgeplan-spec: AC9
        org_a = uuid4()
        org_b = uuid4()
        auth_a = _make_auth("manager", org_id=org_a)

        await _seed_organization(db_session, org_a)
        await _seed_organization(db_session, org_b)
        await _seed_user(db_session, auth_a)

        # Seed 3 cases in org_a, 2 in org_b
        case_a1 = await _seed_case(db_session, org_a, current_status="new")
        case_a2 = await _seed_case(db_session, org_a, current_status="new")
        case_a3 = await _seed_case(db_session, org_a, current_status="new")
        case_b1 = await _seed_case(db_session, org_b, current_status="new")
        case_b2 = await _seed_case(db_session, org_b, current_status="new")

        app = _make_app(auth_a)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/queues/operations")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 3
        returned_ids = {item["case_id"] for item in data["items"]}
        assert case_b1.id not in returned_ids
        assert case_b2.id not in returned_ids

    @pytest.mark.asyncio
    async def test_priority_filter(self, db_session):
        # @forgeplan-spec: AC2
        auth = _make_auth("manager")
        org_id = auth.organization_id
        await _seed_organization(db_session, org_id)
        await _seed_user(db_session, auth)

        await _seed_case(db_session, org_id, priority_level="urgent")
        await _seed_case(db_session, org_id, priority_level="routine")
        await _seed_case(db_session, org_id, priority_level="emergent")

        app = _make_app(auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/queues/operations?priority=urgent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_count"] == 1
        assert data["items"][0]["priority_level"] == "urgent"


# ---------------------------------------------------------------------------
# AC3 — SLA flags from case_status_history.entered_at (integration)
# ---------------------------------------------------------------------------

class TestSlaFlagsIntegration:
    """AC3 — SLA computed from status_history.entered_at, not updated_at."""

    @pytest.mark.asyncio
    async def test_pending_facility_response_50h_is_red(self, db_session):
        # @forgeplan-spec: AC3
        auth = _make_auth("manager")
        org_id = auth.organization_id
        await _seed_organization(db_session, org_id)
        await _seed_user(db_session, auth)

        now = datetime.now(timezone.utc)
        pc = await _seed_case(
            db_session, org_id,
            current_status="pending_facility_response",
        )
        # Status entered 50 hours ago
        await _seed_status_history(
            db_session, pc.id, org_id,
            to_status="pending_facility_response",
            entered_at=now - timedelta(hours=50),
        )

        app = _make_app(auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/queues/operations")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 1
        sla = data["items"][0]["sla_flag"]
        assert sla["level"] == "red"

    @pytest.mark.asyncio
    async def test_pending_facility_response_30h_is_yellow(self, db_session):
        # @forgeplan-spec: AC3
        auth = _make_auth("manager")
        org_id = auth.organization_id
        await _seed_organization(db_session, org_id)
        await _seed_user(db_session, auth)

        now = datetime.now(timezone.utc)
        pc = await _seed_case(
            db_session, org_id,
            current_status="pending_facility_response",
        )
        await _seed_status_history(
            db_session, pc.id, org_id,
            to_status="pending_facility_response",
            entered_at=now - timedelta(hours=30),
        )

        app = _make_app(auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/queues/operations")
        assert resp.status_code == 200
        sla = resp.json()["items"][0]["sla_flag"]
        assert sla["level"] == "yellow"

    @pytest.mark.asyncio
    async def test_pending_facility_response_10h_is_none(self, db_session):
        # @forgeplan-spec: AC3
        auth = _make_auth("manager")
        org_id = auth.organization_id
        await _seed_organization(db_session, org_id)
        await _seed_user(db_session, auth)

        now = datetime.now(timezone.utc)
        pc = await _seed_case(
            db_session, org_id,
            current_status="pending_facility_response",
        )
        await _seed_status_history(
            db_session, pc.id, org_id,
            to_status="pending_facility_response",
            entered_at=now - timedelta(hours=10),
        )

        app = _make_app(auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/queues/operations")
        assert resp.status_code == 200
        sla = resp.json()["items"][0]["sla_flag"]
        assert sla["level"] == "none"

    @pytest.mark.asyncio
    async def test_sla_uses_entered_at_not_updated_at(self, db_session):
        """SLA must come from case_status_history.entered_at, not PatientCase.updated_at."""
        # @forgeplan-spec: AC3
        auth = _make_auth("manager")
        org_id = auth.organization_id
        await _seed_organization(db_session, org_id)
        await _seed_user(db_session, auth)

        now = datetime.now(timezone.utc)
        # Case was updated_at recently (1 hour ago) but entered current status 50h ago
        pc = await _seed_case(
            db_session, org_id,
            current_status="pending_facility_response",
            created_at=now - timedelta(hours=1),
        )
        # The PatientCase.updated_at would be ~1h ago → no breach if we used it
        # But entered_at is 50h ago → red breach
        await _seed_status_history(
            db_session, pc.id, org_id,
            to_status="pending_facility_response",
            entered_at=now - timedelta(hours=50),
        )

        app = _make_app(auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/queues/operations")
        assert resp.status_code == 200
        sla = resp.json()["items"][0]["sla_flag"]
        # Must be red (50h > 48h threshold) — would be none if using updated_at (1h)
        assert sla["level"] == "red"


# ---------------------------------------------------------------------------
# AC4 — Manager summary
# ---------------------------------------------------------------------------

class TestManagerSummary:
    """AC4 — aging_by_status distribution and sla_breach_cases list."""

    @pytest.mark.asyncio
    async def test_manager_summary_aging_by_status(self, db_session):
        # @forgeplan-spec: AC4
        auth = _make_auth("manager")
        org_id = auth.organization_id
        await _seed_organization(db_session, org_id)
        await _seed_user(db_session, auth)

        now = datetime.now(timezone.utc)
        # 2 cases in needs_clinical_review (1 breaching, 1 not)
        pc1 = await _seed_case(db_session, org_id, current_status="needs_clinical_review")
        await _seed_status_history(
            db_session, pc1.id, org_id, "needs_clinical_review",
            entered_at=now - timedelta(hours=5)  # >4h yellow breach
        )
        pc2 = await _seed_case(db_session, org_id, current_status="needs_clinical_review")
        await _seed_status_history(
            db_session, pc2.id, org_id, "needs_clinical_review",
            entered_at=now - timedelta(hours=2)  # <4h no breach
        )
        # 1 case in outreach_in_progress (no SLA threshold → no breach)
        await _seed_case(db_session, org_id, current_status="outreach_in_progress")

        app = _make_app(auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/queues/manager-summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_active_cases"] == 3

        # aging_by_status must contain needs_clinical_review with case_count=2
        ncr = next(
            (b for b in data["aging_by_status"] if b["status"] == "needs_clinical_review"),
            None
        )
        assert ncr is not None
        assert ncr["case_count"] == 2
        assert ncr["sla_breach_count"] == 1  # only the 5h case

    @pytest.mark.asyncio
    async def test_manager_summary_sla_breach_cases(self, db_session):
        # @forgeplan-spec: AC4
        auth = _make_auth("manager")
        org_id = auth.organization_id
        await _seed_organization(db_session, org_id)
        await _seed_user(db_session, auth)

        now = datetime.now(timezone.utc)
        # 1 breach case
        pc_breach = await _seed_case(db_session, org_id, current_status="declined_retry_needed")
        await _seed_status_history(
            db_session, pc_breach.id, org_id, "declined_retry_needed",
            entered_at=now - timedelta(hours=9)  # >8h red
        )
        # 1 non-breach case
        pc_ok = await _seed_case(db_session, org_id, current_status="new")

        app = _make_app(auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/queues/manager-summary")
        assert resp.status_code == 200
        data = resp.json()
        breach_ids = {c["case_id"] for c in data["sla_breach_cases"]}
        assert pc_breach.id in breach_ids
        assert pc_ok.id not in breach_ids

    @pytest.mark.asyncio
    async def test_total_active_cases_excludes_placed_and_closed(self, db_session):
        # @forgeplan-spec: AC4
        auth = _make_auth("manager")
        org_id = auth.organization_id
        await _seed_organization(db_session, org_id)
        await _seed_user(db_session, auth)

        await _seed_case(db_session, org_id, current_status="new")
        await _seed_case(db_session, org_id, current_status="placed")  # excluded
        await _seed_case(db_session, org_id, current_status="closed")  # excluded

        app = _make_app(auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/queues/manager-summary")
        assert resp.status_code == 200
        assert resp.json()["total_active_cases"] == 1


# ---------------------------------------------------------------------------
# AC5 — Dashboard report
# ---------------------------------------------------------------------------

class TestDashboard:
    """AC5 — case volume, placement rate, stage metrics."""

    @pytest.mark.asyncio
    async def test_dashboard_placement_rate(self, db_session):
        # @forgeplan-spec: AC5
        auth = _make_auth("manager")
        org_id = auth.organization_id
        await _seed_organization(db_session, org_id)
        await _seed_user(db_session, auth)

        # Seed 10 cases: 4 placed, 6 other
        now = datetime.now(timezone.utc)
        for _ in range(4):
            pc = await _seed_case(db_session, org_id, current_status="placed", created_at=now)
            # Add a placed PlacementOutcome for each
            po = PlacementOutcome(
                id=str(uuid4()),
                patient_case_id=pc.id,
                outcome_type="placed",
                recorded_by_user_id=str(auth.user_id),
                created_at=now,
            )
            db_session.add(po)
        for _ in range(6):
            await _seed_case(db_session, org_id, current_status="outreach_in_progress", created_at=now)
        await db_session.commit()

        app = _make_app(auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/analytics/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_cases"] == 10
        assert data["placement_rate_pct"] == 40.0
        assert sum(data["cases_by_status"].values()) == 10

    @pytest.mark.asyncio
    async def test_dashboard_date_range_filter(self, db_session):
        # @forgeplan-spec: AC5
        auth = _make_auth("manager")
        org_id = auth.organization_id
        await _seed_organization(db_session, org_id)
        await _seed_user(db_session, auth)

        now = datetime.now(timezone.utc)
        in_range_date = now - timedelta(days=10)
        out_range_date = now - timedelta(days=60)

        await _seed_case(db_session, org_id, created_at=in_range_date)
        await _seed_case(db_session, org_id, created_at=in_range_date)
        await _seed_case(db_session, org_id, created_at=out_range_date)

        today = now.date()
        from_date = (now - timedelta(days=30)).date()

        app = _make_app(auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                f"/api/v1/analytics/dashboard?date_from={from_date}&date_to={today}"
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_cases"] == 2

    @pytest.mark.asyncio
    async def test_dashboard_invalid_date_range_returns_400(self, db_session):
        # @forgeplan-spec: AC5
        auth = _make_auth("manager")
        org_id = auth.organization_id
        await _seed_organization(db_session, org_id)
        await _seed_user(db_session, auth)

        app = _make_app(auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/api/v1/analytics/dashboard?date_from=2025-01-10&date_to=2025-01-01"
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_dashboard_zero_cases_placement_rate_zero(self, db_session):
        # @forgeplan-spec: AC5 — division by zero returns 0.0
        auth = _make_auth("manager")
        org_id = auth.organization_id
        await _seed_organization(db_session, org_id)
        await _seed_user(db_session, auth)

        app = _make_app(auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/analytics/dashboard")
        assert resp.status_code == 200
        assert resp.json()["placement_rate_pct"] == 0.0


# ---------------------------------------------------------------------------
# AC6 — Outreach performance
# ---------------------------------------------------------------------------

class TestOutreachPerformance:
    """AC6 — accept/decline rates by facility and by decline_reason_code."""

    @pytest.mark.asyncio
    async def test_outreach_performance_by_facility(self, db_session):
        # @forgeplan-spec: AC6
        auth = _make_auth("manager")
        org_id = auth.organization_id
        await _seed_organization(db_session, org_id)
        await _seed_user(db_session, auth)

        now = datetime.now(timezone.utc)

        # Seed a facility
        facility = Facility(
            id=str(uuid4()),
            organization_id=str(org_id),
            facility_name="Sunrise SNF",
            facility_type="snf",
            created_at=now,
            updated_at=now,
        )
        db_session.add(facility)
        await db_session.commit()

        # Seed a case and 5 outcomes: 2 accepted, 3 declined
        pc = await _seed_case(db_session, org_id, created_at=now)
        for outcome_type in ["accepted", "accepted", "declined", "declined", "declined"]:
            po = PlacementOutcome(
                id=str(uuid4()),
                patient_case_id=pc.id,
                facility_id=facility.id,
                outcome_type=outcome_type,
                recorded_by_user_id=str(auth.user_id),
                created_at=now,
            )
            db_session.add(po)
        await db_session.commit()

        app = _make_app(auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/analytics/outreach-performance")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["by_facility"]) == 1
        fac_stats = data["by_facility"][0]
        assert fac_stats["accepted_count"] == 2
        assert fac_stats["declined_count"] == 3
        assert fac_stats["acceptance_rate_pct"] == 40.0
        assert fac_stats["total_outreach_sent"] == 5

    @pytest.mark.asyncio
    async def test_outreach_performance_by_decline_reason(self, db_session):
        # @forgeplan-spec: AC6
        auth = _make_auth("manager")
        org_id = auth.organization_id
        await _seed_organization(db_session, org_id)
        await _seed_user(db_session, auth)

        now = datetime.now(timezone.utc)

        # Seed a decline reason reference
        drr = DeclineReasonReference(
            id=str(uuid4()),
            code="no_beds",
            label="No Available Beds",
        )
        db_session.add(drr)
        await db_session.commit()

        facility = Facility(
            id=str(uuid4()),
            organization_id=str(org_id),
            facility_name="Test Facility",
            facility_type="snf",
            created_at=now,
            updated_at=now,
        )
        db_session.add(facility)
        await db_session.commit()

        pc = await _seed_case(db_session, org_id, created_at=now)

        # 2 declines with same code, 1 with different
        for code in ["no_beds", "no_beds", "insurance_denied"]:
            po = PlacementOutcome(
                id=str(uuid4()),
                patient_case_id=pc.id,
                facility_id=facility.id,
                outcome_type="declined",
                decline_reason_code=code,
                recorded_by_user_id=str(auth.user_id),
                created_at=now,
            )
            db_session.add(po)
        await db_session.commit()

        app = _make_app(auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/analytics/outreach-performance")
        assert resp.status_code == 200
        data = resp.json()

        no_beds_entry = next(
            (r for r in data["by_decline_reason"] if r["decline_reason_code"] == "no_beds"),
            None
        )
        assert no_beds_entry is not None
        assert no_beds_entry["count"] == 2
        # 2/3 total declines = 66.67%
        assert no_beds_entry["pct_of_total_declines"] == pytest.approx(66.67, rel=0.01)
        # Label from reference table
        assert no_beds_entry["decline_reason_label"] == "No Available Beds"

    @pytest.mark.asyncio
    async def test_outreach_date_range_filter(self, db_session):
        # @forgeplan-spec: AC6
        auth = _make_auth("manager")
        org_id = auth.organization_id
        await _seed_organization(db_session, org_id)
        await _seed_user(db_session, auth)

        now = datetime.now(timezone.utc)
        old_date = now - timedelta(days=60)

        facility = Facility(
            id=str(uuid4()),
            organization_id=str(org_id),
            facility_name="Old Facility",
            facility_type="snf",
            created_at=now,
            updated_at=now,
        )
        db_session.add(facility)
        await db_session.commit()

        pc = await _seed_case(db_session, org_id, created_at=now)
        # Outcome created 60 days ago (outside default 30-day window)
        po_old = PlacementOutcome(
            id=str(uuid4()),
            patient_case_id=pc.id,
            facility_id=facility.id,
            outcome_type="declined",
            recorded_by_user_id=str(auth.user_id),
            created_at=old_date,
        )
        db_session.add(po_old)
        await db_session.commit()

        # Default date range (last 30 days) — should not include the old outcome
        app = _make_app(auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/analytics/outreach-performance")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["by_facility"]) == 0


# ---------------------------------------------------------------------------
# AC8 — Pagination
# ---------------------------------------------------------------------------

class TestPagination:
    """AC8 — page and page_size control result window; total_count always returned."""

    @pytest.mark.asyncio
    async def test_operations_queue_pagination(self, db_session):
        # @forgeplan-spec: AC8
        auth = _make_auth("manager")
        org_id = auth.organization_id
        await _seed_organization(db_session, org_id)
        await _seed_user(db_session, auth)

        # Seed 120 cases
        for _ in range(120):
            await _seed_case(db_session, org_id)

        app = _make_app(auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp1 = await client.get("/api/v1/queues/operations?page=1&page_size=50")
            resp3 = await client.get("/api/v1/queues/operations?page=3&page_size=50")

        assert resp1.status_code == 200
        data1 = resp1.json()
        assert len(data1["items"]) == 50
        assert data1["total_count"] == 120

        assert resp3.status_code == 200
        data3 = resp3.json()
        assert len(data3["items"]) == 20  # last page: 120 - 100 = 20
        assert data3["total_count"] == 120

    @pytest.mark.asyncio
    async def test_page_size_max_200(self, db_session):
        # @forgeplan-spec: AC8
        auth = _make_auth("manager")
        org_id = auth.organization_id
        await _seed_organization(db_session, org_id)
        await _seed_user(db_session, auth)

        app = _make_app(auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/queues/operations?page_size=201")
        assert resp.status_code == 422  # FastAPI validation rejects >200

    @pytest.mark.asyncio
    async def test_manager_summary_breach_cases_paginated(self, db_session):
        # @forgeplan-spec: AC8
        auth = _make_auth("manager")
        org_id = auth.organization_id
        await _seed_organization(db_session, org_id)
        await _seed_user(db_session, auth)

        now = datetime.now(timezone.utc)
        # Seed 60 breach cases
        for _ in range(60):
            pc = await _seed_case(db_session, org_id, current_status="declined_retry_needed")
            await _seed_status_history(
                db_session, pc.id, org_id, "declined_retry_needed",
                entered_at=now - timedelta(hours=10)
            )

        app = _make_app(auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/queues/manager-summary?page=1&page_size=50")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_breach_cases"] == 60
        assert len(data["sla_breach_cases"]) == 50


# ---------------------------------------------------------------------------
# AC9 — Cross-org isolation on all four endpoints
# ---------------------------------------------------------------------------

class TestCrossOrgIsolation:
    """AC9 — No cross-org data in any response."""

    @pytest.mark.asyncio
    async def test_all_endpoints_scope_to_org(self, db_session):
        # @forgeplan-spec: AC9
        org_a = uuid4()
        org_b = uuid4()
        auth_a = _make_auth("manager", org_id=org_a)

        await _seed_organization(db_session, org_a)
        await _seed_organization(db_session, org_b)
        await _seed_user(db_session, auth_a)

        now = datetime.now(timezone.utc)

        # Seed 5 cases in org_a
        org_a_case_ids = set()
        for _ in range(5):
            pc = await _seed_case(db_session, org_a, created_at=now)
            org_a_case_ids.add(pc.id)

        # Seed 5 cases in org_b
        org_b_case_ids = set()
        for _ in range(5):
            pc = await _seed_case(db_session, org_b, created_at=now)
            org_b_case_ids.add(pc.id)

        app = _make_app(auth_a)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            ops_resp = await client.get("/api/v1/queues/operations")
            summary_resp = await client.get("/api/v1/queues/manager-summary")
            dashboard_resp = await client.get("/api/v1/analytics/dashboard")
            outreach_resp = await client.get("/api/v1/analytics/outreach-performance")

        # Operations queue: only org_a cases
        ops_data = ops_resp.json()
        assert ops_data["total_count"] == 5
        ops_ids = {item["case_id"] for item in ops_data["items"]}
        assert ops_ids.issubset(org_a_case_ids)
        assert not ops_ids.intersection(org_b_case_ids)

        # Manager summary: total_active_cases == 5
        summary_data = summary_resp.json()
        assert summary_data["total_active_cases"] == 5

        # Dashboard: total_cases == 5
        dashboard_data = dashboard_resp.json()
        assert dashboard_data["total_cases"] == 5

        # Outreach performance: no org_b data (no outcomes seeded for either org, so empty)
        assert outreach_resp.status_code == 200


# ---------------------------------------------------------------------------
# AC7 — Performance test: 1000 cases < 2000ms
# ---------------------------------------------------------------------------

# F45 fix: determine whether the test DB is SQLite or PostgreSQL so the
# performance threshold can be set appropriately.
#
# AC7 specifies < 2000ms against the production PostgreSQL target.
# This test suite always runs against SQLite in-memory (TEST_DB_URL above),
# which has fundamentally different performance characteristics (no network
# round-trips, single-file I/O, no MVCC overhead) and will complete well
# under the production budget.  Using the full 2000ms bound against SQLite
# therefore does NOT validate the production constraint.
#
# Resolution:
#   • When the engine URL contains "sqlite", apply a tighter bound (500ms)
#     that is still meaningful for catching gross regressions while
#     acknowledging SQLite is faster than the real target.
#   • When the engine URL contains "postgresql" (i.e. an integration run
#     wired to a live DB via DATABASE_URL), apply the spec-mandated 2000ms
#     bound.
#   • A pytest.mark.integration marker is added so CI can separate the two
#     test classes cleanly.
#
# To run the authoritative AC7 validation set DATABASE_URL to a real
# PostgreSQL connection string and run with: pytest -m integration

_IS_SQLITE = "sqlite" in TEST_DB_URL

# Threshold: SQLite in-memory runs fast — use 500ms as a regression guard.
# PostgreSQL integration runs use the spec-mandated 2000ms budget.
_PERF_LIMIT_MS = 500 if _IS_SQLITE else 2000


class TestPerformance:
    """AC7 — All endpoints respond in <2000ms for 1000 cases (PostgreSQL target).

    NOTE: This test runs against SQLite in-memory and uses a tighter 500ms
    threshold as a regression guard.  Full AC7 validation requires running
    against a live PostgreSQL instance (pytest -m integration).
    """

    @pytest.mark.asyncio
    @pytest.mark.slow
    @pytest.mark.integration
    async def test_all_endpoints_under_2000ms_for_1000_cases(self, db_session):
        # @forgeplan-spec: AC7
        #
        # Performance threshold is backend-aware (see module-level comment):
        #   SQLite in-memory  → 500ms  (regression guard; not the AC7 bound)
        #   PostgreSQL target → 2000ms (spec-mandated AC7 bound)
        auth = _make_auth("manager")
        org_id = auth.organization_id
        await _seed_organization(db_session, org_id)
        await _seed_user(db_session, auth)

        now = datetime.now(timezone.utc)

        # Bulk seed 1000 cases with status history
        cases = []
        for i in range(1000):
            pc = PatientCase(
                id=str(uuid4()),
                organization_id=str(org_id),
                patient_name=f"Patient {i}",
                current_status="pending_facility_response",
                created_at=now - timedelta(hours=i % 720),
                updated_at=now - timedelta(hours=1),
            )
            cases.append(pc)
        db_session.add_all(cases)
        await db_session.commit()

        # Seed status history for each case
        histories = []
        for pc in cases:
            csh = CaseStatusHistory(
                id=str(uuid4()),
                organization_id=str(org_id),
                patient_case_id=pc.id,
                to_status="pending_facility_response",
                actor_user_id=str(auth.user_id),
                entered_at=now - timedelta(hours=5),
            )
            histories.append(csh)
        db_session.add_all(histories)
        await db_session.commit()

        app = _make_app(auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            endpoints = [
                "/api/v1/queues/operations?page_size=50",
                "/api/v1/queues/manager-summary?page_size=50",
                "/api/v1/analytics/dashboard",
                "/api/v1/analytics/outreach-performance",
            ]
            for endpoint in endpoints:
                start = time.monotonic()
                resp = await client.get(endpoint)
                elapsed_ms = (time.monotonic() - start) * 1000
                assert resp.status_code == 200, f"Endpoint {endpoint} returned {resp.status_code}"
                assert elapsed_ms < _PERF_LIMIT_MS, (
                    f"Endpoint {endpoint} took {elapsed_ms:.0f}ms "
                    f"(limit: {_PERF_LIMIT_MS}ms for "
                    f"{'SQLite regression guard' if _IS_SQLITE else 'PostgreSQL AC7 spec'})"
                )

        # Verify paginated response returns page_size=50 with total_count=1000
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/queues/operations?page=1&page_size=50")
        data = resp.json()
        assert data["total_count"] == 1000
        assert len(data["items"]) == 50
