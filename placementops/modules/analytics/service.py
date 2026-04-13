# @forgeplan-node: analytics-module
"""
Analytics service layer — all four query functions.

READ-ONLY module: no INSERT, UPDATE, or DELETE operations anywhere in this file.
All queries scope by organization_id from AuthContext (never from user input).
"""
# @forgeplan-spec: AC2
# @forgeplan-spec: AC3
# @forgeplan-spec: AC4
# @forgeplan-spec: AC5
# @forgeplan-spec: AC6
# @forgeplan-spec: AC7
# @forgeplan-spec: AC8
# @forgeplan-spec: AC9
# @forgeplan-decision: D-analytics-2-stage-metrics-window -- Stage cycle time via self-join on case_status_history aliased as h1/h2. Why: SQLAlchemy async doesn't support window functions cleanly for this pattern; self-join on (h2.patient_case_id=h1.patient_case_id AND h2.from_status=h1.to_status) gives exact stage durations per the spec's "transition timestamps" requirement.
# @forgeplan-decision: D-analytics-3-placement-outcome-join -- Outcomes org-scoped via JOIN through PatientCase. Why: PlacementOutcome has no organization_id column; must join through patient_cases to enforce tenant isolation on all outcome queries.

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from placementops.core.models import (
    CaseStatusHistory,
    DeclineReasonReference,
    Facility,
    HospitalReference,
    PatientCase,
    PlacementOutcome,
    User,
)
from placementops.modules.analytics.schemas import (
    DashboardReport,
    DeclineReasonBreakdown,
    FacilityOutreachStats,
    ManagerSummary,
    OperationsQueueItem,
    OutreachPerformanceReport,
    PaginatedOperationsQueue,
    SlaFlag,
    StageMetric,
    StatusAgingBucket,
)
from placementops.modules.analytics.sla import SLA, compute_sla_flag


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_date_range(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    """
    Apply 30-day default and validate date range.

    Returns (date_from, date_to).
    Raises HTTP 400 if date_from > date_to.
    """
    today = datetime.now(timezone.utc).date()
    resolved_from = date_from if date_from is not None else (today - timedelta(days=30))
    resolved_to = date_to if date_to is not None else today

    if resolved_from > resolved_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"date_from ({resolved_from}) must be <= date_to ({resolved_to})",
        )
    return resolved_from, resolved_to


def _validate_page_size(page: int, page_size: int) -> None:
    """Validate pagination parameters."""
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="page must be >= 1",
        )
    if page_size < 1 or page_size > 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="page_size must be between 1 and 200",
        )


# ---------------------------------------------------------------------------
# AC2, AC3, AC8 — GET /api/v1/queues/operations
# ---------------------------------------------------------------------------

async def get_operations_queue(
    session: AsyncSession,
    organization_id: UUID,
    *,
    status_filter: str | None = None,
    hospital_id: UUID | None = None,
    assigned_coordinator_user_id: UUID | None = None,
    priority: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> PaginatedOperationsQueue:
    """
    Return paginated OperationsQueueItem list with SLA flags.

    Organization scoped exclusively to organization_id from AuthContext.
    SLA flags computed at query time from case_status_history.entered_at.
    """
    # @forgeplan-spec: AC2
    # @forgeplan-spec: AC8
    # @forgeplan-spec: AC9
    _validate_page_size(page, page_size)

    now_utc = datetime.now(timezone.utc)

    # Correlated subquery: entered_at for current status
    sla_entered_subq = (
        select(func.max(CaseStatusHistory.entered_at))
        .where(
            CaseStatusHistory.patient_case_id == PatientCase.id,
            CaseStatusHistory.to_status == PatientCase.current_status,
        )
        .correlate(PatientCase)
        .scalar_subquery()
    )

    # Build base query with JOINs for hospital name and coordinator name
    stmt = (
        select(
            PatientCase.id.label("case_id"),
            PatientCase.patient_name,
            PatientCase.hospital_id,
            HospitalReference.hospital_name.label("hospital_name"),
            PatientCase.current_status,
            PatientCase.priority_level,
            User.full_name.label("assigned_coordinator_name"),
            PatientCase.assigned_coordinator_user_id,
            PatientCase.discharge_target_date,
            PatientCase.created_at,
            PatientCase.updated_at,
            sla_entered_subq.label("status_entered_at"),
        )
        .outerjoin(
            HospitalReference,
            PatientCase.hospital_id == HospitalReference.id,
        )
        .outerjoin(
            User,
            PatientCase.assigned_coordinator_user_id == User.id,
        )
        .where(PatientCase.organization_id == str(organization_id))
    )

    # Apply optional filters
    if status_filter is not None:
        stmt = stmt.where(PatientCase.current_status == status_filter)
    if hospital_id is not None:
        stmt = stmt.where(PatientCase.hospital_id == str(hospital_id))
    if assigned_coordinator_user_id is not None:
        stmt = stmt.where(
            PatientCase.assigned_coordinator_user_id == str(assigned_coordinator_user_id)
        )
    if priority is not None:
        stmt = stmt.where(PatientCase.priority_level == priority)

    # Count total before pagination
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_count_result = await session.execute(count_stmt)
    total_count = total_count_result.scalar_one()

    # Apply pagination
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size).order_by(PatientCase.created_at.desc())

    result = await session.execute(stmt)
    rows = result.mappings().all()

    # @forgeplan-spec: AC3 — compute SLA flags in Python from status_entered_at
    items: list[OperationsQueueItem] = []
    for row in rows:
        status_val = row["current_status"]
        status_entered_at = row["status_entered_at"]

        if status_entered_at is not None:
            # Normalize to UTC-aware datetime for arithmetic
            if status_entered_at.tzinfo is None:
                status_entered_at = status_entered_at.replace(tzinfo=timezone.utc)
            hours_in_status = (now_utc - status_entered_at).total_seconds() / 3600.0
        else:
            hours_in_status = 0.0

        flag_dict = compute_sla_flag(status_val, hours_in_status)
        sla_flag = SlaFlag(**flag_dict)

        case_id = row["case_id"]
        hospital_id_val = row["hospital_id"]
        coordinator_id_val = row["assigned_coordinator_user_id"]

        items.append(
            OperationsQueueItem(
                case_id=UUID(str(case_id)),
                patient_name=row["patient_name"],
                hospital_id=UUID(str(hospital_id_val)) if hospital_id_val else None,
                hospital_name=row["hospital_name"],
                current_status=status_val,
                priority_level=row["priority_level"],
                assigned_coordinator_name=row["assigned_coordinator_name"],
                assigned_coordinator_user_id=(
                    UUID(str(coordinator_id_val)) if coordinator_id_val else None
                ),
                discharge_target_date=row["discharge_target_date"],
                sla_flag=sla_flag,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        )

    return PaginatedOperationsQueue(
        items=items,
        total_count=total_count,
        page=page,
        page_size=page_size,
    )


# ---------------------------------------------------------------------------
# AC4 — GET /api/v1/queues/manager-summary
# ---------------------------------------------------------------------------

async def get_manager_summary(
    session: AsyncSession,
    organization_id: UUID,
    *,
    page: int = 1,
    page_size: int = 50,
) -> ManagerSummary:
    """
    Return queue aging distribution and SLA breach case list.

    Organization scoped exclusively to organization_id from AuthContext.
    """
    # @forgeplan-spec: AC4
    # @forgeplan-spec: AC8
    # @forgeplan-spec: AC9
    _validate_page_size(page, page_size)

    now_utc = datetime.now(timezone.utc)

    # Correlated subquery for status_entered_at
    sla_entered_subq = (
        select(func.max(CaseStatusHistory.entered_at))
        .where(
            CaseStatusHistory.patient_case_id == PatientCase.id,
            CaseStatusHistory.to_status == PatientCase.current_status,
        )
        .correlate(PatientCase)
        .scalar_subquery()
    )

    # Fetch all active cases with SLA data in one query
    active_statuses_excluded = ("placed", "closed")
    base_stmt = (
        select(
            PatientCase.id.label("case_id"),
            PatientCase.patient_name,
            PatientCase.hospital_id,
            HospitalReference.hospital_name.label("hospital_name"),
            PatientCase.current_status,
            PatientCase.priority_level,
            User.full_name.label("assigned_coordinator_name"),
            PatientCase.assigned_coordinator_user_id,
            PatientCase.discharge_target_date,
            PatientCase.created_at,
            PatientCase.updated_at,
            sla_entered_subq.label("status_entered_at"),
        )
        .outerjoin(HospitalReference, PatientCase.hospital_id == HospitalReference.id)
        .outerjoin(User, PatientCase.assigned_coordinator_user_id == User.id)
        .where(
            PatientCase.organization_id == str(organization_id),
            PatientCase.current_status.notin_(active_statuses_excluded),
        )
    )

    result = await session.execute(base_stmt)
    rows = result.mappings().all()

    total_active_cases = len(rows)

    # Build OperationsQueueItem objects with SLA flags
    all_items: list[OperationsQueueItem] = []
    status_buckets: dict[str, dict] = {}

    for row in rows:
        status_val = row["current_status"]
        status_entered_at = row["status_entered_at"]

        if status_entered_at is not None:
            if status_entered_at.tzinfo is None:
                status_entered_at = status_entered_at.replace(tzinfo=timezone.utc)
            hours_in_status = (now_utc - status_entered_at).total_seconds() / 3600.0
        else:
            hours_in_status = 0.0

        flag_dict = compute_sla_flag(status_val, hours_in_status)
        sla_flag = SlaFlag(**flag_dict)

        case_id = row["case_id"]
        hospital_id_val = row["hospital_id"]
        coordinator_id_val = row["assigned_coordinator_user_id"]

        item = OperationsQueueItem(
            case_id=UUID(str(case_id)),
            patient_name=row["patient_name"],
            hospital_id=UUID(str(hospital_id_val)) if hospital_id_val else None,
            hospital_name=row["hospital_name"],
            current_status=status_val,
            priority_level=row["priority_level"],
            assigned_coordinator_name=row["assigned_coordinator_name"],
            assigned_coordinator_user_id=(
                UUID(str(coordinator_id_val)) if coordinator_id_val else None
            ),
            discharge_target_date=row["discharge_target_date"],
            sla_flag=sla_flag,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        all_items.append(item)

        # Aggregate into status buckets
        if status_val not in status_buckets:
            status_buckets[status_val] = {
                "hours_list": [],
                "breach_count": 0,
            }
        status_buckets[status_val]["hours_list"].append(hours_in_status)
        if sla_flag.level in ("yellow", "red"):
            status_buckets[status_val]["breach_count"] += 1

    # Build aging_by_status list
    aging_by_status: list[StatusAgingBucket] = []
    for status_val, data in sorted(status_buckets.items()):
        hours_list = data["hours_list"]
        avg_hours = sum(hours_list) / len(hours_list) if hours_list else 0.0
        aging_by_status.append(
            StatusAgingBucket(
                status=status_val,
                case_count=len(hours_list),
                sla_breach_count=data["breach_count"],
                avg_hours_in_status=avg_hours,
            )
        )

    # Filter breach cases
    breach_items = [item for item in all_items if item.sla_flag.level in ("yellow", "red")]
    total_breach = len(breach_items)

    # Paginate breach cases
    offset = (page - 1) * page_size
    paginated_breach = breach_items[offset : offset + page_size]

    return ManagerSummary(
        total_active_cases=total_active_cases,
        aging_by_status=aging_by_status,
        sla_breach_cases=paginated_breach,
        generated_at=now_utc,
        total_breach_cases=total_breach,
        page=page,
        page_size=page_size,
    )


# ---------------------------------------------------------------------------
# AC5 — GET /api/v1/analytics/dashboard
# ---------------------------------------------------------------------------

async def get_dashboard_report(
    session: AsyncSession,
    organization_id: UUID,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> DashboardReport:
    """
    Return case volume by status, placement rate, and stage cycle metrics.

    Date range defaults to last 30 days. Filters on PatientCase.created_at.
    Organization scoped exclusively to organization_id from AuthContext.
    """
    # @forgeplan-spec: AC5
    # @forgeplan-spec: AC9
    resolved_from, resolved_to = _resolve_date_range(date_from, date_to)
    now_utc = datetime.now(timezone.utc)

    # Convert dates to datetime for comparison with timestamp columns
    from_dt = datetime.combine(resolved_from, datetime.min.time()).replace(tzinfo=timezone.utc)
    to_dt = datetime.combine(resolved_to, datetime.max.time()).replace(tzinfo=timezone.utc)

    # Total case count and cases by status
    status_count_stmt = (
        select(
            PatientCase.current_status,
            func.count(PatientCase.id).label("cnt"),
        )
        .where(
            PatientCase.organization_id == str(organization_id),
            PatientCase.created_at >= from_dt,
            PatientCase.created_at <= to_dt,
        )
        .group_by(PatientCase.current_status)
    )
    status_result = await session.execute(status_count_stmt)
    status_rows = status_result.all()

    cases_by_status: dict[str, int] = {}
    total_cases = 0
    for row in status_rows:
        cases_by_status[row.current_status] = row.cnt
        total_cases += row.cnt

    # Placement rate: count(outcome_type='placed') / total_cases * 100
    # Uses PlacementOutcome joined to PatientCase for org scoping
    placed_count_stmt = (
        select(func.count(PlacementOutcome.id))
        .join(PatientCase, PlacementOutcome.patient_case_id == PatientCase.id)
        .where(
            PatientCase.organization_id == str(organization_id),
            PatientCase.created_at >= from_dt,
            PatientCase.created_at <= to_dt,
            PlacementOutcome.outcome_type == "placed",
        )
    )
    placed_result = await session.execute(placed_count_stmt)
    placed_count = placed_result.scalar_one() or 0

    if total_cases > 0:
        placement_rate_pct = round((placed_count / total_cases) * 100.0, 2)
    else:
        placement_rate_pct = 0.0

    # avg_placement_days: average days from PatientCase.created_at to when the case
    # first reached 'placed' or 'closed' status in case_status_history.
    # Fetched as (case created_at, history entered_at) pairs and averaged in Python
    # for DB-agnostic datetime arithmetic (avoids PG-only extract("epoch") syntax).
    placement_timing_stmt = (
        select(
            PatientCase.created_at.label("case_created_at"),
            func.min(CaseStatusHistory.entered_at).label("terminal_entered_at"),
        )
        .join(CaseStatusHistory, CaseStatusHistory.patient_case_id == PatientCase.id)
        .where(
            PatientCase.organization_id == str(organization_id),
            PatientCase.created_at >= from_dt,
            PatientCase.created_at <= to_dt,
            CaseStatusHistory.to_status.in_(["placed", "closed"]),
        )
        .group_by(PatientCase.id, PatientCase.created_at)
    )
    placement_timing_result = await session.execute(placement_timing_stmt)
    placement_timing_rows = placement_timing_result.mappings().all()

    avg_placement_days: float | None = None
    if placement_timing_rows:
        day_deltas: list[float] = []
        for row in placement_timing_rows:
            t_created = row["case_created_at"]
            t_terminal = row["terminal_entered_at"]
            if t_created is not None and t_terminal is not None:
                if t_created.tzinfo is None:
                    t_created = t_created.replace(tzinfo=timezone.utc)
                if t_terminal.tzinfo is None:
                    t_terminal = t_terminal.replace(tzinfo=timezone.utc)
                delta_days = (t_terminal - t_created).total_seconds() / 86400.0
                if delta_days >= 0:
                    day_deltas.append(delta_days)
        if day_deltas:
            avg_placement_days = round(sum(day_deltas) / len(day_deltas), 2)

    # Stage metrics: avg cycle time per status stage using case_status_history
    # Self-join: h1 = entering a stage, h2 = leaving that stage (h2.from_status = h1.to_status)
    # Raw timestamps fetched in Python for DB-agnostic arithmetic (avoids extract("epoch") PG-only syntax)
    # @forgeplan-decision: D-analytics-4-stage-metrics-python-arithmetic -- Stage cycle hours computed in Python after fetching (h1.entered_at, h2.entered_at) pairs. Why: func.extract("epoch", timedelta) is PostgreSQL-only; Python datetime arithmetic works on both SQLite (tests) and PostgreSQL (production).
    h1 = aliased(CaseStatusHistory)
    h2 = aliased(CaseStatusHistory)

    stage_raw_stmt = (
        select(
            h1.to_status.label("stage_name"),
            h1.entered_at.label("h1_entered_at"),
            h2.entered_at.label("h2_entered_at"),
        )
        .join(
            h2,
            (h2.patient_case_id == h1.patient_case_id)
            & (h2.from_status == h1.to_status),
        )
        .join(
            PatientCase,
            PatientCase.id == h1.patient_case_id,
        )
        .where(
            PatientCase.organization_id == str(organization_id),
            PatientCase.created_at >= from_dt,
            PatientCase.created_at <= to_dt,
        )
    )
    stage_raw_result = await session.execute(stage_raw_stmt)
    stage_raw_rows = stage_raw_result.mappings().all()

    # Aggregate in Python
    stage_buckets: dict[str, list[float]] = {}
    for row in stage_raw_rows:
        stage_name = row["stage_name"]
        t1 = row["h1_entered_at"]
        t2 = row["h2_entered_at"]
        if t1 is not None and t2 is not None:
            if t1.tzinfo is None:
                t1 = t1.replace(tzinfo=timezone.utc)
            if t2.tzinfo is None:
                t2 = t2.replace(tzinfo=timezone.utc)
            delta_hours = (t2 - t1).total_seconds() / 3600.0
            if stage_name not in stage_buckets:
                stage_buckets[stage_name] = []
            stage_buckets[stage_name].append(delta_hours)

    stage_metrics: list[StageMetric] = []
    for stage_name, hours_list in sorted(stage_buckets.items()):
        avg_hours = sum(hours_list) / len(hours_list) if hours_list else 0.0
        stage_metrics.append(
            StageMetric(
                stage_name=stage_name,
                avg_cycle_hours=round(avg_hours, 2),
                case_count=len(hours_list),
            )
        )

    return DashboardReport(
        date_from=resolved_from,
        date_to=resolved_to,
        total_cases=total_cases,
        cases_by_status=cases_by_status,
        placement_rate_pct=placement_rate_pct,
        avg_placement_days=avg_placement_days,
        stage_metrics=stage_metrics,
        generated_at=now_utc,
    )


# ---------------------------------------------------------------------------
# AC6 — GET /api/v1/analytics/outreach-performance
# ---------------------------------------------------------------------------

async def get_outreach_performance(
    session: AsyncSession,
    organization_id: UUID,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> OutreachPerformanceReport:
    """
    Return accept/decline rates by facility and decline reason breakdown.

    Date range filters on PlacementOutcome.created_at.
    Organization scoped via JOIN through PatientCase (PlacementOutcome has no org_id).
    """
    # @forgeplan-spec: AC6
    # @forgeplan-spec: AC9
    resolved_from, resolved_to = _resolve_date_range(date_from, date_to)
    now_utc = datetime.now(timezone.utc)

    from_dt = datetime.combine(resolved_from, datetime.min.time()).replace(tzinfo=timezone.utc)
    to_dt = datetime.combine(resolved_to, datetime.max.time()).replace(tzinfo=timezone.utc)

    # --- By facility: group PlacementOutcomes by facility_id
    # accepted = outcome_type IN ('accepted', 'placed')
    # declined = outcome_type = 'declined'
    facility_stmt = (
        select(
            PlacementOutcome.facility_id,
            Facility.facility_name,
            func.count(PlacementOutcome.id).label("total_outreach_sent"),
            func.sum(
                case(
                    (PlacementOutcome.outcome_type.in_(["accepted", "placed"]), 1),
                    else_=0,
                )
            ).label("accepted_count"),
            func.sum(
                case(
                    (PlacementOutcome.outcome_type == "declined", 1),
                    else_=0,
                )
            ).label("declined_count"),
        )
        .join(PatientCase, PlacementOutcome.patient_case_id == PatientCase.id)
        .join(Facility, PlacementOutcome.facility_id == Facility.id)
        .where(
            PatientCase.organization_id == str(organization_id),
            PlacementOutcome.created_at >= from_dt,
            PlacementOutcome.created_at <= to_dt,
            PlacementOutcome.facility_id.is_not(None),
        )
        .group_by(PlacementOutcome.facility_id, Facility.facility_name)
        .order_by(Facility.facility_name)
    )
    facility_result = await session.execute(facility_stmt)
    facility_rows = facility_result.all()

    by_facility: list[FacilityOutreachStats] = []
    for row in facility_rows:
        total = row.total_outreach_sent or 0
        accepted = int(row.accepted_count or 0)
        declined = int(row.declined_count or 0)
        rate = round((accepted / total * 100.0) if total > 0 else 0.0, 2)
        by_facility.append(
            FacilityOutreachStats(
                facility_id=UUID(str(row.facility_id)),
                facility_name=row.facility_name,
                total_outreach_sent=total,
                accepted_count=accepted,
                declined_count=declined,
                acceptance_rate_pct=rate,
            )
        )

    # --- By decline reason: group PlacementOutcomes with outcome_type='declined'
    total_declines_stmt = (
        select(func.count(PlacementOutcome.id))
        .join(PatientCase, PlacementOutcome.patient_case_id == PatientCase.id)
        .where(
            PatientCase.organization_id == str(organization_id),
            PlacementOutcome.created_at >= from_dt,
            PlacementOutcome.created_at <= to_dt,
            PlacementOutcome.outcome_type == "declined",
        )
    )
    total_declines_result = await session.execute(total_declines_stmt)
    total_declines = total_declines_result.scalar_one() or 0

    decline_reason_stmt = (
        select(
            PlacementOutcome.decline_reason_code,
            DeclineReasonReference.label.label("decline_reason_label"),
            func.count(PlacementOutcome.id).label("cnt"),
        )
        .join(PatientCase, PlacementOutcome.patient_case_id == PatientCase.id)
        .outerjoin(
            DeclineReasonReference,
            PlacementOutcome.decline_reason_code == DeclineReasonReference.code,
        )
        .where(
            PatientCase.organization_id == str(organization_id),
            PlacementOutcome.created_at >= from_dt,
            PlacementOutcome.created_at <= to_dt,
            PlacementOutcome.outcome_type == "declined",
            PlacementOutcome.decline_reason_code.is_not(None),
        )
        .group_by(
            PlacementOutcome.decline_reason_code,
            DeclineReasonReference.label,
        )
        .order_by(func.count(PlacementOutcome.id).desc())
    )
    decline_result = await session.execute(decline_reason_stmt)
    decline_rows = decline_result.all()

    by_decline_reason: list[DeclineReasonBreakdown] = []
    for row in decline_rows:
        pct = round((row.cnt / total_declines * 100.0) if total_declines > 0 else 0.0, 2)
        # Fall back to the code if no reference label exists
        label = row.decline_reason_label if row.decline_reason_label else row.decline_reason_code
        by_decline_reason.append(
            DeclineReasonBreakdown(
                decline_reason_code=row.decline_reason_code,
                decline_reason_label=label,
                count=row.cnt,
                pct_of_total_declines=pct,
            )
        )

    return OutreachPerformanceReport(
        date_from=resolved_from,
        date_to=resolved_to,
        by_facility=by_facility,
        by_decline_reason=by_decline_reason,
        generated_at=now_utc,
    )
