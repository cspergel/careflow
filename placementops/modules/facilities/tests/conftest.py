# @forgeplan-node: facilities-module
"""
pytest fixtures for facilities-module tests.

Uses SQLite in-memory (aiosqlite) for database — no live Postgres required.
JWT minting reuses the helper from the auth module.
AuditEvent is backed by a JSON column in SQLite (JSONB not supported, but
SQLAlchemy falls back gracefully for SQLite).

All facility tests are self-contained within placementops/modules/facilities/tests/.
"""

import os
import pytest
import pytest_asyncio
from datetime import datetime, timezone
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
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-secret-key-minimum-32-chars-long")
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")

from placementops.core.database import Base, get_db
from placementops.core.models import (
    Facility,
    FacilityCapabilities,
    FacilityContact,
    FacilityInsuranceRule,
    Organization,
    PayerReference,
    User,
)
# Import FacilityPreference to ensure its table is created by create_all
from placementops.modules.facilities.models import FacilityPreference
from placementops.modules.facilities.router import router as facilities_router
from placementops.modules.auth.tests.helpers import TEST_ORG_ID, TEST_SECRET, make_jwt

# Stable test IDs
TEST_ORG_ID_A: UUID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TEST_ORG_ID_B: UUID = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
TEST_PAYER_ID: UUID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


# ── SQLite engine ─────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def async_engine():
    """In-memory SQLite engine with all ORM tables created."""
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
    """Async session bound to the test in-memory database."""
    session_factory = async_sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session


# ── FastAPI test app ──────────────────────────────────────────────────────────

@pytest.fixture
def facilities_app(db_session):
    """Minimal FastAPI app with the facilities router mounted."""
    app = FastAPI()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.include_router(facilities_router, prefix="/api/v1")
    return app


@pytest_asyncio.fixture
async def async_client(facilities_app):
    """Async HTTP client for the facilities test app."""
    async with AsyncClient(
        transport=ASGITransport(app=facilities_app), base_url="http://test"
    ) as client:
        yield client


# ── JWT helpers ───────────────────────────────────────────────────────────────

def make_auth_header(
    role_key: str,
    user_id: UUID | None = None,
    org_id: UUID | None = None,
) -> dict:
    """Return Authorization header dict with a test JWT for the given role."""
    uid = user_id or uuid4()
    oid = org_id or TEST_ORG_ID_A
    token = make_jwt(user_id=uid, org_id=oid, role_key=role_key, secret=TEST_SECRET)
    return {"Authorization": f"Bearer {token}"}


# ── DB seed helpers ───────────────────────────────────────────────────────────

async def seed_org(db: AsyncSession, org_id: UUID, name: str = "Test Org") -> Organization:
    org = Organization(id=str(org_id), name=name)
    db.add(org)
    await db.commit()
    return org


async def seed_user(
    db: AsyncSession,
    role_key: str,
    user_id: UUID | None = None,
    org_id: UUID | None = None,
) -> User:
    uid = user_id or uuid4()
    oid = org_id or TEST_ORG_ID_A
    user = User(
        id=str(uid),
        organization_id=str(oid),
        email=f"{role_key}_{str(uid)[:8]}@example.com",
        full_name=f"{role_key} User",
        role_key=role_key,
        status="active",
    )
    db.add(user)
    await db.commit()
    return user


async def seed_payer(db: AsyncSession, payer_id: UUID = TEST_PAYER_ID) -> PayerReference:
    payer = PayerReference(id=str(payer_id), payer_name="Medicare", payer_type="government")
    db.add(payer)
    await db.commit()
    return payer


async def seed_facility(
    db: AsyncSession,
    org_id: UUID = TEST_ORG_ID_A,
    facility_type: str = "snf",
    facility_name: str = "Test SNF",
    state: str = "CA",
    county: str = "Los Angeles",
) -> Facility:
    facility = Facility(
        organization_id=str(org_id),
        facility_name=facility_name,
        facility_type=facility_type,
        state=state,
        county=county,
    )
    db.add(facility)
    await db.commit()
    return facility


async def seed_capabilities(
    db: AsyncSession,
    facility_id: str,
    **overrides: bool,
) -> FacilityCapabilities:
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
        "last_verified_at": datetime.now(timezone.utc),
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
    accepted_status: str = "accepted",
) -> FacilityInsuranceRule:
    rule = FacilityInsuranceRule(
        facility_id=facility_id,
        payer_id=str(payer_id),
        payer_name="Medicare",
        accepted_status=accepted_status,
        last_verified_at=datetime.now(timezone.utc),
    )
    db.add(rule)
    await db.commit()
    return rule


async def seed_contact(
    db: AsyncSession,
    facility_id: str,
    contact_name: str = "Jane Doe",
    phone_extension: str | None = None,
    best_call_window: str | None = None,
    phone_contact_name: str | None = None,
) -> FacilityContact:
    contact = FacilityContact(
        facility_id=facility_id,
        contact_name=contact_name,
        phone="555-0100",
        phone_extension=phone_extension,
        best_call_window=best_call_window,
        phone_contact_name=phone_contact_name,
        is_primary=True,
    )
    db.add(contact)
    await db.commit()
    return contact


async def seed_preference(
    db: AsyncSession,
    facility_id: str,
    scope: str = "global",
    preference_rank: int = 1,
    scope_reference_id: str | None = None,
) -> FacilityPreference:
    pref = FacilityPreference(
        facility_id=facility_id,
        scope=scope,
        preference_rank=preference_rank,
        scope_reference_id=scope_reference_id,
    )
    db.add(pref)
    await db.commit()
    return pref


# ── Pytest fixtures for common DB state ───────────────────────────────────────

@pytest_asyncio.fixture
async def org_a(db_session) -> Organization:
    return await seed_org(db_session, TEST_ORG_ID_A, "Org A")


@pytest_asyncio.fixture
async def org_b(db_session) -> Organization:
    return await seed_org(db_session, TEST_ORG_ID_B, "Org B")


@pytest_asyncio.fixture
async def payer(db_session, org_a) -> PayerReference:
    return await seed_payer(db_session)


@pytest_asyncio.fixture
async def admin_user(db_session, org_a) -> User:
    return await seed_user(db_session, "admin")


@pytest_asyncio.fixture
async def coordinator_user(db_session, org_a) -> User:
    return await seed_user(db_session, "placement_coordinator")


@pytest_asyncio.fixture
async def intake_user(db_session, org_a) -> User:
    return await seed_user(db_session, "intake_staff")


@pytest_asyncio.fixture
async def clinical_user(db_session, org_a) -> User:
    return await seed_user(db_session, "clinical_reviewer")


@pytest_asyncio.fixture
async def manager_user(db_session, org_a) -> User:
    return await seed_user(db_session, "manager")


@pytest_asyncio.fixture
async def read_only_user(db_session, org_a) -> User:
    return await seed_user(db_session, "read_only")
