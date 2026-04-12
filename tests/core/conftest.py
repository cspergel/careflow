# @forgeplan-node: core-infrastructure
"""
pytest fixtures for core-infrastructure tests.

Uses SQLite in-memory (via aiosqlite) for unit tests that don't need Postgres-specific
features. Tests requiring Postgres triggers (AC7 AuditEvent immutability) use a separate
fixture that marks the test as requiring a live Postgres connection.

JWT fixtures use PyJWT to mint tokens signed with a test secret.
"""

import os
import pytest
import pytest_asyncio


def pytest_collection_modifyitems(config, items):
    """Skip tests marked postgres_required when DATABASE_URL is not PostgreSQL."""
    database_url = os.environ.get("DATABASE_URL", "")
    if "postgresql" not in database_url and "postgres" not in database_url:
        skip_mark = pytest.mark.skip(
            reason="postgres_required: set DATABASE_URL to a PostgreSQL connection to run"
        )
        for item in items:
            if "postgres_required" in item.keywords:
                item.add_marker(skip_mark)
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool

# Set test environment variables BEFORE importing app modules
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DATABASE_DIRECT_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret-key-minimum-32-chars-long")

from placementops.core.database import Base, get_db
from placementops.core.auth import AuthContext
from placementops.core.models import (
    Organization, User, PatientCase, AuditEvent, CaseStatusHistory
)
from placementops.core.events import _subscribers

TEST_SECRET = "test-secret-key-minimum-32-chars-long"


@pytest.fixture(autouse=True)
def clear_event_subscribers():
    """Auto-use fixture: clear global event bus subscribers before each test to prevent pollution."""
    _subscribers.clear()
    yield
    _subscribers.clear()
TEST_ORG_ID = uuid4()
TEST_ORG_ID_B = uuid4()
TEST_USER_ID = uuid4()


# ── In-memory SQLite engine for unit tests ────────────────────────────────────

@pytest_asyncio.fixture
async def async_engine():
    """Create an in-memory SQLite engine with all tables created."""
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


# ── JWT helpers ───────────────────────────────────────────────────────────────

def make_jwt(
    user_id: UUID | None = None,
    org_id: UUID | None = None,
    role_key: str = "intake_staff",
    secret: str = TEST_SECRET,
    expired: bool = False,
    put_org_in_user_metadata: bool = False,
    algorithm: str = "HS256",
) -> str:
    """Mint a test JWT with configurable claims."""
    uid = user_id or TEST_USER_ID
    oid = org_id or TEST_ORG_ID
    now = datetime.now(timezone.utc)
    exp = now - timedelta(hours=1) if expired else now + timedelta(hours=1)

    if put_org_in_user_metadata:
        # AC12: org_id in user_metadata instead of app_metadata — should be rejected
        payload = {
            "sub": str(uid),
            "aud": "authenticated",
            "iat": now,
            "exp": exp,
            "app_metadata": {},
            "user_metadata": {"organization_id": str(oid)},
            "role_key": role_key,
        }
    else:
        payload = {
            "sub": str(uid),
            "aud": "authenticated",
            "iat": now,
            "exp": exp,
            "app_metadata": {
                "organization_id": str(oid),
                "role_key": role_key,
            },
        }

    return jwt.encode(payload, secret, algorithm=algorithm)


# ── FastAPI test app ──────────────────────────────────────────────────────────

@pytest.fixture
def test_app(db_session):
    """Create a minimal FastAPI test application with auth middleware."""
    from fastapi import Depends
    from placementops.core.auth import get_auth_context

    app = FastAPI()

    # Override the get_db dependency with our test session
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    @app.get("/protected")
    async def protected_route(auth: AuthContext = Depends(get_auth_context)):
        return {
            "user_id": str(auth.user_id),
            "organization_id": str(auth.organization_id),
            "role_key": auth.role_key,
        }

    return app


@pytest_asyncio.fixture
async def async_client(test_app):
    """Async HTTP client for the test FastAPI app."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        yield client


# ── Seed helpers ──────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def org(db_session) -> Organization:
    """Create and return a test organization."""
    org = Organization(id=str(TEST_ORG_ID), name="Test Org A")
    db_session.add(org)
    await db_session.commit()
    return org


@pytest_asyncio.fixture
async def org_b(db_session) -> Organization:
    """Create and return a second test organization."""
    org_b = Organization(id=str(TEST_ORG_ID_B), name="Test Org B")
    db_session.add(org_b)
    await db_session.commit()
    return org_b


@pytest_asyncio.fixture
async def user(db_session, org) -> User:
    """Create a test user in org A."""
    u = User(
        id=str(TEST_USER_ID),
        organization_id=str(TEST_ORG_ID),
        email="test@example.com",
        full_name="Test User",
        role_key="intake_staff",
        status="active",
    )
    db_session.add(u)
    await db_session.commit()
    return u


@pytest_asyncio.fixture
async def patient_case(db_session, org, user) -> PatientCase:
    """Create a test PatientCase in org A with status=new."""
    case = PatientCase(
        id=str(uuid4()),
        organization_id=str(TEST_ORG_ID),
        patient_name="John Doe",
        current_status="new",
    )
    db_session.add(case)
    await db_session.commit()
    return case


@pytest_asyncio.fixture
async def closed_case(db_session, org, user) -> PatientCase:
    """Create a PatientCase with status=closed."""
    case = PatientCase(
        id=str(uuid4()),
        organization_id=str(TEST_ORG_ID),
        patient_name="Jane Doe",
        current_status="closed",
    )
    db_session.add(case)
    await db_session.commit()
    return case
