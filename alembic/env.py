# @forgeplan-node: core-infrastructure
"""
Alembic environment — async-aware migration runner.

Uses DATABASE_DIRECT_URL (port 5432) — NOT DATABASE_URL (port 6543).
Supavisor transaction mode is incompatible with Alembic's migration approach.
"""
# @forgeplan-spec: AC1

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

# Import Base so all models are registered in metadata
from placementops.core.database import Base

# Import all models to populate Base.metadata
from placementops.core.models import (  # noqa: F401
    Organization,
    UserRole,
    DeclineReasonReference,
    PayerReference,
    HospitalReference,
    User,
    PatientCase,
    Facility,
    FacilityCapabilities,
    FacilityInsuranceRule,
    FacilityContact,
    OutreachAction,
    OutreachTemplate,
    ClinicalAssessment,
    FacilityMatch,
    ImportJob,
    PlacementOutcome,
    AuditEvent,
    CaseStatusHistory,
)

# Alembic Config object (access to alembic.ini)
config = context.config

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata for autogenerate support
target_metadata = Base.metadata

# DATABASE_DIRECT_URL — port 5432 direct connection for migrations
# This is the ONLY place DATABASE_DIRECT_URL is used.
DATABASE_DIRECT_URL: str = os.environ["DATABASE_DIRECT_URL"]


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode (emit SQL without connecting to the DB).
    Useful for generating SQL scripts for DBA review.
    """
    context.configure(
        url=DATABASE_DIRECT_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode using an async engine against DATABASE_DIRECT_URL.

    Uses run_sync() to execute the synchronous Alembic migration functions
    within an async context. NullPool is NOT used here — migrations require
    a persistent connection and multiple transactions.
    """
    connectable = create_async_engine(
        DATABASE_DIRECT_URL,
        poolclass=pool.NullPool,  # One-shot: create, migrate, destroy
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
