# @forgeplan-node: analytics-module
"""
Pydantic v2 schemas for all analytics module data models.

Covers: SlaFlag, OperationsQueueItem, SlaThresholds, StatusAgingBucket,
ManagerSummary, StageMetric, DashboardReport, FacilityOutreachStats,
DeclineReasonBreakdown, OutreachPerformanceReport, PaginationMeta,
PaginatedOperationsQueue.
"""
# @forgeplan-spec: AC1
# @forgeplan-spec: AC2
# @forgeplan-spec: AC3
# @forgeplan-spec: AC4
# @forgeplan-spec: AC5
# @forgeplan-spec: AC6
# @forgeplan-spec: AC8

from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# SLA schemas
# ---------------------------------------------------------------------------

class SlaFlag(BaseModel):
    """SLA aging flag for a single case. level: none | yellow | red."""
    level: Literal["none", "yellow", "red"]
    status: str
    hours_in_status: float


# ---------------------------------------------------------------------------
# Operations queue schemas
# ---------------------------------------------------------------------------

class OperationsQueueItem(BaseModel):
    """Single row in the operations queue with SLA aging flag."""
    case_id: UUID
    patient_name: str
    hospital_id: UUID | None
    hospital_name: str | None
    current_status: str
    priority_level: str | None
    assigned_coordinator_name: str | None
    assigned_coordinator_user_id: UUID | None
    discharge_target_date: date | None
    sla_flag: SlaFlag
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaginatedOperationsQueue(BaseModel):
    """Paginated response for GET /api/v1/queues/operations."""
    items: list[OperationsQueueItem]
    total_count: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Manager summary schemas
# ---------------------------------------------------------------------------

class StatusAgingBucket(BaseModel):
    """Aging distribution bucket for a single status."""
    status: str
    case_count: int
    sla_breach_count: int
    avg_hours_in_status: float


class ManagerSummary(BaseModel):
    """Response for GET /api/v1/queues/manager-summary."""
    total_active_cases: int
    aging_by_status: list[StatusAgingBucket]
    sla_breach_cases: list[OperationsQueueItem]
    generated_at: datetime
    # Pagination metadata for sla_breach_cases list
    total_breach_cases: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Dashboard report schemas
# ---------------------------------------------------------------------------

class StageMetric(BaseModel):
    """Average cycle time for a workflow stage."""
    stage_name: str
    avg_cycle_hours: float
    case_count: int


class DashboardReport(BaseModel):
    """Response for GET /api/v1/analytics/dashboard."""
    date_from: date
    date_to: date
    total_cases: int
    cases_by_status: dict[str, int]
    placement_rate_pct: float
    avg_placement_days: Optional[float] = None
    stage_metrics: list[StageMetric]
    generated_at: datetime


# ---------------------------------------------------------------------------
# Outreach performance schemas
# ---------------------------------------------------------------------------

class FacilityOutreachStats(BaseModel):
    """Accept/decline stats for a single facility."""
    facility_id: UUID
    facility_name: str
    total_outreach_sent: int
    accepted_count: int
    declined_count: int
    acceptance_rate_pct: float


class DeclineReasonBreakdown(BaseModel):
    """Decline reason frequency breakdown."""
    decline_reason_code: str
    decline_reason_label: str
    count: int
    pct_of_total_declines: float


class OutreachPerformanceReport(BaseModel):
    """Response for GET /api/v1/analytics/outreach-performance."""
    date_from: date
    date_to: date
    by_facility: list[FacilityOutreachStats]
    by_decline_reason: list[DeclineReasonBreakdown]
    generated_at: datetime


# ---------------------------------------------------------------------------
# Query parameter schemas
# ---------------------------------------------------------------------------

class DateRangeParams(BaseModel):
    """Validated date range parameters with 30-day default."""
    date_from: date | None = None
    date_to: date | None = None

    @field_validator("date_from", "date_to", mode="before")
    @classmethod
    def parse_date(cls, v):
        if v is None:
            return None
        if isinstance(v, date):
            return v
        return date.fromisoformat(str(v))
