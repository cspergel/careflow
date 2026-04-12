# @forgeplan-node: intake-module
"""
Intake module FastAPI router.

All endpoints under /api/v1/cases and /api/v1/imports and /api/v1/queues/intake.

Role enforcement:
  - POST /cases, POST /cases/{id}/mark-intake-complete: intake_staff + admin only (AC16)
  - PATCH /cases/{id}: intake_staff + placement_coordinator (role-field allowlist in service)
  - POST /cases/{id}/assign: any role with write permission (AC6)
  - GET endpoints: any authenticated user
  - POST /imports: any authenticated user with write permission
"""
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
# @forgeplan-spec: AC16

from __future__ import annotations

from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.auth import AuthContext, get_auth_context
from placementops.core.database import get_db
from placementops.modules.auth.dependencies import require_role, require_write_permission
from placementops.modules.intake import service
from placementops.modules.intake.schemas import (
    AssignCaseRequest,
    AssignCaseResponse,
    ColumnMappingRequest,
    CreateCaseResponse,
    CaseCreateRequest,
    CasePatchRequest,
    ImportJobResponse,
    IntakeQueueResponse,
    MarkIntakeCompleteResponse,
    PaginatedCasesResponse,
    PatientCaseDetail,
    PatientCaseSummary,
    StatusTransitionRequest,
    ValidateImportResponse,
    IntakeFieldIssueResponse,
)

router = APIRouter(tags=["intake"])

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACCEPTED_CONTENT_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv",
}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


# ---------------------------------------------------------------------------
# Case endpoints
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC1
# @forgeplan-spec: AC14
# @forgeplan-spec: AC16
@router.post(
    "/cases",
    status_code=status.HTTP_201_CREATED,
    response_model=CreateCaseResponse,
    dependencies=[
        require_role("intake_staff", "admin"),
        require_write_permission,
    ],
)
async def create_case(
    payload: CaseCreateRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> CreateCaseResponse:
    """
    Create a new PatientCase.

    Status auto-advances: new → intake_in_progress on creation.
    Includes duplicate detection — returns DuplicateWarning if match found.
    Restricted to intake_staff and admin roles.
    """
    case, duplicate_warning = await service.create_case(
        session=db,
        payload=payload,
        organization_id=auth.organization_id,
        created_by_user_id=auth.user_id,
        actor_role=auth.role_key,
    )

    case_summary = PatientCaseSummary.model_validate(case)
    return CreateCaseResponse(
        case=case_summary,
        duplicate_warning=duplicate_warning,
    )


# @forgeplan-spec: AC2
@router.get(
    "/cases",
    response_model=PaginatedCasesResponse,
)
async def list_cases(
    status_filter: str | None = Query(default=None, alias="status"),
    hospital_id: str | None = Query(default=None),
    assigned_user_id: str | None = Query(default=None),
    priority_level: str | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> PaginatedCasesResponse:
    """
    Return paginated list of cases with optional filters.

    Filters: status, hospital_id, assigned_user_id, priority_level, search (patient name).
    """
    cases, total = await service.list_cases(
        session=db,
        organization_id=auth.organization_id,
        status_filter=status_filter,
        hospital_id=hospital_id,
        assigned_user_id=assigned_user_id,
        priority_level=priority_level,
        search=search,
        page=page,
        page_size=page_size,
    )
    return PaginatedCasesResponse(
        cases=[PatientCaseSummary.model_validate(c) for c in cases],
        total=total,
        page=page,
        page_size=page_size,
    )


# @forgeplan-spec: AC3
@router.get(
    "/cases/{case_id}",
    response_model=PatientCaseDetail,
)
async def get_case(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> PatientCaseDetail:
    """Return full case detail including all intake_field_issues."""
    case, issues = await service.get_case_detail(
        session=db,
        case_id=case_id,
        organization_id=auth.organization_id,
    )
    detail = PatientCaseDetail.model_validate(case)
    detail.intake_field_issues = [
        IntakeFieldIssueResponse.model_validate(i) for i in issues
    ]
    return detail


# @forgeplan-spec: AC4
@router.patch(
    "/cases/{case_id}",
    response_model=PatientCaseSummary,
    dependencies=[require_write_permission],
)
async def patch_case(
    case_id: UUID,
    payload: CasePatchRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> PatientCaseSummary:
    """
    Partial update of a case.

    Role-based field allowlists enforced server-side:
      - intake_staff: intake fields only
      - placement_coordinator: priority_level and assigned_coordinator_user_id only
      - admin: all fields above
      - Other roles: 403
    """
    case = await service.patch_case(
        session=db,
        case_id=case_id,
        organization_id=auth.organization_id,
        payload=payload,
        actor_role=auth.role_key,
        actor_user_id=auth.user_id,
    )
    return PatientCaseSummary.model_validate(case)


# @forgeplan-spec: AC5
# @forgeplan-spec: AC16
@router.post(
    "/cases/{case_id}/mark-intake-complete",
    response_model=MarkIntakeCompleteResponse,
    dependencies=[
        require_role("intake_staff", "admin"),
        require_write_permission,
    ],
)
async def mark_intake_complete(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> MarkIntakeCompleteResponse:
    """
    Mark intake as complete.

    Validates required fields — 422 if any are missing.
    Auto-advances: intake_in_progress → intake_complete → needs_clinical_review.
    Restricted to intake_staff and admin.
    """
    case = await service.mark_intake_complete(
        session=db,
        case_id=case_id,
        organization_id=auth.organization_id,
        actor_role=auth.role_key,
        actor_user_id=auth.user_id,
    )
    return MarkIntakeCompleteResponse(
        case_id=UUID(case.id),
        final_status=case.current_status,
        message="Intake complete. Case advanced to needs_clinical_review.",
    )


# @forgeplan-spec: AC6
@router.post(
    "/cases/{case_id}/assign",
    response_model=AssignCaseResponse,
    dependencies=[require_write_permission],
)
async def assign_case(
    case_id: UUID,
    payload: AssignCaseRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> AssignCaseResponse:
    """
    Assign a user to a case.

    If the user's role is placement_coordinator, also updates
    PatientCase.assigned_coordinator_user_id.
    """
    assignment = await service.assign_case(
        session=db,
        case_id=case_id,
        organization_id=auth.organization_id,
        assigned_user_id=payload.user_id,
        assigned_role=payload.role,
        assigned_by_user_id=auth.user_id,
    )
    return AssignCaseResponse(
        case_id=UUID(assignment.patient_case_id),
        assigned_user_id=UUID(assignment.assigned_user_id),
        assigned_role=assignment.assigned_role,
        message=f"User assigned as {assignment.assigned_role}",
    )


# @forgeplan-spec: AC7
@router.post(
    "/cases/{case_id}/status-transition",
    response_model=PatientCaseSummary,
    dependencies=[require_write_permission],
)
async def status_transition(
    case_id: UUID,
    payload: StatusTransitionRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> PatientCaseSummary:
    """
    Perform a manual status transition.

    Delegates to core state_machine.
    Returns 400 with allowed_transitions if transition is invalid.
    Returns 403 if the caller's role is not permitted for this transition.
    """
    case = await service.status_transition(
        session=db,
        case_id=case_id,
        organization_id=auth.organization_id,
        to_status=payload.to_status,
        actor_role=auth.role_key,
        actor_user_id=auth.user_id,
        transition_reason=payload.transition_reason,
    )
    return PatientCaseSummary.model_validate(case)


# ---------------------------------------------------------------------------
# Import endpoints
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC8
@router.post(
    "/imports",
    status_code=status.HTTP_201_CREATED,
    response_model=ImportJobResponse,
    dependencies=[require_write_permission],
)
async def upload_import(
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> ImportJobResponse:
    """
    Accept multipart XLSX or CSV upload.

    Enforces:
      - 10 MB size limit (413)
      - Content-type validation (415)
      - ZIP bomb detection (400)
    Creates ImportJob with status=uploaded.

    CRITICAL: file bytes are read EAGERLY here. UploadFile is NOT passed
    to any background task — only raw bytes are.
    """
    # Content-type validation BEFORE reading body
    if file.content_type not in ACCEPTED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{file.content_type}'. Accepted: xlsx, csv",
        )

    # Read at most MAX_UPLOAD_BYTES+1 bytes — caps memory usage without loading the full file.
    # If exactly MAX_UPLOAD_BYTES+1 bytes are returned the file exceeds the limit.
    # (constraint: UploadFile must NOT be accessed in background task — read eagerly here)
    file_bytes = await file.read(MAX_UPLOAD_BYTES + 1)

    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large: {len(file_bytes)} bytes. Maximum is {MAX_UPLOAD_BYTES} bytes.",
        )

    # ZIP bomb detection BEFORE any spreadsheet parsing
    try:
        service.check_zip_bomb(file_bytes)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # Create ImportJob in DB (MUST be persisted before endpoint returns)
    job = await service.create_import_job(
        session=db,
        organization_id=auth.organization_id,
        created_by_user_id=auth.user_id,
        file_name=file.filename or "upload",
        file_size_bytes=len(file_bytes),
    )

    return ImportJobResponse.model_validate(job)


# @forgeplan-spec: AC9
@router.post(
    "/imports/{import_job_id}/map-columns",
    response_model=ImportJobResponse,
    dependencies=[require_write_permission],
)
async def map_columns(
    import_job_id: UUID,
    payload: ColumnMappingRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> ImportJobResponse:
    """Save column mapping and advance ImportJob to status=mapping."""
    job = await service.map_import_columns(
        session=db,
        import_job_id=import_job_id,
        organization_id=auth.organization_id,
        mapping=payload,
    )
    return ImportJobResponse.model_validate(job)


# @forgeplan-spec: AC10
@router.post(
    "/imports/{import_job_id}/validate",
    response_model=ValidateImportResponse,
    dependencies=[require_write_permission],
)
async def validate_import(
    import_job_id: UUID,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> ValidateImportResponse:
    """
    Dry-run validate all rows using openpyxl read_only=True.

    Returns per-row validation results. Advances ImportJob to status=ready.
    """
    # Content-type validation
    if file.content_type not in ACCEPTED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{file.content_type}'.",
        )

    file_bytes = await file.read(MAX_UPLOAD_BYTES + 1)

    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large",
        )

    try:
        service.check_zip_bomb(file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    job, row_results = await service.validate_import(
        session=db,
        import_job_id=import_job_id,
        organization_id=auth.organization_id,
        file_bytes=file_bytes,
        content_type=file.content_type,
    )
    return ValidateImportResponse(
        import_job_id=UUID(job.id),
        status=job.status,
        total_rows=job.total_rows or 0,
        row_results=row_results,
    )


# @forgeplan-spec: AC11
@router.post(
    "/imports/{import_job_id}/commit",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ImportJobResponse,
    dependencies=[require_write_permission],
)
async def commit_import(
    import_job_id: UUID,
    file: UploadFile,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> ImportJobResponse:
    """
    Commit import rows into PatientCase records via BackgroundTask.

    Returns 202 immediately. Background task opens FRESH AsyncSessionLocal.
    File bytes are read eagerly here — UploadFile is NEVER passed to the task.
    """
    # Content-type validation
    if file.content_type not in ACCEPTED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{file.content_type}'.",
        )

    # Read bytes eagerly BEFORE returning (constraint: UploadFile must not be accessed after request)
    file_bytes = await file.read(MAX_UPLOAD_BYTES + 1)

    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large",
        )

    try:
        service.check_zip_bomb(file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    # Verify import job exists and get column mapping
    job = await service.get_import_job(
        session=db,
        import_job_id=import_job_id,
        organization_id=auth.organization_id,
    )

    if job.column_mapping_json is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Column mapping must be set before committing",
        )

    content_type = file.content_type
    column_mapping_json = job.column_mapping_json

    # Queue background task — pass bytes (not UploadFile)
    background_tasks.add_task(
        service.run_commit,
        import_job_id=str(import_job_id),
        organization_id=str(auth.organization_id),
        created_by_user_id=str(auth.user_id),
        file_bytes=file_bytes,
        content_type=content_type,
        column_mapping_json=column_mapping_json,
    )

    return ImportJobResponse.model_validate(job)


# @forgeplan-spec: AC12
@router.get(
    "/imports/{import_job_id}",
    response_model=ImportJobResponse,
)
async def get_import_job(
    import_job_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> ImportJobResponse:
    """Return ImportJob status with current row counts."""
    job = await service.get_import_job(
        session=db,
        import_job_id=import_job_id,
        organization_id=auth.organization_id,
    )
    return ImportJobResponse.model_validate(job)


# ---------------------------------------------------------------------------
# Queue endpoints
# ---------------------------------------------------------------------------


# @forgeplan-spec: AC13
@router.get(
    "/queues/intake",
    response_model=IntakeQueueResponse,
    dependencies=[require_role("intake_staff", "admin")],
)
async def get_intake_queue(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> IntakeQueueResponse:
    """
    Return the intake queue for offshore intake staff.

    Returns cases in intake_in_progress status.
    """
    cases, total = await service.get_intake_queue(
        session=db,
        organization_id=auth.organization_id,
        page=page,
        page_size=page_size,
    )
    return IntakeQueueResponse(
        cases=[PatientCaseSummary.model_validate(c) for c in cases],
        total=total,
        page=page,
        page_size=page_size,
    )
