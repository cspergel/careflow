# Node: analytics-module

## Operational Summary
- **Status:** reviewed
- **Node type:** service
- **Tracked files:** 7
- **Test files:** 0
- **Dependencies:** 3 | **Connections:** 2

## Decisions (from @forgeplan-decision markers)
- **D-analytics-1-sla-subquery**: SLA hours_in_status uses MAX(entered_at) subquery. Why: a case may re-enter the same status (e.g., declined_retry_needed twice); MAX gives the most recent transition into the current status, which is what the spec requires. [placementops/modules/analytics/sla.py:10]
- **D-analytics-2-stage-metrics-window**: Stage cycle time via self-join on case_status_history aliased as h1/h2. Why: SQLAlchemy async doesn't support window functions cleanly for this pattern; self-join on (h2.patient_case_id=h1.patient_case_id AND h2.from_status=h1.to_status) gives exact stage durations per the spec's "transition timestamps" requirement.. [placementops/modules/analytics/service.py:16]
- **D-analytics-3-placement-outcome-join**: Outcomes org-scoped via JOIN through PatientCase. Why: PlacementOutcome has no organization_id column; must join through patient_cases to enforce tenant isolation on all outcome queries.. [placementops/modules/analytics/service.py:17]
- **D-analytics-4-stage-metrics-python-arithmetic**: Stage cycle hours computed in Python after fetching (h1.entered_at, h2.entered_at) pairs. Why: func.extract("epoch", timedelta) is PostgreSQL-only; Python datetime arithmetic works on both SQLite (tests) and PostgreSQL (production).. [placementops/modules/analytics/service.py:484]

## Past Findings
| Pass | Agent | Finding | Resolution |
|------|-------|---------|------------|

## Cross-References
- Depends on: core-infrastructure
- Depends on: auth-module
- Depends on: outcomes-module
- Connected to: core-infrastructure
- Connected to: outcomes-module
