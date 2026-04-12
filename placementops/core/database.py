# @forgeplan-node: core-infrastructure
"""
Database engine, session factory, and declarative base for PlacementOps.

Uses NullPool + statement_cache_size=0 for Supavisor transaction mode (port 6543).
expire_on_commit=False prevents MissingGreenlet errors in async context.
"""
# @forgeplan-decision: D-core-1-nullpool-supavisor -- NullPool with statement_cache_size=0 and prepared_statement_cache_size=0. Why: Supavisor transaction mode (port 6543) cannot maintain prepared statements across transactions; NullPool hands connection management to Supavisor entirely

import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

# @forgeplan-spec: AC2
DATABASE_URL: str = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///:memory:")  # port 6543 — Supavisor transaction mode; falls back to in-memory SQLite for test environments

_connect_args: dict = {}
if "postgresql" in DATABASE_URL or "postgres" in DATABASE_URL:
    # Supavisor-specific settings — only valid for asyncpg driver
    _connect_args = {
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
        "server_settings": {"jit": "off"},
    }

engine = create_async_engine(
    DATABASE_URL,
    poolclass=NullPool,
    connect_args=_connect_args,
    echo=False,
)

# @forgeplan-spec: AC2
AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Required: prevents MissingGreenlet on detached objects
)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session."""
    async with AsyncSessionLocal() as session:
        yield session
