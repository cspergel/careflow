# @forgeplan-node: outreach-module
# @forgeplan-spec: AC1
# @forgeplan-spec: AC2
# @forgeplan-spec: AC3
# @forgeplan-spec: AC4
# @forgeplan-spec: AC5
# @forgeplan-spec: AC6
# @forgeplan-spec: AC7
# @forgeplan-spec: AC8
# @forgeplan-spec: AC9
# @forgeplan-spec: AC10
# @forgeplan-spec: AC11
# @forgeplan-spec: AC12
"""
Shared pytest fixtures for outreach-module tests.

Uses SQLite in-memory database (aiosqlite) for fast, isolated tests.
Follows the same pattern as matching-module conftest.py.
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
    Facility,
    HospitalReference,
    Organization,
    OutreachAction,
    OutreachTemplate,
    PatientCase,
    User,
)

# ── Constants ──────────────────────────────────────────────────────────────────

TEST_SECRET = "test-secret-key-minimum-32-chars-long"
TEST_ORG_ID: UUID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TEST_ORG2_ID: UUID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
TEST_HOSPITAL_ID: UUID = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


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
    from placementops.modules.outreach.router import router as outreach_router
    from placementops.modules.auth.router import router as auth_router

    app = FastAPI()
    app.include_router(outreach_router, prefix="/api/v1")
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
    current_status: str = "facility_options_generated",
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


async def seed_template(
    db: AsyncSession,
    org_id: UUID = TEST_ORG_ID,
    template_name: str = "Admission Request",
    body_template: str = "Dear {{ facility_name }}, please admit {{ patient_name }}.",
    subject_template: str | None = "Admission for {{ patient_name }}",
    template_type: str = "email",
    is_active: bool = True,
    created_by_user_id: str | None = None,
    template_id: UUID | None = None,
) -> OutreachTemplate:
    tid = template_id or UUID(make_id())
    creator = created_by_user_id or make_id()
    template = OutreachTemplate(
        id=str(tid),
        organization_id=str(org_id),
        template_name=template_name,
        template_type=template_type,
        subject_template=subject_template,
        body_template=body_template,
        allowed_variables=["patient_name", "facility_name", "payer_name"],
        is_active=is_active,
        created_by_user_id=creator,
    )
    db.add(template)
    await db.commit()
    return template


async def seed_outreach_action(
    db: AsyncSession,
    case_id: str,
    org_id: UUID = TEST_ORG_ID,
    channel: str = "email",
    action_type: str = "facility_outreach",
    approval_status: str = "draft",
    draft_body: str = "Please admit this patient.",
    draft_subject: str | None = "Admission request",
    approved_by_user_id: str | None = None,
    approved_at: datetime | None = None,
    sent_by_user_id: str | None = None,
    sent_at: datetime | None = None,
    action_id: UUID | None = None,
) -> OutreachAction:
    aid = action_id or UUID(make_id())
    action = OutreachAction(
        id=str(aid),
        patient_case_id=case_id,
        channel=channel,
        action_type=action_type,
        approval_status=approval_status,
        draft_body=draft_body,
        draft_subject=draft_subject,
        approved_by_user_id=approved_by_user_id,
        approved_at=approved_at,
        sent_by_user_id=sent_by_user_id,
        sent_at=sent_at,
    )
    db.add(action)
    await db.commit()
    return action


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
async def intake_user(db_session: AsyncSession, seed_org_fixture) -> User:
    return await seed_user(db_session, "intake_staff")


@pytest_asyncio.fixture
async def clinical_user(db_session: AsyncSession, seed_org_fixture) -> User:
    return await seed_user(db_session, "clinical_reviewer")


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
def auth_ctx_intake(intake_user: User) -> AuthContext:
    return make_auth_ctx(
        user_id=UUID(intake_user.id),
        org_id=TEST_ORG_ID,
        role_key="intake_staff",
    )


@pytest.fixture
def auth_ctx_clinical(clinical_user: User) -> AuthContext:
    return make_auth_ctx(
        user_id=UUID(clinical_user.id),
        org_id=TEST_ORG_ID,
        role_key="clinical_reviewer",
    )


# ── Composite seeded fixtures ──────────────────────────────────────────────────


@pytest_asyncio.fixture
async def seeded_case(
    db_session: AsyncSession,
    seed_org_fixture: Organization,
) -> PatientCase:
    """Case at facility_options_generated — ready for outreach."""
    return await seed_case(
        db_session,
        org_id=TEST_ORG_ID,
        current_status="facility_options_generated",
    )


@pytest_asyncio.fixture
async def seeded_template(
    db_session: AsyncSession,
    seed_org_fixture: Organization,
    coordinator_user: User,
) -> OutreachTemplate:
    """Active email template with patient_name and facility_name variables."""
    return await seed_template(
        db_session,
        org_id=TEST_ORG_ID,
        created_by_user_id=coordinator_user.id,
    )
