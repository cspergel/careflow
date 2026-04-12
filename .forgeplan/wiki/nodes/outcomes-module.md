# Node: outcomes-module

## Operational Summary
- **Status:** reviewed
- **Node type:** service
- **Tracked files:** 8
- **Test files:** 0
- **Dependencies:** 3 | **Connections:** 4
- **Recent issues:** review/reviewer: AC14 | review/reviewer: F3

## Decisions (from @forgeplan-decision markers)
- **D-outcomes-1-pre-flush-atomicity**: Flush all pending writes before calling transition_case_status which commits. Why: transition_case_status owns the commit; flushing ensures outcome row + auto-cancel updates land in the same atomic commit as the status advance. [placementops/modules/outcomes/service.py:30]
- **D-outcomes-2-timeline-from-csh**: Read timeline from CaseStatusHistory table. Why: in-process event bus (CaseActivityEvent) is ephemeral; CaseStatusHistory is the only durable timeline store written by transition_case_status. [placementops/modules/outcomes/service.py:31]
- **D-outcomes-3-family-withdrawn-no-transition**: family_declined/withdrawn do not call transition_case_status. Why: spec requires manager confirmation via separate status-transition; auto-advancing to closed removes required managerial oversight. [placementops/modules/outcomes/service.py:32]
- **D-outcomes-4-outcome-audit-separate**: Write AuditEvent with entity_type=placement_outcome for every outcome type. Why: AC14 mandates audit for all 5 types; transition_case_status only writes for types that advance status; family_declined/withdrawn have no status change audit unless we write it here. [placementops/modules/outcomes/service.py:33]

## Past Findings
| Pass | Agent | Finding | Resolution |
|------|-------|---------|------------|
| review | reviewer | AC14 | MEDIUM |
| review | reviewer | F3 | AC1 |

## Cross-References
- Depends on: core-infrastructure
- Depends on: auth-module
- Depends on: outreach-module
- Connected to: core-infrastructure
- Connected to: auth-module
- Connected to: outreach-module
- Connected to: analytics-module
