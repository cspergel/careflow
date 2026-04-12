# @forgeplan-node: matching-module
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
# @forgeplan-spec: AC13
# @forgeplan-spec: AC14
# @forgeplan-spec: AC15
# @forgeplan-spec: AC16
# @forgeplan-spec: AC17
"""
Shared pytest fixtures for matching-module tests.

Uses SQLite in-memory database (aiosqlite) for fast, isolated tests.
Follows the same pattern as clinical-module and facilities-module conftest.py.

Design choices:
  - Each test gets a fresh in-memory DB (function scope)
  - JWTs minted with test secret; role validated from DB row by auth middleware
  - Fixtures provide auth_ctx objects directly for service-layer tests
    (avoids HTTP overhead for unit tests)
  - HTTP client fixtures provided for router integration tests
"""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
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
# SQLAlchemy's postgresql.JSONB is not renderable by SQLite's type compiler.
# Patch the SQLiteTypeCompiler to fall back to JSON rendering for JSONB columns
# so that Base.metadata.create_all works on in-memory SQLite test engines.
# This only affects DDL compilation (CREATE TABLE) — runtime JSON I/O is fine.
# ---------------------------------------------------------------------------
if not hasattr(SQLiteTypeCompiler, "visit_JSONB"):
    SQLiteTypeCompiler.visit_JSONB = SQLiteTypeCompiler.visit_JSON  # type: ignore[attr-defined]
from placementops.core.models import (
    AuditEvent,
    CaseStatusHistory,
    ClinicalAssessment,
    Facility,
    FacilityCapabilities,
    FacilityInsuranceRule,
    FacilityMatch,
    HospitalReference,
    Organization,
    PatientCase,
    PayerReference,
    User,
)
# Import FacilityPreference to ensure its table is created by create_all
from placementops.modules.facilities.models import FacilityPreference

# ── Constants ─────────────────────────────────────────────────────────────────

TEST_SECRET = "test-secret-key-minimum-32-chars-long"
TEST_ORG_ID: UUID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TEST_PAYER_ID: UUID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
TEST_HOSPITAL_ID: UUID = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


# ── Engine / session fixtures ─────────────────────────────────────────────────


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


# ── FastAPI test client ───────────────────────────────────────────────────────


@pytest_asyncio.fixture(scope="function")
async def client(test_engine) -> AsyncGenerator[AsyncClient, None]:
    """Return an HTTPX AsyncClient backed by the in-memory SQLite engine."""
    from placementops.modules.matching.router import router as matching_router
    from placementops.modules.auth.router import router as auth_router

    app = FastAPI()
    app.include_router(matching_router, prefix="/api/v1")
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


# ── JWT / auth helpers ────────────────────────────────────────────────────────


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


# ── Seed helpers ──────────────────────────────────────────────────────────────


def make_id() -> str:
    """Return a new random UUID string."""
    return str(uuid.uuid4())


async def seed_org(db: AsyncSession, org_id: UUID = TEST_ORG_ID) -> Organization:
    org = Organization(id=str(org_id), name="Test Org")
    db.add(org)
    await db.commit()
    return org


async def seed_hospital(
    db: AsyncSession,
    org_id: UUID = TEST_ORG_ID,
    hospital_id: UUID = TEST_HOSPITAL_ID,
) -> HospitalReference:
    hospital = HospitalReference(
        id=str(hospital_id),
        organization_id=str(org_id),
        hospital_name="Test Hospital",
    )
    db.add(hospital)
    await db.commit()
    return hospital


async def seed_payer(
    db: AsyncSession,
    payer_id: UUID = TEST_PAYER_ID,
    payer_name: str = "Medicare",
) -> PayerReference:
    payer = PayerReference(
        id=str(payer_id),
        payer_name=payer_name,
        payer_type="government",
    )
    db.add(payer)
    await db.commit()
    return payer


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
    current_status: str = "ready_for_matching",
    patient_zip: str | None = None,
    insurance_primary: str | None = "Medicare",
    hospital_id: UUID | None = None,
    case_id: UUID | None = None,
) -> PatientCase:
    cid = case_id or UUID(make_id())
    case = PatientCase(
        id=str(cid),
        organization_id=str(org_id),
        patient_name="Test Patient",
        current_status=current_status,
        patient_zip=patient_zip,
        insurance_primary=insurance_primary,
        hospital_id=str(hospital_id) if hospital_id else None,
    )
    db.add(case)
    await db.commit()
    return case


async def seed_assessment(
    db: AsyncSession,
    case_id: str,
    reviewer_user_id: str,
    review_status: str = "finalized",
    recommended_loc: str = "snf",
    **clinical_flags,
) -> ClinicalAssessment:
    """Seed a ClinicalAssessment. clinical_flags override boolean defaults (all False)."""
    defaults = {
        "accepts_trach": False,
        "accepts_vent": False,
        "accepts_hd": False,
        "in_house_hemodialysis": False,
        "accepts_peritoneal_dialysis": False,
        "accepts_wound_vac": False,
        "accepts_iv_antibiotics": False,
        "accepts_tpn": False,
        "accepts_isolation_cases": False,
        "accepts_behavioral_complexity": False,
        "accepts_bariatric": False,
        "accepts_memory_care": False,
        "accepts_oxygen_therapy": False,
    }
    defaults.update(clinical_flags)
    assessment = ClinicalAssessment(
        id=make_id(),
        patient_case_id=case_id,
        reviewer_user_id=reviewer_user_id,
        review_status=review_status,
        recommended_level_of_care=recommended_loc,
        **defaults,
    )
    db.add(assessment)
    await db.commit()
    return assessment


async def seed_facility(
    db: AsyncSession,
    org_id: UUID = TEST_ORG_ID,
    facility_name: str = "Test Facility",
    facility_type: str = "snf",
    active_status: bool = True,
    latitude: float | None = None,
    longitude: float | None = None,
    facility_id: UUID | None = None,
) -> Facility:
    fid = facility_id or UUID(make_id())
    facility = Facility(
        id=str(fid),
        organization_id=str(org_id),
        facility_name=facility_name,
        facility_type=facility_type,
        active_status=active_status,
        latitude=latitude,
        longitude=longitude,
    )
    db.add(facility)
    await db.commit()
    return facility


async def seed_capabilities(
    db: AsyncSession,
    facility_id: str,
    **overrides,
) -> FacilityCapabilities:
    """Seed FacilityCapabilities with all-False defaults; use overrides to set True flags."""
    defaults = {
        "accepts_snf": False,
        "accepts_irf": False,
        "accepts_ltach": False,
        "accepts_trach": False,
        "accepts_vent": False,
        "accepts_hd": False,
        "in_house_hemodialysis": False,
        "accepts_peritoneal_dialysis": False,
        "accepts_wound_vac": False,
        "accepts_iv_antibiotics": False,
        "accepts_tpn": False,
        "accepts_bariatric": False,
        "accepts_behavioral_complexity": False,
        "accepts_memory_care": False,
        "accepts_isolation_cases": False,
        "accepts_oxygen_therapy": False,
        "weekend_admissions": False,
        "after_hours_admissions": False,
    }
    defaults.update(overrides)
    caps = FacilityCapabilities(facility_id=facility_id, **defaults)
    db.add(caps)
    await db.commit()
    return caps


async def seed_insurance_rule(
    db: AsyncSession,
    facility_id: str,
    payer_id: UUID = TEST_PAYER_ID,
    payer_name: str = "Medicare",
    accepted_status: str = "accepted",
) -> FacilityInsuranceRule:
    rule = FacilityInsuranceRule(
        id=make_id(),
        facility_id=facility_id,
        payer_id=str(payer_id),
        payer_name=payer_name,
        accepted_status=accepted_status,
    )
    db.add(rule)
    await db.commit()
    return rule


async def seed_preference(
    db: AsyncSession,
    facility_id: str,
    scope: str = "global",
    scope_reference_id: str | None = None,
    preference_rank: int = 1,
) -> FacilityPreference:
    pref = FacilityPreference(
        id=make_id(),
        facility_id=facility_id,
        scope=scope,
        scope_reference_id=scope_reference_id,
        preference_rank=preference_rank,
    )
    db.add(pref)
    await db.commit()
    return pref


# ── Auth context fixtures ──────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def seed_org_fixture(db_session: AsyncSession) -> Organization:
    """Seed default test organization."""
    return await seed_org(db_session, TEST_ORG_ID)


@pytest_asyncio.fixture
async def coordinator_user(db_session: AsyncSession, seed_org_fixture) -> User:
    """placement_coordinator user seeded in DB."""
    return await seed_user(db_session, "placement_coordinator")


@pytest_asyncio.fixture
async def clinical_user(db_session: AsyncSession, seed_org_fixture) -> User:
    """clinical_reviewer user seeded in DB."""
    return await seed_user(db_session, "clinical_reviewer")


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession, seed_org_fixture) -> User:
    """admin user seeded in DB."""
    return await seed_user(db_session, "admin")


@pytest_asyncio.fixture
async def intake_user(db_session: AsyncSession, seed_org_fixture) -> User:
    """intake_staff user seeded in DB."""
    return await seed_user(db_session, "intake_staff")


@pytest_asyncio.fixture
async def readonly_user(db_session: AsyncSession, seed_org_fixture) -> User:
    """read_only user seeded in DB."""
    return await seed_user(db_session, "read_only")


@pytest.fixture
def auth_ctx_coordinator(coordinator_user: User) -> AuthContext:
    """AuthContext for placement_coordinator."""
    return make_auth_ctx(
        user_id=UUID(coordinator_user.id),
        org_id=TEST_ORG_ID,
        role_key="placement_coordinator",
    )


@pytest.fixture
def auth_ctx_clinical(clinical_user: User) -> AuthContext:
    """AuthContext for clinical_reviewer."""
    return make_auth_ctx(
        user_id=UUID(clinical_user.id),
        org_id=TEST_ORG_ID,
        role_key="clinical_reviewer",
    )


@pytest.fixture
def auth_ctx_intake(intake_user: User) -> AuthContext:
    """AuthContext for intake_staff (403 tests)."""
    return make_auth_ctx(
        user_id=UUID(intake_user.id),
        org_id=TEST_ORG_ID,
        role_key="intake_staff",
    )


@pytest.fixture
def auth_ctx_readonly(readonly_user: User) -> AuthContext:
    """AuthContext for read_only (403 tests)."""
    return make_auth_ctx(
        user_id=UUID(readonly_user.id),
        org_id=TEST_ORG_ID,
        role_key="read_only",
    )


# ── Composite seeded fixtures ─────────────────────────────────────────────────


@pytest_asyncio.fixture
async def seeded_case(
    db_session: AsyncSession,
    seed_org_fixture: Organization,
    coordinator_user: User,
) -> PatientCase:
    """
    Case at ready_for_matching with a finalized ClinicalAssessment (no clinical complexity).

    Used for basic match generation tests that don't need specific clinical flags.
    """
    case = await seed_case(db_session, org_id=TEST_ORG_ID)
    await seed_assessment(
        db_session,
        case_id=case.id,
        reviewer_user_id=coordinator_user.id,
        review_status="finalized",
        recommended_loc="snf",
    )
    return case


@pytest_asyncio.fixture
async def seeded_payer(db_session: AsyncSession) -> PayerReference:
    """PayerReference for Medicare (used in insurance rule seeding)."""
    return await seed_payer(db_session, TEST_PAYER_ID, "Medicare")


@pytest_asyncio.fixture
async def seeded_facilities(
    db_session: AsyncSession,
    seed_org_fixture: Organization,
    seeded_payer: PayerReference,
) -> list[Facility]:
    """
    10 active + 2 inactive facilities, each with capabilities and insurance rules.

    All active facilities: accepts_snf=True, accepts Medicare as 'accepted'.
    Inactive facilities: active_status=False.
    """
    facilities = []

    # 10 active facilities
    for i in range(10):
        f = await seed_facility(
            db_session,
            org_id=TEST_ORG_ID,
            facility_name=f"Active Facility {i + 1}",
            active_status=True,
        )
        await seed_capabilities(db_session, f.id, accepts_snf=True)
        await seed_insurance_rule(
            db_session, f.id, TEST_PAYER_ID, "Medicare", "accepted"
        )
        facilities.append(f)

    # 2 inactive facilities — must never appear in match results (AC2)
    for i in range(2):
        f = await seed_facility(
            db_session,
            org_id=TEST_ORG_ID,
            facility_name=f"Inactive Facility {i + 1}",
            active_status=False,
        )
        await seed_capabilities(db_session, f.id, accepts_snf=True)
        await seed_insurance_rule(
            db_session, f.id, TEST_PAYER_ID, "Medicare", "accepted"
        )
        facilities.append(f)

    return facilities
