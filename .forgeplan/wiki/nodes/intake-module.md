# Node: intake-module

## Operational Summary
- **Status:** reviewed
- **Node type:** service
- **Tracked files:** 10
- **Test files:** 0
- **Dependencies:** 2 | **Connections:** 4

## Decisions (from @forgeplan-decision markers)
- **D-intake-1-local-models**: IntakeFieldIssue and CaseAssignment defined in intake module (not core). Why: these models do not exist in core/models and are intake-specific; defining locally avoids modifying core file_scope while keeping the data models available. [placementops/modules/intake/models.py:11]
- **D-intake-2-file-bytes-in-memory**: file_bytes passed in-memory to BackgroundTask, not persisted to DB. Why: ImportJob has no file_bytes column; spec pattern shows bytes passed as task argument; avoids adding large binary to ImportJob table. [placementops/modules/intake/service.py:16]
- **D-intake-3-required-intake-fields**: Required fields for mark-intake-complete: patient_name, hospital_id, hospital_unit, room_number, admission_date, primary_diagnosis_text, insurance_primary. Why: minimum fields needed for clinical review; inferred from intake domain since spec does not enumerate them. [placementops/modules/intake/service.py:17]
- **D-intake-4-resolved-flag-true**: resolved_flag=True means issue is resolved. Why: "resolved" semantics; set to True when field re-submitted with valid value per AC15. [placementops/modules/intake/service.py:18]
- **D-intake-5-fresh-session-background**: Opens fresh AsyncSessionLocal in background task. Why: request session is closed before background task runs; reusing it causes DetachedInstanceError on every write. [placementops/modules/intake/service.py:1020]

## Past Findings
| Pass | Agent | Finding | Resolution |
|------|-------|---------|------------|

## Cross-References
- Depends on: core-infrastructure
- Depends on: auth-module
- Connected to: core-infrastructure
- Connected to: auth-module
- Connected to: clinical-module
- Connected to: admin-surfaces
