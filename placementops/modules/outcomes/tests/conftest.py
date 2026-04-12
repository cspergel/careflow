# @forgeplan-node: outcomes-module
# @forgeplan-spec: AC1, AC2, AC3, AC4, AC5, AC6, AC7, AC8, AC9, AC10, AC11, AC12, AC13, AC14, AC15, AC16
"""
Shared pytest fixtures for outcomes-module tests.

Uses SQLite in-memory database (aiosqlite) for fast, isolated tests.
Follows the pattern established by outreach-module and matching-module conftest files.

Seeding helpers included:
  - seed_org, seed_user, seed_case, seed_facility
  - seed_outreach_action (with facility_id for outcome validation tests)
  - seed_decline_reason (for AC16 reference table tests)
  - seed_outcome (for history/timeline tests)
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator
from uuid import UUID

# Set test env vars BEFORE any module imports that read them
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret-key-minimum-32-chars-long")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import jwt
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from placementops.core.auth import AuthContext
from placementops.core.database import Base, get_db

# ---------------------------------------------------------------------------
# SQLite JSONB compatibility patch
# ---------------------------------------------------------------------------
if not hasattr(SQLiteTypeCompiler, "visit_JSONB"):
    SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON  # type: ignore[attr-defined]

from placementops.core.models import (
    AuditEvent,
    CaseStatusHistory,
    DeclineReasonReference,
    Facility,
    HospitalReference,
    Organization,
    OutreachAction,
    PatientCase,
    PlacementOutcome,
    User,
)

# ── Constants ──────────────────────────────────────────────────────────────────

TEST_SECRET = "test-secret-key-minimum-32-chars-long"
TEST_ORG_ID: UUID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TEST_ORG2_ID: UUID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
TEST_FACILITY_ID: UUID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")

# Seed decline reason codes (AC16)
DECLINE_REASON_CODES = [
    ("bed_no_longer_available", "Bed No Longer Available"),
    ("insurance_issue_post_acceptance", "Insurance Issue Post Acceptance"),
    ("clinical_criteria_not_met", "Clinical Criteria Not Met"),
    ("no_response", "No Response"),
]


# ── Engine / session fixtures ──────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Fresh in-memory SQLite engine per test."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield an AsyncSession for the test-scoped engine."""
    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


# ── FastAPI test client ────────────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="function")
async def client(test_engine) -> AsyncGenerator[AsyncClient, None]:
    """Return an HTTPX AsyncClient backed by the in-memory SQLite engine."""
    from placementops.modules.outcomes.router import router as outcomes_router
    from placementops.modules.auth.router import router as auth_router

    app = FastAPI()
    app.include_router(outcomes_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")

    session_factory = async_sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ── JWT / auth helpers ─────────────────────────────────────────────────────────


def make_jwt(user_id: str, org_id: str, role_key: str) -> str:
    """Mint a test JWT with app_metadata containing organization_id and role_key."""
    payload = {
        "sub": user_id,
        "aud": "authenticated",
        "exp": 9999999999,
        "app_metadata": {"organization_id": org_id, "role_key": role_key},
    }
    return jwt.encode(payload, TEST_SECRET, algorithm="HS256")


def auth_headers(user_id: str, org_id: str, role_key: str) -> dict:
    """Return Authorization header dict for an HTTP client."""
    return {"Authorization": f"Bearer {make_jwt(user_id, org_id, role_key)}"}


def make_auth_ctx(user_id: UUID, org_id: UUID, role_key: str) -> AuthContext:
    """Build an AuthContext directly for service-layer tests."""
    return AuthContext(
        user_id=user_id,
        organization_id=org_id,
        role_key=role_key,
    )


# ── Seed helpers ───────────────────────────────────────────────────────────────


def make_id() -> str:
    """Return a new random UUID string."""
    return str(uuid.uuid4())


async def seed_org(db: AsyncSession, org_id: UUID = TEST_ORG_ID) -> Organization:
    org = Organization(id=str(org_id), name="Test Org")
    db.add(org)
    await db.commit()
    return org


async def seed_user(
    db: AsyncSession,
    role_key: str,
    user_id: UUID | None = None,
    org_id: UUID = TEST_ORG_ID,
) -> User:
    uid = user_id or UUID(make_id())
    user = User(
        id=str(uid),
        organization_id=str(org_id),
        email=f"{role_key}_{str(uid)[:8]}@test.com",
        full_name=f"{role_key} User",
        role_key=role_key,
        status="active",
    )
    db.add(user)
    await db.commit()
    return user


async def seed_case(
    db: AsyncSession,
    org_id: UUID = TEST_ORG_ID,
    current_status: str = "pending_facility_response",
    case_id: UUID | None = None,
) -> PatientCase:
    cid = case_id or UUID(make_id())
    case = PatientCase(
        id=str(cid),
        organization_id=str(org_id),
        patient_name="Test Patient",
        current_status=current_status,
    )
    db.add(case)
    await db.commit()
    return case


async def seed_facility(
    db: AsyncSession,
    org_id: UUID = TEST_ORG_ID,
    facility_id: UUID = TEST_FACILITY_ID,
    facility_name: str = "Test Facility",
) -> Facility:
    facility = Facility(
        id=str(facility_id),
        organization_id=str(org_id),
        facility_name=facility_name,
        facility_type="snf",
    )
    db.add(facility)
    await db.commit()
    return facility


async def seed_outreach_action(
    db: AsyncSession,
    case_id: str,
    facility_id: str | None = None,
    approval_status: str = "sent",
    channel: str = "email",
    action_type: str = "facility_outreach",
    draft_body: str = "Please admit this patient.",
    action_id: UUID | None = None,
) -> OutreachAction:
    aid = action_id or UUID(make_id())
    action = OutreachAction(
        id=str(aid),
        patient_case_id=case_id,
        facility_id=facility_id,
        channel=channel,
        action_type=action_type,
        approval_status=approval_status,
        draft_body=draft_body,
    )
    db.add(action)
    await db.commit()
    return action


async def seed_decline_reasons(db: AsyncSession) -> None:
    """Seed the decline_reason_reference table with the minimum required codes (AC16)."""
    for code, label in DECLINE_REASON_CODES:
        ref = DeclineReasonReference(
            id=make_id(),
            code=code,
            label=label,
            display_order=DECLINE_REASON_CODES.index((code, label)),
        )
        db.add(ref)
    await db.commit()


async def seed_outcome(
    db: AsyncSession,
    case_id: str,
    recorded_by_user_id: str,
    outcome_type: str = "accepted",
    facility_id: str | None = None,
    decline_reason_code: str | None = None,
    decline_reason_text: str | None = None,
    outcome_id: UUID | None = None,
) -> PlacementOutcome:
    oid = outcome_id or UUID(make_id())
    outcome = PlacementOutcome(
        id=str(oid),
        patient_case_id=case_id,
        facility_id=facility_id,
        outcome_type=outcome_type,
        decline_reason_code=decline_reason_code,
        decline_reason_text=decline_reason_text,
        recorded_by_user_id=recorded_by_user_id,
    )
    db.add(outcome)
    await db.commit()
    return outcome


# ── Auth context fixtures ──────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def seed_org_fixture(db_session: AsyncSession) -> Organization:
    return await seed_org(db_session, TEST_ORG_ID)


@pytest_asyncio.fixture
async def coordinator_user(db_session: AsyncSession, seed_org_fixture) -> User:
    return await seed_user(db_session, "placement_coordinator")


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession, seed_org_fixture) -> User:
    return await seed_user(db_session, "admin")


@pytest_asyncio.fixture
async def manager_user(db_session: AsyncSession, seed_org_fixture) -> User:
    return await seed_user(db_session, "manager")


@pytest_asyncio.fixture
async def intake_user(db_session: AsyncSession, seed_org_fixture) -> User:
    return await seed_user(db_session, "intake_staff")


@pytest_asyncio.fixture
async def clinical_user(db_session: AsyncSession, seed_org_fixture) -> User:
    return await seed_user(db_session, "clinical_reviewer")


@pytest_asyncio.fixture
async def read_only_user(db_session: AsyncSession, seed_org_fixture) -> User:
    return await seed_user(db_session, "read_only")


@pytest.fixture
def auth_ctx_coordinator(coordinator_user: User) -> AuthContext:
    return make_auth_ctx(
        user_id=UUID(coordinator_user.id),
        org_id=TEST_ORG_ID,
        role_key="placement_coordinator",
    )


@pytest.fixture
def auth_ctx_admin(admin_user: User) -> AuthContext:
    return make_auth_ctx(
        user_id=UUID(admin_user.id),
        org_id=TEST_ORG_ID,
        role_key="admin",
    )


@pytest.fixture
def auth_ctx_manager(manager_user: User) -> AuthContext:
    return make_auth_ctx(
        user_id=UUID(manager_user.id),
        org_id=TEST_ORG_ID,
        role_key="manager",
    )


@pytest.fixture
def auth_ctx_intake(intake_user: User) -> AuthContext:
    return make_auth_ctx(
        user_id=UUID(intake_user.id),
        org_id=TEST_ORG_ID,
        role_key="intake_staff",
    )
