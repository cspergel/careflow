# @forgeplan-node: admin-surfaces
# @forgeplan-spec: AC1, AC2, AC3, AC4, AC5, AC6, AC7, AC8, AC9, AC10, AC11
"""
Shared test fixtures for admin-surfaces module tests.

Uses SQLite in-memory database for fast, isolated tests.
All tables registered with Base.metadata are created via create_all().
"""

from __future__ import annotations

import os
import uuid

# Set test environment variables before any module imports that read them
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret-key-minimum-32-chars-long")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import jwt
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from placementops.core.database import Base, get_db
from placementops.core.models import (
    AuditEvent,
    DeclineReasonReference,
    HospitalReference,
    ImportJob,
    OutreachTemplate,
    PayerReference,
    User,
)
from placementops.core.models.reference_tables import Organization

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


# ---------------------------------------------------------------------------
# Async SQLite engine for tests
# ---------------------------------------------------------------------------


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
    """Return an HTTPX AsyncClient pointed at the admin module FastAPI app."""
    from placementops.modules.admin.router import router

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

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


def make_jwt_token(user_id: str, org_id: str, role_key: str) -> str:
    """Create a fake HS256 JWT token for test authentication."""
    secret = os.environ.get("SUPABASE_JWT_SECRET", "test-secret-key-minimum-32-chars-long")
    payload = {
        "sub": user_id,
        "aud": "authenticated",
        "exp": 9999999999,
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


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def seed_org(db_session: AsyncSession) -> str:
    """Insert a minimal Organization row and return its ID."""
    org_id = str(uuid.uuid4())
    org = Organization(id=org_id, name="Test Org")
    db_session.add(org)
    await db_session.commit()
    return org_id


@pytest_asyncio.fixture(scope="function")
async def seed_other_org(db_session: AsyncSession) -> str:
    """Insert a second Organization row (for cross-org isolation tests)."""
    org_id = str(uuid.uuid4())
    org = Organization(id=org_id, name="Other Org")
    db_session.add(org)
    await db_session.commit()
    return org_id


@pytest_asyncio.fixture(scope="function")
async def seed_admin_user(db_session: AsyncSession, seed_org: str) -> dict:
    """Insert an admin User and return info dict."""
    user_id = str(uuid.uuid4())
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
async def seed_manager_user(db_session: AsyncSession, seed_org: str) -> dict:
    """Insert a manager User and return info dict."""
    user_id = str(uuid.uuid4())
    user = User(
        id=user_id,
        organization_id=seed_org,
        email="manager@test.com",
        full_name="Manager User",
        role_key="manager",
        status="active",
    )
    db_session.add(user)
    await db_session.commit()
    return {"user_id": user_id, "role_key": "manager", "org_id": seed_org}


@pytest_asyncio.fixture(scope="function")
async def seed_coordinator_user(db_session: AsyncSession, seed_org: str) -> dict:
    """Insert a placement_coordinator User and return info dict."""
    user_id = str(uuid.uuid4())
    user = User(
        id=user_id,
        organization_id=seed_org,
        email="coordinator@test.com",
        full_name="Coordinator User",
        role_key="placement_coordinator",
        status="active",
    )
    db_session.add(user)
    await db_session.commit()
    return {"user_id": user_id, "role_key": "placement_coordinator", "org_id": seed_org}


@pytest_asyncio.fixture(scope="function")
async def seed_intake_user(db_session: AsyncSession, seed_org: str) -> dict:
    """Insert an intake_staff User and return info dict."""
    user_id = str(uuid.uuid4())
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
async def seed_clinical_reviewer(db_session: AsyncSession, seed_org: str) -> dict:
    """Insert a clinical_reviewer User and return info dict."""
    user_id = str(uuid.uuid4())
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


@pytest_asyncio.fixture(scope="function")
async def seed_read_only_user(db_session: AsyncSession, seed_org: str) -> dict:
    """Insert a read_only User and return info dict."""
    user_id = str(uuid.uuid4())
    user = User(
        id=user_id,
        organization_id=seed_org,
        email="readonly@test.com",
        full_name="Read Only User",
        role_key="read_only",
        status="active",
    )
    db_session.add(user)
    await db_session.commit()
    return {"user_id": user_id, "role_key": "read_only", "org_id": seed_org}


@pytest_asyncio.fixture(scope="function")
async def seed_hospital(db_session: AsyncSession, seed_org: str) -> str:
    """Insert a HospitalReference row and return its ID."""
    hospital_id = str(uuid.uuid4())
    hospital = HospitalReference(
        id=hospital_id,
        organization_id=seed_org,
        hospital_name="Test Hospital",
        address="123 Main St",
    )
    db_session.add(hospital)
    await db_session.commit()
    return hospital_id


@pytest_asyncio.fixture(scope="function")
async def seed_template(db_session: AsyncSession, seed_org: str, seed_admin_user: dict) -> dict:
    """Insert an OutreachTemplate and return info dict."""
    template_id = str(uuid.uuid4())
    template = OutreachTemplate(
        id=template_id,
        organization_id=seed_org,
        template_name="Test Template",
        template_type="email",
        subject_template="Hello {patient_name}",
        body_template="Dear {patient_name}, your placement is ready.",
        allowed_variables=["patient_name"],
        is_active=True,
        created_by_user_id=seed_admin_user["user_id"],
    )
    db_session.add(template)
    await db_session.commit()
    return {"template_id": template_id, "org_id": seed_org}


@pytest_asyncio.fixture(scope="function")
async def seed_other_org_template(
    db_session: AsyncSession, seed_other_org: str, seed_admin_user: dict
) -> str:
    """Insert an OutreachTemplate belonging to the OTHER org and return its ID."""
    template_id = str(uuid.uuid4())
    # Need a user in the other org first
    other_user_id = str(uuid.uuid4())
    other_user = User(
        id=other_user_id,
        organization_id=seed_other_org,
        email="admin2@other.com",
        full_name="Other Admin",
        role_key="admin",
        status="active",
    )
    db_session.add(other_user)
    template = OutreachTemplate(
        id=template_id,
        organization_id=seed_other_org,
        template_name="Other Org Template",
        template_type="email",
        body_template="Body from other org",
        allowed_variables=[],
        is_active=True,
        created_by_user_id=other_user_id,
    )
    db_session.add(template)
    await db_session.commit()
    return template_id


@pytest_asyncio.fixture(scope="function")
async def seed_import_job(db_session: AsyncSession, seed_org: str, seed_admin_user: dict) -> dict:
    """Insert an ImportJob record and return info dict."""
    job_id = str(uuid.uuid4())
    job = ImportJob(
        id=job_id,
        organization_id=seed_org,
        created_by_user_id=seed_admin_user["user_id"],
        file_name="test_import.csv",
        file_size_bytes=1024,
        status="complete",
        total_rows=10,
        created_count=8,
        updated_count=1,
        failed_count=1,
        error_detail_json={"errors": [{"row": 5, "message": "Missing patient_name"}]},
    )
    db_session.add(job)
    await db_session.commit()
    return {"job_id": job_id, "org_id": seed_org}


@pytest_asyncio.fixture(scope="function")
async def seed_other_org_import(
    db_session: AsyncSession, seed_other_org: str
) -> str:
    """Insert an ImportJob belonging to the OTHER org and return its ID."""
    other_user_id = str(uuid.uuid4())
    other_user = User(
        id=other_user_id,
        organization_id=seed_other_org,
        email="admin3@other.com",
        full_name="Other Admin 3",
        role_key="admin",
        status="active",
    )
    db_session.add(other_user)
    job_id = str(uuid.uuid4())
    job = ImportJob(
        id=job_id,
        organization_id=seed_other_org,
        created_by_user_id=other_user_id,
        file_name="other_import.csv",
        file_size_bytes=512,
        status="complete",
    )
    db_session.add(job)
    await db_session.commit()
    return job_id


@pytest_asyncio.fixture(scope="function")
async def seed_decline_reason(db_session: AsyncSession) -> str:
    """Insert a DeclineReasonReference row and return its code."""
    reason = DeclineReasonReference(
        id=str(uuid.uuid4()),
        code="no_beds",
        label="No Available Beds",
        display_order=1,
    )
    db_session.add(reason)
    await db_session.commit()
    return "no_beds"


@pytest_asyncio.fixture(scope="function")
async def seed_payer(db_session: AsyncSession) -> str:
    """Insert a PayerReference row and return its ID."""
    payer_id = str(uuid.uuid4())
    payer = PayerReference(
        id=payer_id,
        payer_name="Medicare",
        payer_type="government",
    )
    db_session.add(payer)
    await db_session.commit()
    return payer_id
