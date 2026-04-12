# @forgeplan-node: auth-module
"""
pytest fixtures for auth-module tests.

Uses SQLite in-memory (aiosqlite) for database — no live Postgres required.
Supabase auth calls are mocked per-test using pytest-mock or unittest.mock.
JWT minting uses PyJWT with the test secret.

All stable test IDs and helper functions are in helpers.py (importable).
This file contains only pytest fixtures (not directly importable).
"""

import os
import pytest
import pytest_asyncio
from uuid import UUID, uuid4

from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

# Set test env vars BEFORE importing application modules
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DATABASE_DIRECT_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret-key-minimum-32-chars-long")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")

from placementops.core.database import Base, get_db
from placementops.core.models import Organization, User

# Import stable test helpers — these are directly importable module-level values
from placementops.modules.auth.tests.helpers import (
    TEST_ORG_ID,
    TEST_USER_ID,
    TEST_SECRET,
    make_jwt,
    make_rbac_app,
)
from placementops.modules.auth.router import router
from placementops.modules.auth.rate_limiter import reset_rate_limiter


# ── Rate limiter reset ────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_rate_limiter():
    """Clear rate limiter state before each test to prevent interference."""
    reset_rate_limiter()
    yield
    reset_rate_limiter()


# ── In-memory SQLite engine ───────────────────────────────────────────────────

@pytest_asyncio.fixture
async def async_engine():
    """Create an in-memory SQLite engine with all ORM tables created."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_engine):
    """Yield an AsyncSession bound to the test in-memory database."""
    session_factory = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


# ── FastAPI test app (auth endpoints only) ────────────────────────────────────

@pytest.fixture
def auth_app(db_session):
    """Build a minimal FastAPI test application with the auth router mounted."""
    app = FastAPI()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.include_router(router, prefix="/api/v1")
    return app


@pytest_asyncio.fixture
async def async_client(auth_app):
    """Async HTTP client for the auth test app."""
    async with AsyncClient(
        transport=ASGITransport(app=auth_app), base_url="http://test"
    ) as client:
        yield client


# ── RBAC test app ─────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def rbac_client(db_session):
    """Async HTTP client backed by the RBAC stub app (AC6-AC11 tests)."""
    app = make_rbac_app(db_session)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


# ── DB seed helpers ───────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def org(db_session) -> Organization:
    """Create and commit a test Organization."""
    org_obj = Organization(id=str(TEST_ORG_ID), name="Test Org")
    db_session.add(org_obj)
    await db_session.commit()
    return org_obj


async def _make_user(
    db_session,
    role_key: str,
    user_id: UUID | None = None,
    org_id: UUID | None = None,
) -> User:
    """Helper: create and commit a User with the given role."""
    uid = user_id or uuid4()
    oid = org_id or TEST_ORG_ID
    user = User(
        id=str(uid),
        organization_id=str(oid),
        email=f"{role_key}_{str(uid)[:8]}@example.com",
        full_name=f"{role_key.replace('_', ' ').title()} User",
        role_key=role_key,
        status="active",
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest_asyncio.fixture
async def admin_user(db_session, org) -> User:
    return await _make_user(db_session, "admin")


@pytest_asyncio.fixture
async def intake_staff_user(db_session, org) -> User:
    return await _make_user(db_session, "intake_staff")


@pytest_asyncio.fixture
async def clinical_reviewer_user(db_session, org) -> User:
    return await _make_user(db_session, "clinical_reviewer")


@pytest_asyncio.fixture
async def placement_coordinator_user(db_session, org) -> User:
    return await _make_user(db_session, "placement_coordinator")


@pytest_asyncio.fixture
async def manager_user(db_session, org) -> User:
    return await _make_user(db_session, "manager")


@pytest_asyncio.fixture
async def read_only_user(db_session, org) -> User:
    return await _make_user(db_session, "read_only")


@pytest_asyncio.fixture
async def base_user(db_session, org) -> User:
    """A generic test user (intake_staff) with known TEST_USER_ID."""
    return await _make_user(db_session, "intake_staff", user_id=TEST_USER_ID)
