# Research: FastAPI SQLAlchemy Alembic Multi-Tenant PostgreSQL Background Tasks

**Date:** 2026-04-10
**Stack:** FastAPI + SQLAlchemy 2.0 + Alembic + PostgreSQL (Supabase) + asyncpg
**Tier:** LARGE (20+ tables, multi-tenant via organization_id, file import background tasks)

---

## Topic 1: SQLAlchemy Async vs Sync for FastAPI

### Verdict: Use Async Throughout

For a LARGE-tier FastAPI backend with concurrent import jobs and HTTP traffic sharing the
same event loop, async is the correct choice — but only if every layer is consistently async.

### The Core Tradeoff

**Async does NOT make individual queries faster.** A single `SELECT` via asyncpg is
measurably slower per-query than the same call via psycopg2 (sync). The slowdown comes
from coroutine scheduling overhead on top of the network round-trip.

**Async wins at concurrency.** Under load (many simultaneous requests), async handles
3–5x more requests/second on the same hardware because it never blocks the event loop
waiting on I/O. One sync DB call in an `async def` endpoint blocks all concurrent
requests — which is worse than plain sync.

The rule: **either go fully async or stay fully sync.** Mixing is the worst outcome.

### Recommended Engine Setup (Production)

```python
# app/db/engine.py
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)
from sqlalchemy.pool import NullPool

# For Supabase Transaction Mode (port 6543) — see Topic 5
DATABASE_URL = "postgresql+asyncpg://user:pass@aws-0-region.pooler.supabase.com:6543/postgres"

engine = create_async_engine(
    DATABASE_URL,
    poolclass=NullPool,          # Let Supavisor manage connections (see Topic 5)
    connect_args={
        "statement_cache_size": 0,           # Required for PgBouncer/Supavisor compat
        "prepared_statement_cache_size": 0,  # Required — asyncpg still creates these
        "server_settings": {"jit": "off"},   # Reduces edge-case failures under burst
    },
    pool_pre_ping=True,           # Validate connections before use
    echo=False,                   # Set True in dev only
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Keep attributes accessible after commit in async contexts
)
```

### FastAPI Dependency Injection

```python
# app/db/deps.py
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.engine import AsyncSessionLocal

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
        # session.close() called automatically by context manager
```

Usage in a route:

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

@router.get("/placements")
async def list_placements(
    db: AsyncSession = Depends(get_db),
    org_id: UUID = Depends(current_org),
):
    result = await db.execute(
        select(Placement).where(Placement.organization_id == org_id)
    )
    return result.scalars().all()
```

### FastAPI Lifespan for Engine Startup/Teardown

```python
# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.db.engine import engine

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: engine is lazy — no explicit init needed with NullPool
    yield
    # Shutdown: dispose engine cleanly
    await engine.dispose()

app = FastAPI(lifespan=lifespan)
```

### Alembic Configuration for Async Engine

Alembic runs synchronously by default. For async engines you must bridge with
`run_sync`:

```python
# alembic/env.py
import asyncio
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy import pool
from alembic import context
from app.db.base import Base  # imports all models

target_metadata = Base.metadata

def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,        # Detect column type changes
        compare_server_defaults=True,
    )
    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations():
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # Always NullPool for migration runs
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()

def run_migrations_online():
    asyncio.run(run_async_migrations())
```

Note: Alembic migrations run against the **direct connection** (port 5432), not the
transaction pooler — prepared statements and session-level features are fine there.

### Async vs Sync Decision Matrix

| Scenario | Recommendation |
|---|---|
| HTTP request handlers | `async def` + `AsyncSession` |
| Background import tasks (BackgroundTasks) | `async def` + new `AsyncSession` per task |
| Alembic migration scripts | sync bridge via `run_sync` |
| CLI scripts / one-off tools | sync engine + sync session acceptable |
| Tests (pytest-asyncio) | `AsyncSession` + `pytest-asyncio` fixtures |

---

## Topic 2: Alembic Migration Patterns for Multi-Tenant Schemas

### Architecture Choice: Shared Schema with organization_id Column

This project uses a **shared-schema multi-tenancy** approach — all tenants in one
PostgreSQL database with an `organization_id` column on every table. This is the correct
choice for a LARGE Supabase-hosted backend (schema-per-tenant would hit Supabase's
connection limits and complicate Supabase Auth).

Alembic handles this naturally — migrations are just standard schema migrations. No
tenant-iteration required because there is only one schema.

### Model Base Pattern: Enforce organization_id at the ORM Level

```python
# app/db/base.py
from sqlalchemy.orm import DeclarativeBase, declared_attr
from sqlalchemy import Column, UUID, func, DateTime
import uuid

class Base(DeclarativeBase):
    pass

class TenantMixin:
    """Mixin that adds organization_id to every tenant-scoped table."""

    @declared_attr
    def organization_id(cls):
        return Column(
            UUID(as_uuid=True),
            nullable=False,
            index=True,
            comment="Foreign key to organizations table — row-level tenant isolation",
        )

class TimestampMixin:
    """Adds created_at / updated_at with server-side defaults."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

# Every tenant-scoped model:
class Placement(TenantMixin, TimestampMixin, Base):
    __tablename__ = "placements"
    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # ... other columns
```

### Alembic autogenerate Setup

Ensure all models are imported before autogenerate runs, otherwise Alembic won't detect
new tables:

```python
# app/db/base.py — the "registry" module
from app.db.base_class import Base  # noqa: F401
from app.models.organization import Organization  # noqa: F401
from app.models.placement import Placement  # noqa: F401
from app.models.resident import Resident  # noqa: F401
# ... all 20+ models imported here
```

```ini
# alembic.ini
[alembic]
script_location = alembic
sqlalchemy.url = postgresql+asyncpg://%(DB_USER)s:%(DB_PASS)s@%(DB_HOST)s:5432/%(DB_NAME)s
```

### Seed Data Migrations

Use `op.bulk_insert()` with an ad-hoc table definition (never import your live model
class into a migration — it breaks when the model later changes):

```python
# alembic/versions/0002_seed_lookup_tables.py
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
import uuid

def upgrade():
    # Ad-hoc table definition — don't import live models
    care_levels_table = sa.table(
        "care_levels",
        sa.column("id", UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("organization_id", UUID(as_uuid=True)),
    )

    # Seed system-wide lookup values (organization_id = system org UUID)
    SYSTEM_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

    op.bulk_insert(care_levels_table, [
        {"id": uuid.uuid4(), "name": "Independent", "organization_id": SYSTEM_ORG_ID},
        {"id": uuid.uuid4(), "name": "Assisted Living", "organization_id": SYSTEM_ORG_ID},
        {"id": uuid.uuid4(), "name": "Memory Care", "organization_id": SYSTEM_ORG_ID},
        {"id": uuid.uuid4(), "name": "Skilled Nursing", "organization_id": SYSTEM_ORG_ID},
    ])

def downgrade():
    op.execute("DELETE FROM care_levels WHERE organization_id = '00000000-0000-0000-0000-000000000001'")
```

### Enum Column Pattern

For PostgreSQL native enums (preferred over VARCHAR CHECK constraints for type safety):

```python
# In migration file — create enum then table
from sqlalchemy.dialects.postgresql import ENUM

def upgrade():
    # Create the enum type first
    placement_status_enum = ENUM(
        "pending", "active", "discharged", "cancelled",
        name="placement_status",
        create_type=True,  # Creates the PG TYPE
    )
    placement_status_enum.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "placements",
        sa.Column("status", sa.Enum("pending", "active", "discharged", "cancelled",
                                    name="placement_status"), nullable=False,
                  server_default="pending"),
    )

def downgrade():
    op.drop_column("placements", "status")
    op.execute("DROP TYPE IF EXISTS placement_status")
```

### Critical Rule: Never Import Live Models in Migrations

```python
# BAD — breaks when Placement model changes in future
from app.models.placement import Placement
op.bulk_insert(Placement.__table__, [...])

# GOOD — ad-hoc table that matches current migration's schema snapshot
placements_table = sa.table("placements", sa.column("id", UUID), sa.column("status", sa.String))
op.bulk_insert(placements_table, [...])
```

### Migration Naming Convention

```
alembic/versions/
  0001_initial_schema.py
  0002_seed_lookup_data.py
  0003_add_placement_status_enum.py
  0004_add_audit_triggers.py     # see Topic 4
  0005_add_import_jobs_table.py  # see Topic 3
```

Use sequential prefixes for readability. Alembic's chain is determined by `down_revision`,
not file names, but readable names help debugging a 20+ migration chain.

---

## Topic 3: FastAPI BackgroundTasks for Long-Running File Import

### The Core Limitation of BackgroundTasks

FastAPI's `BackgroundTasks` runs in the **same event loop** as the HTTP server, in the
same process, with no persistence. If the server restarts mid-import, the job is lost.
There is no built-in retry, no cross-worker visibility, and no result storage.

For Phase 1 (no external broker), this is manageable if you:
1. Store all job state in the **database** (not in-memory dicts)
2. Create a **new session** inside the background task (never reuse the request session)
3. Design for eventual migration to Celery/ARQ in Phase 2

### ImportJob Database Table

```python
# app/models/import_job.py
import enum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import Enum as SAEnum, Text, Integer, DateTime, func
import uuid

class ImportJobStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class ImportJob(TenantMixin, Base):
    __tablename__ = "import_jobs"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    status: Mapped[ImportJobStatus] = mapped_column(
        SAEnum(ImportJobStatus, name="import_job_status"),
        nullable=False,
        default=ImportJobStatus.PENDING,
        index=True,
    )
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    import_type: Mapped[str] = mapped_column(Text, nullable=False)  # "placements", "residents"

    # Progress tracking
    total_rows: Mapped[int] = mapped_column(Integer, nullable=True)
    rows_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_succeeded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rows_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Error detail — array of {row: N, error: "message", data: {...}}
    row_errors: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    # Summary error for job-level failures (e.g., unreadable file)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
```

### POST Endpoint: Enqueue Import

```python
# app/api/routes/imports.py
from fastapi import APIRouter, BackgroundTasks, UploadFile, Depends
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

@router.post("/imports/placements", status_code=202)
async def upload_placement_import(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Read file contents eagerly — UploadFile is not safe to pass to background task
    file_bytes = await file.read()

    # Create the job record synchronously before responding
    job = ImportJob(
        organization_id=current_user.organization_id,
        file_name=file.filename,
        import_type="placements",
        status=ImportJobStatus.PENDING,
        created_by=current_user.id,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    # Schedule background processing — pass job_id and file bytes, NOT the session
    background_tasks.add_task(
        process_placement_import,
        job_id=job.id,
        org_id=current_user.organization_id,
        file_bytes=file_bytes,
        filename=file.filename,
    )

    return {"job_id": str(job.id), "status": "pending"}
```

**Critical:** Pass `job_id` to the background task, not the session or the ORM object.
The request session closes after the response; using it in the background task causes
`DetachedInstanceError` or connection pool exhaustion.

### Background Task: Session Scoping

```python
# app/services/import_processor.py
import asyncio
import openpyxl
from datetime import datetime, timezone
from sqlalchemy import select, update
from app.db.engine import AsyncSessionLocal

async def process_placement_import(
    job_id: UUID,
    org_id: UUID,
    file_bytes: bytes,
    filename: str,
) -> None:
    """
    Background task — creates its own session lifecycle, completely
    independent of the request session.
    """
    async with AsyncSessionLocal() as session:
        # Mark job as started
        await session.execute(
            update(ImportJob)
            .where(ImportJob.id == job_id)
            .values(status=ImportJobStatus.PROCESSING, started_at=datetime.now(timezone.utc))
        )
        await session.commit()

        try:
            errors = []
            rows_succeeded = 0
            rows_failed = 0

            # Parse XLSX from bytes
            wb = openpyxl.load_workbook(filename=BytesIO(file_bytes), read_only=True)
            ws = wb.active

            headers = [cell.value for cell in next(ws.iter_rows(max_row=1))]
            data_rows = list(ws.iter_rows(min_row=2, values_only=True))
            total_rows = len(data_rows)

            # Update total count
            await session.execute(
                update(ImportJob)
                .where(ImportJob.id == job_id)
                .values(total_rows=total_rows)
            )
            await session.commit()

            # Process rows in batches to avoid holding a transaction open too long
            BATCH_SIZE = 50
            for batch_start in range(0, total_rows, BATCH_SIZE):
                batch = data_rows[batch_start : batch_start + BATCH_SIZE]

                async with session.begin():  # One transaction per batch
                    for row_idx, row in enumerate(batch, start=batch_start + 2):
                        try:
                            row_dict = dict(zip(headers, row))
                            placement = _parse_placement_row(row_dict, org_id)
                            session.add(placement)
                            rows_succeeded += 1
                        except ValueError as exc:
                            rows_failed += 1
                            errors.append({
                                "row": row_idx,
                                "error": str(exc),
                                "data": {k: str(v) for k, v in zip(headers, row)},
                            })

                # Update progress after each batch (outside the batch transaction)
                await session.execute(
                    update(ImportJob)
                    .where(ImportJob.id == job_id)
                    .values(
                        rows_processed=batch_start + len(batch),
                        rows_succeeded=rows_succeeded,
                        rows_failed=rows_failed,
                        row_errors=errors[-100:],  # Cap stored errors to last 100
                    )
                )
                await session.commit()

            # Mark completed
            await session.execute(
                update(ImportJob)
                .where(ImportJob.id == job_id)
                .values(
                    status=ImportJobStatus.COMPLETED,
                    completed_at=datetime.now(timezone.utc),
                    row_errors=errors,
                )
            )
            await session.commit()

        except Exception as exc:
            # Job-level failure (unreadable file, DB constraint, etc.)
            await session.execute(
                update(ImportJob)
                .where(ImportJob.id == job_id)
                .values(
                    status=ImportJobStatus.FAILED,
                    completed_at=datetime.now(timezone.utc),
                    error_message=str(exc),
                )
            )
            await session.commit()
            # Do not re-raise — background task failures are silent to the client
```

### Note: BackgroundTasks Runs in Event Loop Context

FastAPI's `BackgroundTasks` runs async tasks correctly — `async def` background
functions are awaited by FastAPI on the event loop. This works well. The important
constraint is that no I/O-blocking code (sync file reads, sync DB calls) goes inside an
`async def` background task.

If `process_placement_import` contains CPU-heavy parsing (large XLSX files), offload to a
thread pool to avoid blocking the event loop:

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Inside the background task, for CPU-heavy parsing:
loop = asyncio.get_event_loop()
with ThreadPoolExecutor() as pool:
    data_rows = await loop.run_in_executor(pool, _parse_xlsx_sync, file_bytes)
```

### GET Endpoint: Status Polling

```python
@router.get("/imports/{job_id}")
async def get_import_status(
    job_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(ImportJob).where(
            ImportJob.id == job_id,
            ImportJob.organization_id == current_user.organization_id,
        )
    )
    job = result.scalar_one_or_none()
    if not job:
        raise HTTPException(status_code=404, detail="Import job not found")

    progress_pct = 0
    if job.total_rows and job.total_rows > 0:
        progress_pct = round((job.rows_processed / job.total_rows) * 100)

    return {
        "job_id": str(job.id),
        "status": job.status,
        "file_name": job.file_name,
        "progress_pct": progress_pct,
        "total_rows": job.total_rows,
        "rows_processed": job.rows_processed,
        "rows_succeeded": job.rows_succeeded,
        "rows_failed": job.rows_failed,
        "row_errors": job.row_errors,      # Full error list when complete
        "error_message": job.error_message,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
    }
```

### Phase 1 Limitations (Honest Assessment)

| Limitation | Impact | Phase 2 Fix |
|---|---|---|
| No retry on failure | Import fails permanently if DB blip occurs | ARQ or Celery |
| Job lost on server restart | Mid-import progress lost | Celery + Redis |
| CPU-heavy parsing blocks event loop | Slow on large files (>5000 rows) | `run_in_executor` or separate worker |
| No concurrency limit | 10 simultaneous imports = 10x CPU | Celery concurrency setting |
| No cancellation | Cannot stop a running import | Celery `revoke()` |

For Phase 1 with expected import sizes <1000 rows and low concurrency, these are
acceptable trade-offs. The database-backed job table ensures status survives server
restarts even if the task itself does not.

---

## Topic 4: SQLAlchemy Model Patterns for Audit Logging

### Architecture: Separate AuditEvent Table, Immutable at DB Level

The recommended pattern is a single `audit_events` table (not per-model audit tables)
that captures all mutations across the system. Immutability is enforced via a PostgreSQL
trigger that raises an exception on any UPDATE or DELETE.

### AuditEvent SQLAlchemy Model

```python
# app/models/audit_event.py
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy import Text, DateTime, func
import uuid

class AuditEvent(Base):
    """
    Insert-only audit log. Never updated or deleted — enforced by DB trigger.
    No TenantMixin because organization_id is stored in the payload JSON,
    or add it as a plain column for indexing.
    """
    __tablename__ = "audit_events"

    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # When
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    # Who
    actor_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)  # "user", "system", "import"
    organization_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    # What
    event_type: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    # e.g., "placement.created", "resident.discharged", "import.completed"

    # Target entity
    entity_type: Mapped[str | None] = mapped_column(Text, nullable=True)  # "Placement"
    entity_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    # Full snapshot
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # e.g., {"before": {...}, "after": {...}} for updates,
    #        {"created": {...}} for inserts

    # Request context
    ip_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(Text, nullable=True)
```

### PostgreSQL Immutability Trigger

Add this trigger via an Alembic migration (not via SQLAlchemy DDL events — the DDL
event approach is fragile across async engine resets):

```python
# alembic/versions/0004_add_audit_immutability_trigger.py
from alembic import op

def upgrade():
    # The function that enforces immutability
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_audit_event_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION
                'audit_events is immutable — UPDATE and DELETE are not permitted. '
                'Attempted operation: % on row id=%',
                TG_OP, OLD.id;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql SECURITY DEFINER;
    """)

    # Trigger fires BEFORE UPDATE or DELETE — blocks both operations
    op.execute("""
        CREATE TRIGGER audit_events_immutability
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_event_mutation();
    """)

    # Optional: also prevent TRUNCATE
    op.execute("""
        CREATE OR REPLACE RULE audit_events_no_truncate AS
        ON DELETE TO audit_events DO INSTEAD NOTHING;
    """)

def downgrade():
    op.execute("DROP TRIGGER IF EXISTS audit_events_immutability ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_event_mutation()")
```

### AuditEvent Service: Writing Audit Events from Application Code

```python
# app/services/audit.py
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.audit_event import AuditEvent

async def record_audit_event(
    session: AsyncSession,
    event_type: str,
    actor_id: UUID | None,
    actor_type: str,
    organization_id: UUID | None,
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    payload: dict | None = None,
    request_id: str | None = None,
) -> None:
    """
    Fire-and-forget audit write. Runs inside the caller's transaction so it
    rolls back atomically with the main operation on failure.
    """
    event = AuditEvent(
        event_type=event_type,
        actor_id=actor_id,
        actor_type=actor_type,
        organization_id=organization_id,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload or {},
        request_id=request_id,
    )
    session.add(event)
    # Do NOT commit here — let the caller's transaction include this INSERT
```

Usage:

```python
# In a service function, within an existing transaction
async def discharge_resident(session, resident_id, org_id, actor_id):
    resident = await session.get(Resident, resident_id)
    before_snapshot = resident.__dict__.copy()

    resident.status = "discharged"
    resident.discharged_at = datetime.now(timezone.utc)

    await record_audit_event(
        session=session,
        event_type="resident.discharged",
        actor_id=actor_id,
        actor_type="user",
        organization_id=org_id,
        entity_type="Resident",
        entity_id=resident_id,
        payload={
            "before": {"status": before_snapshot["status"]},
            "after": {"status": "discharged"},
        },
    )
    await session.commit()  # Both resident update and audit event committed atomically
```

### Alternative: SQLAlchemy ORM Event Hook (For Automatic Capture)

For automatically capturing all model mutations without manual calls:

```python
# app/db/audit_hooks.py
from sqlalchemy import event
from sqlalchemy.orm import Session

def attach_audit_listeners(session_class):
    @event.listens_for(session_class, "before_flush")
    def receive_before_flush(session, flush_context, instances):
        for obj in session.new:
            if hasattr(obj, "__audit__") and obj.__audit__:
                _queue_audit_event(session, "created", obj)
        for obj in session.dirty:
            if hasattr(obj, "__audit__") and obj.__audit__:
                _queue_audit_event(session, "updated", obj)
        for obj in session.deleted:
            if hasattr(obj, "__audit__") and obj.__audit__:
                _queue_audit_event(session, "deleted", obj)

def _queue_audit_event(session, operation, obj):
    event = AuditEvent(
        event_type=f"{obj.__tablename__}.{operation}",
        entity_type=obj.__class__.__name__,
        entity_id=getattr(obj, "id", None),
        organization_id=getattr(obj, "organization_id", None),
        payload={"operation": operation},
    )
    session.add(event)
```

The ORM hook approach is convenient but has two risks: (1) it captures all flushes
including internal SQLAlchemy operations, which can cause recursion, and (2) it makes
auditing implicit, which can hide audit gaps. The explicit `record_audit_event()` call
is more predictable for a LARGE-tier project.

### Recommended: Hybrid Approach

- Use the explicit service call (`record_audit_event`) for business-level events
  (resident discharged, placement created, import completed).
- Use a PostgreSQL trigger for structural audit of sensitive tables (users, organizations)
  where you want DB-level guarantees regardless of which application inserts.

### Index Strategy for AuditEvent

```sql
-- For "show audit trail for entity X" queries
CREATE INDEX idx_audit_events_entity ON audit_events(entity_type, entity_id, occurred_at DESC);

-- For "show all events by org in date range" queries
CREATE INDEX idx_audit_events_org_time ON audit_events(organization_id, occurred_at DESC);

-- For "show events by actor" queries
CREATE INDEX idx_audit_events_actor ON audit_events(actor_id, occurred_at DESC);
```

Add these in the same Alembic migration that creates the `audit_events` table using
`op.create_index()`.

---

## Topic 5: Connection Pooling for Supabase PostgreSQL + SQLAlchemy

### The Supabase + asyncpg Problem (Verified)

This is a **known, confirmed issue** with multiple GitHub issues and a fix that must be
explicitly applied. PgBouncer (and Supabase's Supavisor in transaction mode) do not
support prepared statements. asyncpg creates prepared statements by default. The result:

```
asyncpg.exceptions.InvalidSQLStatementNameError:
prepared statement "asyncpg_stmt_9" does not exist
```

This error appears intermittently under burst load — fine in dev, fails in production.

### Three Connection Options (Pick One)

| Option | Port | Mode | Use Case |
|---|---|---|---|
| Direct (no pooler) | 5432 | N/A | Alembic migrations, pg_dump, admin CLI |
| Supavisor session mode | 5432 | Session | Long-lived connections, prepared statement support |
| Supavisor transaction mode | 6543 | Transaction | FastAPI app — serverless-style, high concurrency |

**Recommendation for this project:** Transaction mode (port 6543) + NullPool + disabled
prepared statements for the FastAPI application. Direct connection for Alembic only.

### Production Engine Configuration (The Correct Setup)

```python
# app/db/engine.py
import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool

# Two separate URLs — one for app, one for migrations
APP_DATABASE_URL = (
    f"postgresql+asyncpg://{os.environ['DB_USER']}:{os.environ['DB_PASS']}"
    f"@{os.environ['DB_HOST_POOLER']}:6543/{os.environ['DB_NAME']}"
)
MIGRATION_DATABASE_URL = (
    f"postgresql+asyncpg://{os.environ['DB_USER']}:{os.environ['DB_PASS']}"
    f"@{os.environ['DB_HOST_DIRECT']}:5432/{os.environ['DB_NAME']}"
)

engine = create_async_engine(
    APP_DATABASE_URL,
    poolclass=NullPool,           # Delegate pooling to Supavisor — do NOT use QueuePool here
    connect_args={
        "statement_cache_size": 0,           # Disable asyncpg statement cache
        "prepared_statement_cache_size": 0,  # Belt-and-suspenders — also disable this
        "server_settings": {"jit": "off"},   # Reduces edge-case JIT compilation failures
    },
    pool_pre_ping=True,           # Validate connection before use (catches stale connections)
    echo=os.environ.get("SQL_ECHO", "false").lower() == "true",
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
```

### Why NullPool for the App Engine?

With `NullPool`, SQLAlchemy opens a new connection from Supavisor for each request and
releases it immediately. This sounds wasteful but is correct because:

1. Supavisor (the external pooler) maintains the actual backend connections to PostgreSQL
2. SQLAlchemy's internal pool would compete with Supavisor's pool, doubling management
3. In transaction mode, each connection is returned to Supavisor after every transaction
   anyway, so SQLAlchemy holding it longer provides no benefit

### If Using QueuePool (Without NullPool)

If you have a reason to use SQLAlchemy's internal pool (e.g., connecting direct on port
5432), these are the production parameters:

```python
engine = create_async_engine(
    DIRECT_DATABASE_URL,  # port 5432 direct
    pool_size=10,          # Persistent connections in pool
    max_overflow=5,        # Additional connections during peak (total max: 15)
    pool_timeout=30,       # Wait up to 30s for a connection from pool
    pool_recycle=300,      # Recycle connections every 5 min (prevents Supabase idle timeout)
    pool_pre_ping=True,    # Health-check on checkout
)
```

Pool sizing formula: `pool_size = (number_of_workers * 2) + 1`
For Gunicorn with 4 workers: `pool_size=9`, `max_overflow=3`.

Supabase Nano tier allows 15–20 backend connections total. With 4 workers each holding
pool_size=9, you'd exceed the limit immediately. NullPool + Supavisor avoids this math.

### Separate URL Configuration for Alembic

```ini
# alembic.ini — uses DIRECT connection, not pooler
[alembic]
sqlalchemy.url = postgresql+asyncpg://%(DB_USER)s:%(DB_PASS)s@%(DB_HOST_DIRECT)s:5432/%(DB_NAME)s
```

Or in `env.py`, override via environment variable:

```python
# alembic/env.py
config.set_main_option(
    "sqlalchemy.url",
    os.environ["DIRECT_DATABASE_URL"]  # Always direct for migrations
)
```

### Connection Health Monitoring

```python
# app/api/routes/health.py
from sqlalchemy import text

@router.get("/health/db")
async def db_health(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"database": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database unavailable: {exc}")
```

---

## Implementation Checklist

### SQLAlchemy Async Setup
- [ ] Use `postgresql+asyncpg://` driver string
- [ ] Set `expire_on_commit=False` on session factory
- [ ] Use `async with AsyncSessionLocal() as session:` context manager everywhere
- [ ] Never share a session across request boundary into background tasks

### Alembic Configuration
- [ ] Import all models in `app/db/base.py` before `target_metadata = Base.metadata`
- [ ] Use `run_sync` bridge in `env.py` for async engine
- [ ] Use direct DB URL (port 5432) for Alembic, not the pooler
- [ ] Use ad-hoc table definitions in data migrations — never import live models

### Multi-Tenant (organization_id)
- [ ] Add `TenantMixin` to every tenant-scoped model
- [ ] Add `organization_id` index to every table (explicit, not just FK)
- [ ] Filter all queries by `organization_id` at the service layer
- [ ] Seed system-level data with a dedicated system organization UUID

### Background Tasks
- [ ] Create `import_jobs` table with JSONB `row_errors` column
- [ ] Read file bytes eagerly before handing to background task
- [ ] Create new `AsyncSession` inside the background task function
- [ ] Update job progress in DB after each batch (not each row)
- [ ] Cap stored `row_errors` to prevent unbounded JSONB growth

### Audit Events
- [ ] Create `audit_events` table with JSONB `payload` column
- [ ] Add immutability trigger via Alembic migration
- [ ] Add composite indexes: `(entity_type, entity_id, occurred_at)` and `(org_id, occurred_at)`
- [ ] Write audit events inside the same transaction as the business operation

### Connection Pooling
- [ ] Use `NullPool` + Supavisor transaction mode (port 6543) for the app
- [ ] Set `statement_cache_size=0` and `prepared_statement_cache_size=0` in `connect_args`
- [ ] Set `server_settings={"jit": "off"}` in `connect_args`
- [ ] Use direct connection (port 5432) for Alembic migrations
- [ ] Add `/health/db` endpoint

---

## Package Summary

| Package | Version | License | Downloads/wk | Status | Purpose |
|---|---|---|---|---|---|
| sqlalchemy | 2.x | MIT | 25M+ | APPROVED | ORM + async engine |
| asyncpg | 0.29+ | Apache-2.0 | 4M+ | APPROVED | PostgreSQL async driver |
| alembic | 1.13+ | MIT | 13M+ | APPROVED | Schema migrations |
| openpyxl | 3.1+ | MIT | 13M+ | APPROVED | XLSX parsing in imports |
| psycopg2-binary | 2.9+ | LGPL-3.0 | 10M+ | WARNING (devDep ok) | Sync driver for scripts/tests |

**Note on psycopg2-binary:** LGPL-3.0 is a WARNING status for runtime dependencies.
It is fine as a dev/test dependency. For the production app, asyncpg (Apache-2.0) is
the runtime driver.

---

## Research Gaps

1. **BackgroundTasks event loop interaction under Gunicorn multi-worker:** The research
   confirmed BackgroundTasks works correctly in single-worker Uvicorn. Behavior under
   Gunicorn with multiple workers is less documented — each worker runs its own event
   loop and its own background tasks independently. Cross-worker job visibility requires
   the database-backed `ImportJob` table (not in-memory state).

2. **Supabase Supavisor vs dedicated PgBouncer performance delta:** Multiple sources
   confirm the asyncpg compatibility fix (NullPool + cache disabled), but no benchmark
   data was found comparing Supavisor vs dedicated PgBouncer latency for a FastAPI
   workload. The Supabase docs indicate dedicated PgBouncer (paid tier) has lower
   latency due to co-location.

3. **Audit trigger + Supabase RLS interaction:** Supabase's Row Level Security (RLS)
   uses `SET SESSION ROLE` per-connection. In transaction mode pooling, session-level
   settings do not persist across transactions. If RLS is used alongside audit triggers,
   the trigger's `SECURITY DEFINER` must be tested to ensure it executes with the correct
   role context.

4. **XLSX parsing memory for large files:** openpyxl `read_only=True` was referenced as
   the low-memory approach for large files, but no benchmark was found for the specific
   row counts expected in this project. Files >50MB may need streaming parsing via
   `read_only=True` + early generator consumption to avoid holding the entire workbook
   in memory during async processing.

---

## Sources

- [Building a Production-Grade Async Backend with FastAPI, SQLAlchemy, PostgreSQL, and Alembic](https://dev.to/rosewabere/building-a-production-grade-async-backend-with-fastapi-sqlalchemy-postgresql-and-alembic-2ca4)
- [FastAPI Async vs Sync: Benchmark Results (Feb 2026)](https://medium.com/@kenancan.dev/fastapi-async-vs-sync-benchmark-results-2c5798bbdb16)
- [FastAPI with Async SQLAlchemy, SQLModel, and Alembic - TestDriven.io](https://testdriven.io/blog/fastapi-sqlmodel/)
- [Async SQLAlchemy Engine in FastAPI — The Guide](https://mjmichael.medium.com/async-sqlalchemy-engine-in-fastapi-the-guide-e5acdba75c99)
- [Building High-Performance Async APIs with FastAPI, SQLAlchemy 2.0, and Asyncpg](https://leapcell.io/blog/building-high-performance-async-apis-with-fastapi-sqlalchemy-2-0-and-asyncpg)
- [Patterns and Practices for using SQLAlchemy 2.0 with FastAPI](https://chaoticengineer.hashnode.dev/fastapi-sqlalchemy)
- [Alembic Cookbook — multi-tenant, async, bulk_insert](https://alembic.sqlalchemy.org/en/latest/cookbook.html)
- [How to run multi-tenant migrations in Alembic (Gist)](https://gist.github.com/nickretallack/bb8ca0e37829b4722dd1)
- [Schema-level multi-tenancy with one common schema — Alembic Discussion](https://github.com/sqlalchemy/alembic/discussions/1105)
- [Managing Background Tasks and Long-Running Operations in FastAPI](https://leapcell.io/blog/managing-background-tasks-and-long-running-operations-in-fastapi)
- [How to Build Background Task Processing in FastAPI (Jan 2026)](https://oneuptime.com/blog/post/2026-01-25-background-task-processing-fastapi/view)
- [Simple Background Job Management with FastAPI (with status) — Gist](https://gist.github.com/johnidm/789759fbcdbb7bd574fdbf5e6476012f)
- [Best practice for async DB session in background tasks — FastAPI Discussion #10897](https://github.com/fastapi/fastapi/discussions/10897)
- [PostgreSQL Trigger-Based Audit Log](https://medium.com/israeli-tech-radar/postgresql-trigger-based-audit-log-fd9d9d5e412c)
- [Using Database Triggers in SQLAlchemy — Atlas Guides](https://atlasgo.io/guides/orms/sqlalchemy/triggers)
- [SQLAlchemy PostgreSQL Audit — PyPI](https://pypi.org/project/sqlalchemy-postgresql-audit/)
- [Creating audit table to log changes in SQLAlchemy using events](https://medium.com/@singh.surbhicse/creating-audit-table-to-log-insert-update-and-delete-changes-in-flask-sqlalchemy-f2ca53f7b02f)
- [Connect to your database — Supabase Docs](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [Supabase Pooling and asyncpg Don't Mix — Here's the Real Fix](https://medium.com/@patrickduch93/supabase-pooling-and-asyncpg-dont-mix-here-s-the-real-fix-44f700b05249)
- [Python asyncpg fails with burst requests on both Supabase poolers — Issue #39227](https://github.com/supabase/supabase/issues/39227)
- [Supabase Connection Scaling: The Essential Guide for FastAPI Developers](https://dev.to/papansarkar101/supabase-connection-scaling-the-essential-guide-for-fastapi-developers-348o)
- [Connection Pooling — SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/core/pooling.html)
- [A Gentleman's Guide to PostgreSQL Connection Pooling](https://goldlapel.com/how-to/connection-pooling)
- [Supavisor — cloud-native multi-tenant Postgres connection pooler](https://github.com/supabase/supavisor)
- [Asynchronous I/O (asyncio) — SQLAlchemy 2.0 Documentation](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
