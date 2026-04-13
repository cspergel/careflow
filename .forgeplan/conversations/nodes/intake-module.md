# intake-module Build Log

## Pre-Build Spec Challenge

### Files Read
- `placementops/core/database.py` — AsyncSessionLocal, get_db, Base, NullPool config
- `placementops/core/auth.py` — AuthContext, get_auth_context, require_org_match
- `placementops/modules/auth/dependencies.py` — require_role, require_write_permission, RolePermissions
- `placementops/core/models/patient_case.py` — PatientCase ORM, CASE_STATUSES
- `placementops/core/models/import_job.py` — ImportJob ORM (no file_bytes field)
- `placementops/core/models/case_status_history.py` — CaseStatusHistory ORM
- `placementops/core/state_machine.py` — transition_case_status, STATE_MACHINE_TRANSITIONS
- `placementops/core/events.py` — CaseActivityEvent, publish_case_activity_event
- `placementops/core/audit.py` — emit_audit_event()
- `placementops/core/models/__init__.py` — exported models list
- `placementops/core/models/user.py` — User ORM

### Ambiguities Resolved

#### 1. IntakeFieldIssue and CaseAssignment missing from core
Neither `IntakeFieldIssue` nor `CaseAssignment` exists in `placementops/core/models/`. Both will be defined locally in `placementops/modules/intake/models.py`.
**CONCERN**: These local models will need migrations or `Base.metadata.create_all()` for test setup.

#### 2. openpyxl not in requirements.txt
`openpyxl` is absent from requirements.txt. **CONCERN**: orchestrator must add it. The implementation imports openpyxl and will fail at import time if not installed. Documented for orchestrator.

#### 3. file_bytes storage for BackgroundTask
`ImportJob` has no `file_bytes` column. The spec says "reads file bytes (already stored)" for AC11. Two interpretations:
- (A) Bytes are passed as an in-memory parameter to the BackgroundTask function directly (spec example confirms this pattern)
- (B) Bytes are persisted to DB in a LargeBinary column

**Decision**: Use interpretation (A) — pass bytes in memory. The spec example explicitly shows `background_tasks.add_task(service.run_commit, import_id=..., file_bytes=file_bytes, ...)`. The phrase "already stored" in AC11 description refers to the bytes being stored in the task's closure, not in the DB. This avoids adding a potentially large binary column to ImportJob.

#### 4. transition_case_status commits internally
`transition_case_status()` in state_machine.py calls `await session.commit()` internally. This means for AC1 (two transitions), we cannot batch both transitions in one outer transaction — each call commits independently. This is the correct pattern; we call transition_case_status twice in sequence.

#### 5. AC5 mark-intake-complete: required fields
The spec says "validates required fields" but doesn't enumerate them. Based on the intake domain, required fields for intake completion are: `hospital_id`, `patient_name`, `hospital_unit`, `room_number`, `admission_date`, `primary_diagnosis_text`, `insurance_primary`. This is a reasonable interpretation since these are the minimum needed for clinical review. Documented as assumption.

#### 6. AC15: resolved_flag behavior
The spec says "resolved_flag cleared when re-submitted with valid value". "Cleared" means set to True (resolved), not set to False. The field is `resolved_flag` (resolved = True means the issue is resolved). On PATCH with a previously invalid field now having a valid value, we set `resolved_flag = True` on the matching IntakeFieldIssue.

#### 7. State machine for AC1: two transitions via transition_case_status
For creating a case:
1. Create PatientCase with status="new", commit
2. Call transition_case_status(case_id, "intake_in_progress", actor_role="system" or "intake_staff")

The STATE_MACHINE_TRANSITIONS allows `new → intake_in_progress` for ["system", "intake_staff", "admin"]. We use the authenticated user's role_key directly.

#### 8. PATCH allowlist for placement_coordinator
The spec says placement_coordinator may update `priority_level` and `assigned_coordinator_user_id`. The PATCH model also includes these. Confirmed: these are the only two fields placement_coordinator may set.

### Decisions Made

- D-intake-1: IntakeFieldIssue and CaseAssignment defined locally (not in core)
- D-intake-2: file_bytes passed in-memory to BackgroundTask, not persisted to DB
- D-intake-3: Required fields for intake completion: patient_name, hospital_id, hospital_unit, room_number, admission_date, primary_diagnosis_text, insurance_primary
- D-intake-4: ac15 resolved_flag=True means issue is resolved; set on valid re-submission
- D-intake-5: Column mapping stored as JSON list of {source_column, destination_field} objects
- D-intake-6: Import validate step stores parsed row count in ImportJob.total_rows

## CONCERNS (for orchestrator)

1. **openpyxl missing from requirements.txt** — must be added before this module can be used: `openpyxl==3.1.5` (or latest stable). Service has a try/except import with a clear RuntimeError message.
2. **IntakeFieldIssue and CaseAssignment defined locally** — need `Base.metadata.create_all()` for test setup (handled in conftest), or these tables need migrations for production.
3. **ImportJob.file_bytes not persisted** — if the server restarts between upload and commit, the bytes are lost and the ImportJob is stuck in "uploaded" or "ready" state. Acceptable per non_goals (no retry logic).
4. **Duplicate detection index** — the spec failure mode notes the query on (organization_id, patient_name, dob, hospital_id) can cause full-table scans at scale. This composite index must be added to the patient_cases migration (outside this file_scope).
5. **Router not registered in main.py** — router registration is outside file_scope; orchestrator must add `app.include_router(intake_router)` to main.py.

## Build Status
DONE_WITH_CONCERNS
- [2026-04-11T17:25:36.256Z] Created: `placementops/modules/intake/__init__.py`
- [2026-04-11T17:25:51.389Z] Created: `placementops/modules/intake/models.py`
- [2026-04-11T17:26:18.135Z] Created: `placementops/modules/intake/schemas.py`
- [2026-04-11T17:28:29.541Z] Created: `placementops/modules/intake/service.py`
- [2026-04-11T17:29:32.160Z] Created: `placementops/modules/intake/router.py`
- [2026-04-11T17:29:35.436Z] Created: `placementops/modules/intake/tests/__init__.py`
- [2026-04-11T17:30:00.410Z] Created: `placementops/modules/intake/tests/conftest.py`
- [2026-04-11T17:30:10.157Z] Created: `placementops/modules/intake/tests/conftest.py`
- [2026-04-11T17:31:33.457Z] Created: `placementops/modules/intake/tests/test_cases.py`
- [2026-04-11T17:32:24.477Z] Created: `placementops/modules/intake/tests/test_imports.py`
- [2026-04-11T17:32:45.768Z] Created: `placementops/modules/intake/tests/test_queues.py`
- [2026-04-11T17:34:04.758Z] Created: `placementops/modules/intake/tests/conftest.py`
- [2026-04-11T17:34:19.853Z] Created: `placementops/modules/intake/tests/conftest.py`
- [2026-04-11T17:34:23.574Z] Created: `placementops/modules/intake/tests/test_cases.py`
- [2026-04-11T17:34:29.367Z] Created: `placementops/modules/intake/tests/test_imports.py`
- [2026-04-11T17:34:39.146Z] Created: `placementops/modules/intake/tests/test_queues.py`
- [2026-04-11T17:35:11.111Z] Created: `placementops/modules/intake/service.py`
- [2026-04-11T17:36:42.608Z] Created: `placementops/modules/intake/service.py`
- [2026-04-11T17:36:50.237Z] Created: `placementops/modules/intake/service.py`
- [2026-04-11T17:37:02.881Z] Created: `placementops/modules/intake/router.py`
- [2026-04-11T23:43:22.074Z] Created: `placementops/modules/intake/service.py`
- [2026-04-11T23:43:25.191Z] Created: `placementops/modules/intake/service.py`
- [2026-04-11T23:43:28.570Z] Created: `placementops/modules/intake/service.py`
- [2026-04-11T23:43:31.986Z] Created: `placementops/modules/intake/service.py`
- [2026-04-11T23:43:35.482Z] Created: `placementops/modules/intake/service.py`
- [2026-04-12T14:12:53.588Z] Created: `placementops/modules/intake/tests/conftest.py`
- [2026-04-12T14:38:38.584Z] Created: `placementops/modules/intake/router.py`
- [2026-04-12T14:38:44.674Z] Created: `placementops/modules/intake/router.py`
- [2026-04-12T14:38:58.301Z] Created: `placementops/modules/intake/tests/test_cases.py`
- [2026-04-12T14:39:02.722Z] Created: `placementops/modules/intake/tests/test_cases.py`
- [2026-04-12T14:39:06.766Z] Created: `placementops/modules/intake/tests/test_cases.py`
- [2026-04-12T14:39:13.478Z] Created: `placementops/modules/intake/router.py`
- [2026-04-12T14:39:19.412Z] Created: `placementops/modules/intake/service.py`
- [2026-04-12T14:39:24.266Z] Created: `placementops/modules/intake/service.py`
- [2026-04-12T20:32:01.534Z] Created: `placementops/modules/intake/router.py`
- [2026-04-12T20:32:05.742Z] Created: `placementops/modules/intake/router.py`
- [2026-04-12T20:32:14.688Z] Created: `placementops/modules/intake/router.py`
- [2026-04-12T20:32:19.928Z] Created: `placementops/modules/intake/router.py`
- [2026-04-12T20:32:28.231Z] Created: `placementops/modules/intake/tests/test_cases.py`
- [2026-04-12T20:32:31.918Z] Created: `placementops/modules/intake/tests/test_cases.py`
- [2026-04-12T20:32:35.096Z] Created: `placementops/modules/intake/tests/test_cases.py`
- [2026-04-12T20:32:40.379Z] Created: `placementops/modules/intake/service.py`
- [2026-04-12T20:32:47.203Z] Created: `placementops/modules/intake/service.py`
- [2026-04-13T00:39:57.081Z] Created: `placementops/modules/intake/router.py`
- [2026-04-13T00:40:03.685Z] Created: `placementops/modules/intake/router.py`
- [2026-04-13T00:40:09.432Z] Created: `placementops/modules/intake/router.py`
- [2026-04-13T00:40:14.449Z] Created: `placementops/modules/intake/router.py`
