# @forgeplan-node: intake-module
"""
Shared test fixtures for intake module tests.

Uses SQLite in-memory database for fast, isolated tests.
All tables (core + local intake models) are created via Base.metadata.create_all().
"""

from __future__ import annotations

import os

# Set test environment variables before any module imports that read them
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret-key-minimum-32-chars-long")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from placementops.core.database import Base, AsyncSessionLocal
from placementops.core.models import (
    Organization,
    PatientCase,
    ImportJob,
    CaseStatusHistory,
    User,
    AuditEvent,
    HospitalReference,
)
from placementops.modules.intake.models import IntakeFieldIssue, CaseAssignment

# Import local models so they register with Base.metadata
_INTAKE_MODELS = [IntakeFieldIssue, CaseAssignment]


# ---------------------------------------------------------------------------
# Async SQLite engine for tests
# ---------------------------------------------------------------------------

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Create a fresh in-memory SQLite engine for each test."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
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
async def db_session(test_engine):
    """Yield an AsyncSession for the test-scoped engine."""
    test_session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with test_session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# FastAPI test client
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture(scope="function")
async def client(test_engine, db_session):
    """
    Return an HTTPX AsyncClient pointed at the FastAPI app.

    Overrides get_db and AsyncSessionLocal to use the test engine.
    """
    from fastapi import FastAPI
    from placementops.core.database import get_db
    from placementops.modules.intake.router import router

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")

    test_session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async def override_get_db():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Patch AsyncSessionLocal for background tasks
    import placementops.modules.intake.service as svc_module
    original = svc_module.AsyncSessionLocal

    svc_module.AsyncSessionLocal = test_session_factory

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    svc_module.AsyncSessionLocal = original


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

import uuid
from datetime import date


def make_org_id() -> str:
    return str(uuid.uuid4())


def make_user_id() -> str:
    return str(uuid.uuid4())


def make_hospital_id() -> str:
    return str(uuid.uuid4())


@pytest_asyncio.fixture(scope="function")
async def seed_org(db_session: AsyncSession) -> str:
    """Insert a minimal Organization row and return its ID."""
    org_id = make_org_id()
    org = Organization(
        id=org_id,
        name="Test Org",
    )
    db_session.add(org)
    await db_session.commit()
    return org_id


@pytest_asyncio.fixture(scope="function")
async def seed_hospital(db_session: AsyncSession, seed_org: str) -> str:
    """Insert a HospitalReference row and return its ID."""
    hospital_id = make_hospital_id()
    hospital = HospitalReference(
        id=hospital_id,
        organization_id=seed_org,
        hospital_name="Test Hospital",
    )
    db_session.add(hospital)
    await db_session.commit()
    return hospital_id


@pytest_asyncio.fixture(scope="function")
async def seed_intake_user(db_session: AsyncSession, seed_org: str) -> dict:
    """Insert an intake_staff User and return info dict."""
    user_id = make_user_id()
    user = User(
        id=user_id,
        organization_id=seed_org,
        email="intake@test.com",
        full_name="Intake Staff",
        role_key="intake_staff",
        status="active",
    )
    db_session.add(user)
    await db_session.commit()
    return {"user_id": user_id, "role_key": "intake_staff", "org_id": seed_org}


@pytest_asyncio.fixture(scope="function")
async def seed_admin_user(db_session: AsyncSession, seed_org: str) -> dict:
    """Insert an admin User and return info dict."""
    user_id = make_user_id()
    user = User(
        id=user_id,
        organization_id=seed_org,
        email="admin@test.com",
        full_name="Admin User",
        role_key="admin",
        status="active",
    )
    db_session.add(user)
    await db_session.commit()
    return {"user_id": user_id, "role_key": "admin", "org_id": seed_org}


@pytest_asyncio.fixture(scope="function")
async def seed_coordinator_user(db_session: AsyncSession, seed_org: str) -> dict:
    """Insert a placement_coordinator User and return info dict."""
    user_id = make_user_id()
    user = User(
        id=user_id,
        organization_id=seed_org,
        email="coordinator@test.com",
        full_name="Placement Coordinator",
        role_key="placement_coordinator",
        status="active",
    )
    db_session.add(user)
    await db_session.commit()
    return {"user_id": user_id, "role_key": "placement_coordinator", "org_id": seed_org}


@pytest_asyncio.fixture(scope="function")
async def seed_clinical_reviewer(db_session: AsyncSession, seed_org: str) -> dict:
    """Insert a clinical_reviewer User and return info dict."""
    user_id = make_user_id()
    user = User(
        id=user_id,
        organization_id=seed_org,
        email="clinical@test.com",
        full_name="Clinical Reviewer",
        role_key="clinical_reviewer",
        status="active",
    )
    db_session.add(user)
    await db_session.commit()
    return {"user_id": user_id, "role_key": "clinical_reviewer", "org_id": seed_org}


def make_jwt_token(user_id: str, org_id: str, role_key: str) -> str:
    """
    Create a fake HS256 JWT token for test authentication.
    Uses SUPABASE_JWT_SECRET set in conftest env setup.
    """
    import jwt

    secret = os.environ.get("SUPABASE_JWT_SECRET", "test-secret-key-minimum-32-chars-long")
    payload = {
        "sub": user_id,
        "aud": "authenticated",
        "exp": 9999999999,  # Far future
        "app_metadata": {
            "organization_id": org_id,
            "role_key": role_key,
        },
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def auth_headers(user_id: str, org_id: str, role_key: str) -> dict:
    """Return Authorization header dict for test requests."""
    token = make_jwt_token(user_id, org_id, role_key)
    return {"Authorization": f"Bearer {token}"}
