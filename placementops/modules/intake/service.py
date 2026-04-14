# @forgeplan-node: intake-module
"""
Intake service layer — all database operations for patient case intake.

Handles case creation, PATCH, list, detail, mark-intake-complete, assign,
status-transition, import job lifecycle, duplicate detection, and intake
field issue management.

CRITICAL constraints implemented here:
  - File bytes are passed as `bytes` to run_commit — UploadFile is NEVER accessed here.
  - BackgroundTask functions open a FRESH AsyncSessionLocal — never reuse the request session.
  - Import progress persisted every 50 rows (not per-row).
  - openpyxl uses read_only=True and runs in loop.run_in_executor().
  - ZIP bomb detection occurs before any spreadsheet parsing.
"""
# @forgeplan-decision: D-intake-2-file-bytes-in-memory -- file_bytes passed in-memory to BackgroundTask, not persisted to DB. Why: ImportJob has no file_bytes column; spec pattern shows bytes passed as task argument; avoids adding large binary to ImportJob table
# @forgeplan-decision: D-intake-3-required-intake-fields -- Required fields for mark-intake-complete: patient_name, hospital_id, hospital_unit, room_number, admission_date, primary_diagnosis_text, insurance_primary. Why: minimum fields needed for clinical review; inferred from intake domain since spec does not enumerate them
# @forgeplan-decision: D-intake-4-resolved-flag-true -- resolved_flag=True means issue is resolved. Why: "resolved" semantics; set to True when field re-submitted with valid value per AC15

from __future__ import annotations

import asyncio
import csv
import io
import logging
import zipfile
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.audit import emit_audit_event
from placementops.core.database import AsyncSessionLocal
from placementops.core.models import (
    CaseStatusHistory,
    ImportJob,
    PatientCase,
    User,
)
from placementops.core.state_machine import transition_case_status
from placementops.modules.intake.models import CaseAssignment, IntakeFieldIssue
from placementops.modules.intake.schemas import (
    CaseCreateRequest,
    CasePatchRequest,
    ColumnMappingRequest,
    DuplicateWarning,
    PatientCaseSummary,
    RowValidationResult,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Statuses where a case is still considered "active" (for duplicate detection)
TERMINAL_STATUSES: frozenset[str] = frozenset({"placed", "closed", "declined_final"})

# Required fields for mark-intake-complete (AC5)
REQUIRED_INTAKE_FIELDS: list[str] = [
    "patient_name",
    "hospital_id",
    "hospital_unit",
    "room_number",
    "admission_date",
    "primary_diagnosis_text",
    "insurance_primary",
]

# Role-based field allowlists for PATCH (AC4)
INTAKE_STAFF_FIELDS: frozenset[str] = frozenset({
    "hospital_unit",
    "room_number",
    "admission_date",
    "primary_diagnosis_text",
    "insurance_primary",
    "insurance_secondary",
    "patient_zip",
    "patient_phone",
    "preferred_geography_text",
    "discharge_target_date",
    "priority_level",
})

PLACEMENT_COORDINATOR_FIELDS: frozenset[str] = frozenset({
    "priority_level",
    "patient_phone",
    "assigned_coordinator_user_id",
})

# Maximum upload size: 10 MB
MAX_UPLOAD_BYTES: int = 10 * 1024 * 1024

# Accepted content types for file import
ACCEPTED_CONTENT_TYPES: frozenset[str] = frozenset({
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv",
})

# Progress flush interval (rows)
PROGRESS_FLUSH_INTERVAL: int = 50

# ---------------------------------------------------------------------------
# ZIP bomb detection
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC8
def check_zip_bomb(
    data: bytes,
    max_ratio: float = 100.0,
    max_uncompressed: int = 100 * 1024 * 1024,
) -> None:
    """
    Check for ZIP bombs in XLSX files before any spreadsheet parsing.

    XLSX files are ZIP archives (magic bytes PK). CSV files are not ZIP
    archives and are skipped.

    Raises ValueError if a ZIP bomb is detected.
    """
    # CSV is not a zip archive — skip check
    if not data[:2] == b"PK":
        return

    try:
        zf_ctx = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("Invalid or corrupt ZIP/XLSX file") from exc

    with zf_ctx as zf:
        total_compressed = sum(i.compress_size for i in zf.infolist())
        total_uncompressed = sum(i.file_size for i in zf.infolist())

        if total_compressed > 0 and total_uncompressed / total_compressed > max_ratio:
            raise ValueError("ZIP bomb detected: decompression ratio exceeds limit")

        if total_uncompressed > max_uncompressed:
            raise ValueError(
                f"ZIP bomb detected: decompressed size {total_uncompressed} exceeds limit {max_uncompressed}"
            )


# ---------------------------------------------------------------------------
# openpyxl parsing (in executor)
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC10
async def parse_rows_async(file_bytes: bytes) -> list[tuple]:
    """
    Parse XLSX file bytes into rows using openpyxl read_only=True.

    Runs in a thread executor to avoid blocking the event loop.
    Returns a list of tuples (one per row), first row is headers.
    """
    loop = asyncio.get_running_loop()

    def _parse() -> list[tuple]:
        try:
            import openpyxl  # noqa: PLC0415
        except ImportError as exc:
            raise RuntimeError(
                "openpyxl is required for XLSX parsing. "
                "Add openpyxl to requirements.txt."
            ) from exc

        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        wb.close()
        return rows

    return await loop.run_in_executor(None, _parse)


def parse_csv_rows(file_bytes: bytes) -> list[tuple]:
    """Parse CSV file bytes into rows (synchronous — CSV is not memory-intensive)."""
    text = file_bytes.decode("utf-8-sig")  # handle BOM
    reader = csv.reader(io.StringIO(text))
    return [tuple(row) for row in reader]


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC14
async def detect_duplicate(
    session: AsyncSession,
    organization_id: UUID,
    patient_name: str,
    dob: Any,
    hospital_id: UUID,
    exclude_case_id: str | None = None,
) -> PatientCase | None:
    """
    Return an existing active case matching patient_name + dob + hospital_id, or None.

    Active means NOT in terminal statuses (placed, closed, declined_final).
    """
    stmt = select(PatientCase).where(
        and_(
            PatientCase.organization_id == str(organization_id),
            PatientCase.patient_name == patient_name,
            PatientCase.hospital_id == str(hospital_id),
            PatientCase.current_status.not_in(list(TERMINAL_STATUSES)),
            PatientCase.active_case_flag == True,  # noqa: E712
        )
    )
    if dob is not None:
        stmt = stmt.where(PatientCase.dob == dob)
    if exclude_case_id:
        stmt = stmt.where(PatientCase.id != exclude_case_id)

    result = await session.execute(stmt)
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Intake field issue management
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC15
async def create_intake_field_issue(
    session: AsyncSession,
    patient_case_id: str,
    field_name: str,
    issue_description: str,
) -> IntakeFieldIssue:
    """Create a new IntakeFieldIssue for a validation failure."""
    issue = IntakeFieldIssue(
        patient_case_id=patient_case_id,
        field_name=field_name,
        issue_description=issue_description,
        resolved_flag=False,
    )
    session.add(issue)
    return issue


# @forgeplan-spec: AC15
async def resolve_intake_field_issues(
    session: AsyncSession,
    patient_case_id: str,
    field_name: str,
) -> None:
    """Mark all unresolved issues for a field as resolved (resolved_flag=True)."""
    result = await session.execute(
        select(IntakeFieldIssue).where(
            and_(
                IntakeFieldIssue.patient_case_id == patient_case_id,
                IntakeFieldIssue.field_name == field_name,
                IntakeFieldIssue.resolved_flag == False,  # noqa: E712
            )
        )
    )
    issues = result.scalars().all()
    for issue in issues:
        issue.resolved_flag = True


# ---------------------------------------------------------------------------
# Case creation
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC1
# @forgeplan-spec: AC14
# @forgeplan-spec: AC16
async def create_case(
    session: AsyncSession,
    payload: CaseCreateRequest,
    organization_id: UUID,
    created_by_user_id: UUID,
    actor_role: str,
) -> tuple[PatientCase, DuplicateWarning | None]:
    """
    Create a new PatientCase.

    Steps:
    1. Duplicate detection — return DuplicateWarning if match found
    2. Create PatientCase with status=new
    3. Flush to get case.id
    4. Write CaseStatusHistory row (from_status=None, to_status="new")
    5. Write AuditEvent for case_created
    6. Commit
    7. Transition new → intake_in_progress (transition_case_status handles its own commit)
    8. Publish CaseActivityEvent

    Returns (case, duplicate_warning_or_None).
    """
    # Step 1: Duplicate detection
    duplicate_warning: DuplicateWarning | None = None
    if payload.dob or payload.patient_name:
        existing = await detect_duplicate(
            session=session,
            organization_id=organization_id,
            patient_name=payload.patient_name,
            dob=payload.dob,
            hospital_id=payload.hospital_id,
        )
        if existing is not None:
            duplicate_warning = DuplicateWarning(
                existing_case_id=UUID(existing.id),
                patient_name=existing.patient_name,
                dob=existing.dob,
                hospital_id=UUID(existing.hospital_id) if existing.hospital_id else payload.hospital_id,
                current_status=existing.current_status,
            )

    # Step 2: Create PatientCase with status=new
    case = PatientCase(
        organization_id=str(organization_id),
        hospital_id=str(payload.hospital_id),
        patient_name=payload.patient_name,
        dob=payload.dob,
        mrn=payload.mrn,
        hospital_unit=payload.hospital_unit,
        room_number=payload.room_number,
        admission_date=payload.admission_date,
        primary_diagnosis_text=payload.primary_diagnosis_text,
        insurance_primary=payload.insurance_primary,
        insurance_secondary=payload.insurance_secondary,
        patient_zip=payload.patient_zip,
        preferred_geography_text=payload.preferred_geography_text,
        discharge_target_date=payload.discharge_target_date,
        priority_level=payload.priority_level,
        current_status="new",
        created_by_user_id=str(created_by_user_id),
        updated_by_user_id=str(created_by_user_id),
    )
    session.add(case)

    # Step 3: Flush to get case.id (assigned by DB default)
    await session.flush()

    # Step 4: Write initial CaseStatusHistory row (from_status=None → new)
    history_initial = CaseStatusHistory(
        organization_id=str(organization_id),
        patient_case_id=case.id,
        from_status=None,
        to_status="new",
        actor_user_id=str(created_by_user_id),
        transition_reason="Case created",
    )
    session.add(history_initial)

    # Step 5: Write AuditEvent for case_created (no PHI in payload)
    await emit_audit_event(
        session=session,
        organization_id=organization_id,
        entity_type="patient_case",
        entity_id=UUID(case.id),
        event_type="case_created",
        actor_user_id=created_by_user_id,
        old_value=None,
        new_value={"status": "new"},
    )

    # Step 6: Commit
    await session.commit()

    # Step 7: Transition new → intake_in_progress
    # transition_case_status handles its own commit and CaseStatusHistory row
    case = await transition_case_status(
        case_id=UUID(case.id),
        to_status="intake_in_progress",
        actor_role=actor_role,
        actor_user_id=created_by_user_id,
        session=session,
        transition_reason="Auto-advance on case creation",
        organization_id=organization_id,
    )

    return case, duplicate_warning


# ---------------------------------------------------------------------------
# Case list
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC2
async def list_cases(
    session: AsyncSession,
    organization_id: UUID,
    status_filter: str | None = None,
    hospital_id: str | None = None,
    assigned_user_id: str | None = None,
    priority_level: str | None = None,
    search: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[PatientCase], int]:
    """
    Return paginated list of cases with optional filters.

    Returns (cases, total_count).
    """
    stmt = select(PatientCase).where(
        PatientCase.organization_id == str(organization_id)
    )

    if status_filter:
        stmt = stmt.where(PatientCase.current_status == status_filter)
    if hospital_id:
        stmt = stmt.where(PatientCase.hospital_id == hospital_id)
    if assigned_user_id:
        stmt = stmt.where(
            PatientCase.assigned_coordinator_user_id == assigned_user_id
        )
    if priority_level:
        stmt = stmt.where(PatientCase.priority_level == priority_level)
    if search:
        # Free-text search on patient_name — escape LIKE metacharacters to prevent wildcard injection
        search_safe = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(
            PatientCase.patient_name.ilike(f"%{search_safe}%", escape="\\")
        )

    # Count total (without pagination)
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await session.execute(count_stmt)
    total = total_result.scalar_one()

    # Apply pagination
    offset = (page - 1) * page_size
    stmt = stmt.order_by(PatientCase.created_at.desc()).offset(offset).limit(page_size)
    result = await session.execute(stmt)
    cases = list(result.scalars().all())

    return cases, total


# ---------------------------------------------------------------------------
# Case detail
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC3
async def get_case_detail(
    session: AsyncSession,
    case_id: UUID,
    organization_id: UUID,
) -> tuple[PatientCase, list[IntakeFieldIssue]]:
    """
    Return a case and its intake_field_issues.

    Raises HTTP 404 if case not found or wrong org.
    """
    result = await session.execute(
        select(PatientCase).where(
            and_(
                PatientCase.id == str(case_id),
                PatientCase.organization_id == str(organization_id),
            )
        )
    )
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case {case_id} not found",
        )

    issues_result = await session.execute(
        select(IntakeFieldIssue).where(
            IntakeFieldIssue.patient_case_id == str(case_id)
        )
    )
    issues = list(issues_result.scalars().all())
    return case, issues


# ---------------------------------------------------------------------------
# Case PATCH
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC4
async def patch_case(
    session: AsyncSession,
    case_id: UUID,
    organization_id: UUID,
    payload: CasePatchRequest,
    actor_role: str,
    actor_user_id: UUID,
) -> PatientCase:
    """
    Apply a partial update to a PatientCase, enforcing role-based field allowlists.

    intake_staff: may update intake fields only
    placement_coordinator: may update priority_level and assigned_coordinator_user_id
    Other roles: 403

    updated_by_user_id is always set.
    """
    # Determine allowed fields for this role
    if actor_role in ("admin",):
        allowed_fields = INTAKE_STAFF_FIELDS | PLACEMENT_COORDINATOR_FIELDS
    elif actor_role == "intake_staff":
        allowed_fields = INTAKE_STAFF_FIELDS
    elif actor_role == "placement_coordinator":
        allowed_fields = PLACEMENT_COORDINATOR_FIELDS
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{actor_role}' is not permitted to update cases",
        )

    # Get submitted fields (non-None values from payload)
    submitted_fields = {
        k for k, v in payload.model_dump(exclude_unset=True).items() if v is not None
    }

    # Check for disallowed fields
    disallowed = submitted_fields - allowed_fields
    if disallowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{actor_role}' cannot update fields: {sorted(disallowed)}",
        )

    # Fetch case
    result = await session.execute(
        select(PatientCase).where(
            and_(
                PatientCase.id == str(case_id),
                PatientCase.organization_id == str(organization_id),
            )
        )
    )
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case {case_id} not found",
        )

    # Guard: closed/placed cases are immutable
    if case.current_status in ("placed", "closed"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot modify case in terminal status '{case.current_status}'",
        )

    # Apply updates
    update_data = payload.model_dump(exclude_unset=True)
    old_values: dict[str, Any] = {}

    # Fields that are required for mark-intake-complete (AC15 tracking scope)
    _required_patchable = frozenset(REQUIRED_INTAKE_FIELDS) & INTAKE_STAFF_FIELDS

    for field_name, new_val in update_data.items():
        if field_name not in allowed_fields:
            continue
        old_values[field_name] = getattr(case, field_name, None)

        if field_name == "assigned_coordinator_user_id" and new_val is not None:
            setattr(case, field_name, str(new_val))
        elif new_val is not None:
            setattr(case, field_name, new_val)
        else:
            setattr(case, field_name, None)

        # AC15: Track field issues for required fields
        if field_name in _required_patchable:
            is_empty = new_val is None or (isinstance(new_val, str) and not new_val.strip())
            if is_empty:
                # Clearing a required field — create an issue
                await create_intake_field_issue(
                    session,
                    case.id,
                    field_name,
                    f"Field '{field_name}' is required for intake completion but was cleared.",
                )
            else:
                # Valid value submitted — resolve any open issues for this field
                await resolve_intake_field_issues(session, case.id, field_name)
        elif field_name in submitted_fields:
            # Non-required field: resolve any lingering issues
            await resolve_intake_field_issues(session, case.id, field_name)

    # Always set updated_by_user_id
    case.updated_by_user_id = str(actor_user_id)

    # Emit audit event (no PHI values)
    safe_fields = {k: v for k, v in update_data.items() if k not in ("patient_name", "dob", "mrn")}
    await emit_audit_event(
        session=session,
        organization_id=organization_id,
        entity_type="patient_case",
        entity_id=case_id,
        event_type="case_updated",
        actor_user_id=actor_user_id,
        old_value=None,
        new_value={"updated_fields": list(safe_fields.keys())},
    )

    await session.commit()
    await session.refresh(case)
    return case


# ---------------------------------------------------------------------------
# Mark intake complete
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC5
async def mark_intake_complete(
    session: AsyncSession,
    case_id: UUID,
    organization_id: UUID,
    actor_role: str,
    actor_user_id: UUID,
) -> PatientCase:
    """
    Mark a case's intake as complete.

    Steps:
    1. Load case
    2. Validate required fields — 422 if any missing
    3. Transition intake_in_progress → intake_complete (transition_case_status)
    4. Transition intake_complete → needs_clinical_review (transition_case_status)
    5. Set intake_complete=True, updated_by_user_id

    Writes two CaseStatusHistory rows (one per transition).
    """
    # Load case (no FOR UPDATE — transition_case_status will lock)
    result = await session.execute(
        select(PatientCase).where(
            and_(
                PatientCase.id == str(case_id),
                PatientCase.organization_id == str(organization_id),
            )
        )
    )
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case {case_id} not found",
        )

    if case.current_status != "intake_in_progress":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Case must be in intake_in_progress to mark complete; current status: {case.current_status}",
        )

    # Validate required fields
    missing_fields: list[str] = []
    for field_name in REQUIRED_INTAKE_FIELDS:
        val = getattr(case, field_name, None)
        if val is None or (isinstance(val, str) and not val.strip()):
            missing_fields.append(field_name)

    if missing_fields:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": "missing_required_fields",
                "message": "The following required fields are missing or empty",
                "missing_fields": missing_fields,
            },
        )

    # Transition 1: intake_in_progress → intake_complete
    case = await transition_case_status(
        case_id=case_id,
        to_status="intake_complete",
        actor_role=actor_role,
        actor_user_id=actor_user_id,
        session=session,
        transition_reason="Intake marked complete by staff",
        organization_id=organization_id,
    )

    # Transition 2: intake_complete → needs_clinical_review
    case = await transition_case_status(
        case_id=case_id,
        to_status="needs_clinical_review",
        actor_role=actor_role,
        actor_user_id=actor_user_id,
        session=session,
        transition_reason="Auto-advance after intake complete",
        organization_id=organization_id,
    )

    # Set intake_complete flag on the returned case object
    # transition_case_status already committed; the session is still active
    case.intake_complete = True
    case.updated_by_user_id = str(actor_user_id)
    await session.commit()

    return case


# ---------------------------------------------------------------------------
# Case assignment
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC6
async def assign_case(
    session: AsyncSession,
    case_id: UUID,
    organization_id: UUID,
    assigned_user_id: UUID,
    assigned_role: str,
    assigned_by_user_id: UUID,
) -> CaseAssignment:
    """
    Record a case assignment.

    If the assigned user has role placement_coordinator, also sets
    PatientCase.assigned_coordinator_user_id (denormalized for queue performance).
    """
    # Verify case exists
    result = await session.execute(
        select(PatientCase).where(
            and_(
                PatientCase.id == str(case_id),
                PatientCase.organization_id == str(organization_id),
            )
        )
    )
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case {case_id} not found",
        )

    # Verify assigned user exists within the same organization (prevents cross-org assignment)
    user_result = await session.execute(
        select(User).where(
            and_(
                User.id == str(assigned_user_id),
                User.organization_id == str(organization_id),
            )
        )
    )
    assigned_user = user_result.scalar_one_or_none()
    if assigned_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {assigned_user_id} not found in this organization",
        )

    # Record assignment
    assignment = CaseAssignment(
        patient_case_id=str(case_id),
        assigned_user_id=str(assigned_user_id),
        assigned_role=assigned_role,
        assigned_by_user_id=str(assigned_by_user_id),
    )
    session.add(assignment)

    # Update denormalized coordinator field if applicable
    if assigned_user.role_key == "placement_coordinator":
        case.assigned_coordinator_user_id = str(assigned_user_id)
        case.updated_by_user_id = str(assigned_by_user_id)

    await emit_audit_event(
        session=session,
        organization_id=organization_id,
        entity_type="patient_case",
        entity_id=case_id,
        event_type="case_assigned",
        actor_user_id=assigned_by_user_id,
        old_value=None,
        new_value={"assigned_role": assigned_role},
    )

    await session.commit()
    return assignment


# ---------------------------------------------------------------------------
# Status transition (delegating to state_machine)
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC7
async def status_transition(
    session: AsyncSession,
    case_id: UUID,
    organization_id: UUID,
    to_status: str,
    actor_role: str,
    actor_user_id: UUID,
    transition_reason: str | None = None,
) -> PatientCase:
    """
    Delegate status transition to core state_machine.

    Returns updated PatientCase.
    Raises 400 for invalid transitions, 403 for wrong role.
    """
    # Verify org membership (defense-in-depth)
    result = await session.execute(
        select(PatientCase).where(
            and_(
                PatientCase.id == str(case_id),
                PatientCase.organization_id == str(organization_id),
            )
        )
    )
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case {case_id} not found",
        )

    return await transition_case_status(
        case_id=case_id,
        to_status=to_status,
        actor_role=actor_role,
        actor_user_id=actor_user_id,
        session=session,
        transition_reason=transition_reason,
        organization_id=organization_id,
    )


# ---------------------------------------------------------------------------
# Import job creation
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC8
async def create_import_job(
    session: AsyncSession,
    organization_id: UUID,
    created_by_user_id: UUID,
    file_name: str,
    file_size_bytes: int,
) -> ImportJob:
    """
    Create an ImportJob with status=uploaded and commit it to DB.

    The ImportJob MUST be in the DB before the endpoint returns.
    """
    job = ImportJob(
        organization_id=str(organization_id),
        created_by_user_id=str(created_by_user_id),
        file_name=file_name,
        file_size_bytes=file_size_bytes,
        status="uploaded",
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)
    return job


# ---------------------------------------------------------------------------
# Map columns
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC9
async def map_import_columns(
    session: AsyncSession,
    import_job_id: UUID,
    organization_id: UUID,
    mapping: ColumnMappingRequest,
) -> ImportJob:
    """
    Save column_mapping_json and advance ImportJob to status=mapping.
    """
    result = await session.execute(
        select(ImportJob).where(
            and_(
                ImportJob.id == str(import_job_id),
                ImportJob.organization_id == str(organization_id),
            )
        )
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ImportJob {import_job_id} not found",
        )

    job.column_mapping_json = {
        "mappings": [m.model_dump() for m in mapping.mappings]
    }
    job.status = "mapping"
    await session.commit()
    await session.refresh(job)
    return job


# ---------------------------------------------------------------------------
# Validate import (dry-run)
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC10
async def validate_import(
    session: AsyncSession,
    import_job_id: UUID,
    organization_id: UUID,
    file_bytes: bytes,
    content_type: str,
) -> tuple[ImportJob, list[RowValidationResult]]:
    """
    Dry-run validate all rows using openpyxl read_only=True in executor.

    Advances ImportJob to status=ready.
    Returns (job, row_results).
    """
    result = await session.execute(
        select(ImportJob).where(
            and_(
                ImportJob.id == str(import_job_id),
                ImportJob.organization_id == str(organization_id),
            )
        )
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ImportJob {import_job_id} not found",
        )

    if job.column_mapping_json is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Column mapping must be set before validation",
        )

    # Parse rows
    if content_type == "text/csv":
        raw_rows = parse_csv_rows(file_bytes)
    else:
        raw_rows = await parse_rows_async(file_bytes)

    if not raw_rows:
        job.status = "ready"
        job.total_rows = 0
        await session.commit()
        await session.refresh(job)
        return job, []

    # First row is header
    headers = [str(h).strip() if h is not None else "" for h in raw_rows[0]]
    data_rows = raw_rows[1:]

    # Build mapping: source_column → destination_field
    mappings = job.column_mapping_json.get("mappings", [])
    col_map: dict[str, str] = {
        m["source_column"]: m["destination_field"]
        for m in mappings
    }

    row_results: list[RowValidationResult] = []
    for idx, row in enumerate(data_rows, start=2):
        row_dict = {
            col_map.get(headers[i], headers[i]): (row[i] if i < len(row) else None)
            for i in range(len(headers))
        }
        errors = _validate_row(row_dict)
        row_results.append(
            RowValidationResult(
                row_number=idx,
                is_valid=len(errors) == 0,
                errors=errors,
            )
        )

    job.total_rows = len(data_rows)
    job.status = "ready"
    await session.commit()
    await session.refresh(job)
    return job, row_results


def _validate_row(row_dict: dict[str, Any]) -> list[str]:
    """Validate a single row dict. Returns list of error messages."""
    errors: list[str] = []
    if not row_dict.get("patient_name"):
        errors.append("patient_name is required")
    if not row_dict.get("hospital_id"):
        errors.append("hospital_id is required")
    return errors


# ---------------------------------------------------------------------------
# Commit import (background task)
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC11
async def run_commit(
    import_job_id: str,
    organization_id: str,
    created_by_user_id: str,
    file_bytes: bytes,
    content_type: str,
    column_mapping_json: dict,
) -> None:
    """
    Background task: commit import rows into PatientCase records.

    CRITICAL: Opens a FRESH AsyncSessionLocal — never reuses the request session.
    Progress persisted every 50 rows.
    Per-row errors stored in error_detail_json.
    """
    # @forgeplan-decision: D-intake-5-fresh-session-background -- Opens fresh AsyncSessionLocal in background task. Why: request session is closed before background task runs; reusing it causes DetachedInstanceError on every write
    async with AsyncSessionLocal() as db:
        # Mark job as committing
        result = await db.execute(
            select(ImportJob).where(ImportJob.id == import_job_id)
        )
        job = result.scalar_one_or_none()
        if job is None:
            logger.error("ImportJob %s not found in background task", import_job_id)
            return

        job.status = "committing"
        await db.commit()

        # Parse rows
        try:
            if content_type == "text/csv":
                raw_rows = parse_csv_rows(file_bytes)
            else:
                raw_rows = await parse_rows_async(file_bytes)
        except Exception as exc:
            logger.exception("Import %s parse failed", import_job_id)
            result2 = await db.execute(
                select(ImportJob).where(ImportJob.id == import_job_id)
            )
            job2 = result2.scalar_one()
            job2.status = "failed"
            job2.error_detail_json = {"error": str(exc)}
            await db.commit()
            return

        if not raw_rows:
            result3 = await db.execute(
                select(ImportJob).where(ImportJob.id == import_job_id)
            )
            job3 = result3.scalar_one()
            job3.status = "complete"
            job3.total_rows = 0
            await db.commit()
            return

        headers = [str(h).strip() if h is not None else "" for h in raw_rows[0]]
        data_rows = raw_rows[1:]

        mappings = column_mapping_json.get("mappings", [])
        col_map: dict[str, str] = {
            m["source_column"]: m["destination_field"]
            for m in mappings
        }

        created_count = 0
        updated_count = 0
        failed_count = 0
        error_details: dict[str, Any] = {}
        total_rows = len(data_rows)

        for idx, row in enumerate(data_rows):
            row_num = idx + 2  # 1-indexed, skip header
            row_dict = {
                col_map.get(headers[i], headers[i]): (row[i] if i < len(row) else None)
                for i in range(len(headers))
            }

            try:
                await _process_import_row(
                    db=db,
                    row_dict=row_dict,
                    organization_id=organization_id,
                    created_by_user_id=created_by_user_id,
                )
                created_count += 1
            except Exception as exc:
                logger.warning("Import row %d failed: %s", row_num, exc)
                failed_count += 1
                error_details[str(row_num)] = str(exc)

            # Flush progress every 50 rows
            if (idx + 1) % PROGRESS_FLUSH_INTERVAL == 0:
                progress_result = await db.execute(
                    select(ImportJob).where(ImportJob.id == import_job_id)
                )
                progress_job = progress_result.scalar_one()
                progress_job.created_count = created_count
                progress_job.updated_count = updated_count
                progress_job.failed_count = failed_count
                await db.commit()

        # Final update
        final_result = await db.execute(
            select(ImportJob).where(ImportJob.id == import_job_id)
        )
        final_job = final_result.scalar_one()
        final_job.status = "complete"
        final_job.total_rows = total_rows
        final_job.created_count = created_count
        final_job.updated_count = updated_count
        final_job.failed_count = failed_count
        if error_details:
            final_job.error_detail_json = {"errors": error_details}
        await db.commit()

        logger.info(
            "Import %s complete: created=%d, updated=%d, failed=%d",
            import_job_id, created_count, updated_count, failed_count,
        )


async def _process_import_row(
    db: AsyncSession,
    row_dict: dict[str, Any],
    organization_id: str,
    created_by_user_id: str,
) -> None:
    """
    Create or update a PatientCase from a single import row.

    Raises ValueError if required fields are missing.
    """
    patient_name = row_dict.get("patient_name")
    hospital_id = row_dict.get("hospital_id")

    if not patient_name:
        raise ValueError("patient_name is required")
    if not hospital_id:
        raise ValueError("hospital_id is required")

    case = PatientCase(
        organization_id=organization_id,
        hospital_id=str(hospital_id),
        patient_name=str(patient_name),
        dob=row_dict.get("dob"),
        mrn=row_dict.get("mrn"),
        hospital_unit=row_dict.get("hospital_unit"),
        room_number=row_dict.get("room_number"),
        primary_diagnosis_text=row_dict.get("primary_diagnosis_text"),
        insurance_primary=row_dict.get("insurance_primary"),
        insurance_secondary=row_dict.get("insurance_secondary"),
        patient_zip=row_dict.get("patient_zip"),
        current_status="intake_in_progress",
        created_by_user_id=created_by_user_id,
        updated_by_user_id=created_by_user_id,
    )
    db.add(case)
    await db.flush()


# ---------------------------------------------------------------------------
# Get import job
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC12
async def get_import_job(
    session: AsyncSession,
    import_job_id: UUID,
    organization_id: UUID,
) -> ImportJob:
    """Return ImportJob by ID."""
    result = await session.execute(
        select(ImportJob).where(
            and_(
                ImportJob.id == str(import_job_id),
                ImportJob.organization_id == str(organization_id),
            )
        )
    )
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"ImportJob {import_job_id} not found",
        )
    return job


# ---------------------------------------------------------------------------
# Intake queue
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC13
async def get_intake_queue(
    session: AsyncSession,
    organization_id: UUID,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[PatientCase], int]:
    """
    Return cases in intake_in_progress status for the intake queue.
    """
    stmt = select(PatientCase).where(
        and_(
            PatientCase.organization_id == str(organization_id),
            PatientCase.current_status == "intake_in_progress",
            PatientCase.active_case_flag == True,  # noqa: E712
        )
    )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await session.execute(count_stmt)
    total = total_result.scalar_one()

    offset = (page - 1) * page_size
    stmt = stmt.order_by(PatientCase.created_at.desc()).offset(offset).limit(page_size)
    result = await session.execute(stmt)
    cases = list(result.scalars().all())

    return cases, total
