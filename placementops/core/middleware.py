# @forgeplan-node: core-infrastructure
"""
Shared FastAPI middleware and dependency utilities.

Provides:
  - check_case_not_closed: FastAPI Depends() for write endpoints on PatientCase children
  - PHILogFilter: logging filter that redacts known PHI field names from log records
  - configure_phi_safe_logging: sets up PHI-safe logging for the application
"""
# @forgeplan-spec: AC11
# @forgeplan-decision: D-core-5-phi-log-filter -- Log filter that redacts known PHI field names (patient_name, dob, mrn, etc.) from structured log records. Why: HIPAA requires that PHI not appear in application logs; filter approach covers all log sites without requiring per-callsite scrubbing

from __future__ import annotations

import logging
from typing import Callable
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.auth import AuthContext, get_auth_context
from placementops.core.database import get_db

# PHI field names that must never appear in logs
_PHI_FIELDS = frozenset(
    [
        "patient_name",
        "dob",
        "mrn",
        "room_number",
        "hospital_unit",
        "primary_diagnosis_text",
        "insurance_primary",
        "insurance_secondary",
        "patient_zip",
        "preferred_geography_text",
        "email",
        "full_name",
        "phone",
        "contact_name",
        "draft_body",
        "draft_subject",
        "clinical_summary",
        "barriers_to_placement",
        "payer_notes",
        "family_preference_notes",
    ]
)


class PHILogFilter(logging.Filter):
    """
    Logging filter that redacts PHI field names from log record messages and args.

    Applied to the root logger or specific loggers. Replaces known PHI key names
    with [REDACTED] in string representations. Does NOT redact UUIDs or status codes.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        # Redact from the message string
        if record.msg and isinstance(record.msg, str):
            for field in _PHI_FIELDS:
                if field in record.msg:
                    record.msg = record.msg.replace(field, "[REDACTED_FIELD]")
        # Redact from kwargs dict if present
        if hasattr(record, "args") and isinstance(record.args, dict):
            for field in _PHI_FIELDS:
                if field in record.args:
                    record.args = {**record.args, field: "[REDACTED]"}
        return True


def configure_phi_safe_logging(level: str = "INFO") -> None:
    """
    Configure application-wide PHI-safe logging.

    Attaches PHILogFilter to the root logger and sets log level.
    Call once at application startup from main.py lifespan.
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    phi_filter = PHILogFilter()
    root_logger.addFilter(phi_filter)

    # Also attach to uvicorn loggers
    for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"):
        logging.getLogger(logger_name).addFilter(phi_filter)


def check_case_not_closed(case_id_param: str = "case_id") -> Callable:
    """
    Factory that returns a FastAPI Depends() which blocks writes to closed cases.

    Usage in a route:
        @router.patch("/{case_id}/assessments")
        async def update_assessment(
            case_id: UUID,
            _: None = Depends(check_case_not_closed()),
            ...
        ):
            ...

    Returns HTTP 404 if case not found.
    Returns HTTP 409 if case is closed.
    """

    async def _dependency(
        case_id: UUID,
        session: AsyncSession = Depends(get_db),
        auth: AuthContext = Depends(get_auth_context),
    ) -> None:
        # @forgeplan-spec: AC11
        from placementops.core.models.patient_case import PatientCase

        # F3: Filter by organization_id to prevent cross-tenant case access.
        # Using select with org_id guard instead of session.get() ensures that a case
        # belonging to a different organisation returns 404 rather than 409, preventing
        # an attacker from probing closed status across tenant boundaries.
        result = await session.execute(
            select(PatientCase).where(
                PatientCase.id == str(case_id),
                PatientCase.organization_id == str(auth.organization_id),
            )
        )
        case = result.scalar_one_or_none()
        if case is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Case {case_id} not found",
            )
        if case.current_status == "closed":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Case is closed — no further modifications permitted",
            )

    return _dependency
