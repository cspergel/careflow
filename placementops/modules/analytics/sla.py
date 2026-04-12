# @forgeplan-node: analytics-module
"""
SLA threshold constants and flag computation logic.

SLA aging thresholds are defined as named constants (not inline magic numbers)
per the spec constraint. Flags are computed at query time from
case_status_history.entered_at — never stored on PatientCase.
"""
# @forgeplan-spec: AC3
# @forgeplan-decision: D-analytics-1-sla-subquery -- SLA hours_in_status uses MAX(entered_at) subquery. Why: a case may re-enter the same status (e.g., declined_retry_needed twice); MAX gives the most recent transition into the current status, which is what the spec requires

from dataclasses import dataclass


# @forgeplan-spec: AC3
@dataclass(frozen=True)
class SlaThresholds:
    """
    Named SLA threshold constants for each flaggable status.

    All values are in hours. Using a frozen dataclass ensures these constants
    cannot be accidentally mutated at runtime.
    """
    needs_clinical_review_yellow_hours: float = 4.0
    under_clinical_review_yellow_hours: float = 8.0
    outreach_pending_approval_yellow_hours: float = 2.0
    pending_facility_response_yellow_hours: float = 24.0
    pending_facility_response_red_hours: float = 48.0
    declined_retry_needed_red_hours: float = 8.0


# Module-level singleton — import this instance everywhere
SLA = SlaThresholds()


def compute_sla_flag(status: str, hours_in_status: float) -> dict:
    """
    Compute the SLA flag level for a given status and hours_in_status.

    Returns a dict with keys: level (none|yellow|red), status, hours_in_status.

    All SLA logic is in one place to prevent inconsistency across endpoints.
    """
    # @forgeplan-spec: AC3
    level = "none"

    if status == "needs_clinical_review":
        if hours_in_status > SLA.needs_clinical_review_yellow_hours:
            level = "yellow"

    elif status == "under_clinical_review":
        if hours_in_status > SLA.under_clinical_review_yellow_hours:
            level = "yellow"

    elif status == "outreach_pending_approval":
        if hours_in_status > SLA.outreach_pending_approval_yellow_hours:
            level = "yellow"

    elif status == "pending_facility_response":
        if hours_in_status > SLA.pending_facility_response_red_hours:
            level = "red"
        elif hours_in_status > SLA.pending_facility_response_yellow_hours:
            level = "yellow"

    elif status == "declined_retry_needed":
        if hours_in_status > SLA.declined_retry_needed_red_hours:
            level = "red"

    return {
        "level": level,
        "status": status,
        "hours_in_status": hours_in_status,
    }
