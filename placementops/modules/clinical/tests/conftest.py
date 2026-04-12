# @forgeplan-node: clinical-module
"""
Shared test fixtures for the clinical module tests.

Uses SQLite in-memory database for fast, isolated tests.
Follows the same pattern as intake-module's conftest.py.
"""

from __future__ import annotations

import os
import uuid
from datetime import date

# Set test environment variables before any module imports that read them
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret-key-minimum-32-chars-long")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import jwt
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from placementops.core.database import Base, get_db
from placementops.core.models import (
    AuditEvent,
    CaseStatusHistory,
    ClinicalAssessment,
    HospitalReference,
    Organization,
    PatientCase,
    User,
)

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# ---------------------------------------------------------------------------
# Engine / session fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Fresh in-memory SQLite engine per test."""
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
async def client(test_engine):
    """Return an HTTPX AsyncClient backed by the in-memory SQLite engine."""
    from fastapi import FastAPI
    from placementops.modules.clinical.router import router as clinical_router
    from placementops.modules.auth.router import router as auth_router

    app = FastAPI()
    app.include_router(clinical_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")

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
# Seed helpers
# ---------------------------------------------------------------------------


def make_id() -> str:
    return str(uuid.uuid4())


def make_jwt(user_id: str, org_id: str, role_key: str) -> str:
    secret = os.environ["SUPABASE_JWT_SECRET"]
    payload = {
        "sub": user_id,
        "aud": "authenticated",
        "exp": 9999999999,
        "app_metadata": {"organization_id": org_id, "role_key": role_key},
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def auth_headers(user_id: str, org_id: str, role_key: str) -> dict:
    return {"Authorization": f"Bearer {make_jwt(user_id, org_id, role_key)}"}


@pytest_asyncio.fixture
async def seed_org(db_session: AsyncSession) -> str:
    org_id = make_id()
    db_session.add(Organization(id=org_id, name="Test Org"))
    await db_session.commit()
    return org_id


@pytest_asyncio.fixture
async def seed_org2(db_session: AsyncSession) -> str:
    """Second org for cross-org isolation tests."""
    org_id = make_id()
    db_session.add(Organization(id=org_id, name="Other Org"))
    await db_session.commit()
    return org_id


async def _seed_user(db_session, org_id, role_key, email=None) -> dict:
    uid = make_id()
    db_session.add(
        User(
            id=uid,
            organization_id=org_id,
            email=email or f"{role_key}-{uid[:8]}@test.com",
            full_name=f"{role_key} User",
            role_key=role_key,
            status="active",
        )
    )
    await db_session.commit()
    return {"user_id": uid, "org_id": org_id, "role_key": role_key}


@pytest_asyncio.fixture
async def clinical_reviewer(db_session: AsyncSession, seed_org: str) -> dict:
    return await _seed_user(db_session, seed_org, "clinical_reviewer")


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession, seed_org: str) -> dict:
    return await _seed_user(db_session, seed_org, "admin")


@pytest_asyncio.fixture
async def intake_user(db_session: AsyncSession, seed_org: str) -> dict:
    return await _seed_user(db_session, seed_org, "intake_staff")


@pytest_asyncio.fixture
async def coordinator_user(db_session: AsyncSession, seed_org: str) -> dict:
    return await _seed_user(db_session, seed_org, "placement_coordinator")


async def _seed_case(
    db_session: AsyncSession,
    org_id: str,
    current_status: str = "needs_clinical_review",
) -> PatientCase:
    case_id = make_id()
    case = PatientCase(
        id=case_id,
        organization_id=org_id,
        patient_name="Test Patient",
        current_status=current_status,
    )
    db_session.add(case)
    await db_session.commit()
    return case


@pytest_asyncio.fixture
async def clinical_case(db_session: AsyncSession, seed_org: str) -> PatientCase:
    """Case at needs_clinical_review status."""
    return await _seed_case(db_session, seed_org, "needs_clinical_review")


@pytest_asyncio.fixture
async def under_review_case(db_session: AsyncSession, seed_org: str) -> PatientCase:
    """Case at under_clinical_review status."""
    return await _seed_case(db_session, seed_org, "under_clinical_review")


@pytest_asyncio.fixture
async def closed_case(db_session: AsyncSession, seed_org: str) -> PatientCase:
    """Closed case for 409 tests."""
    return await _seed_case(db_session, seed_org, "closed")


async def _seed_assessment(
    db_session: AsyncSession,
    case_id: str,
    reviewer_user_id: str,
    review_status: str = "draft",
    recommended_loc: str = "",
) -> ClinicalAssessment:
    assessment = ClinicalAssessment(
        id=make_id(),
        patient_case_id=case_id,
        reviewer_user_id=reviewer_user_id,
        review_status=review_status,
        recommended_level_of_care=recommended_loc,
    )
    db_session.add(assessment)
    await db_session.commit()
    return assessment
