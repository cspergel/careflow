# Build Log: core-infrastructure

**Node:** core-infrastructure
**Date:** 2026-04-11
**Builder:** claude-sonnet-4-6

## Pre-Build Spec Challenge

### Ambiguities Reviewed and Assumptions Documented

1. **prepared_statement_cache_size**: Research recommends adding `prepared_statement_cache_size: 0` in connect_args alongside `statement_cache_size: 0`. The spec only mentions `statement_cache_size=0`. Assumption: include both for full Supavisor compatibility.

2. **JWT audience claim**: Research shows Supabase JWTs use `audience="authenticated"`. The spec doesn't specify. Assumption: validate `aud="authenticated"` for HS256; for ES256 via JWKS, use PyJWKClient which handles audience separately.

3. **ES256 JWKS fallback**: When `SUPABASE_JWKS_URL` is set, the algorithm in the JWT header determines which path to take. Assumption: check `alg` in unverified header — if ES256 and JWKS URL set, use PyJWKClient; if HS256 or JWKS URL not set, use shared secret.

4. **TenantMixin**: CaseStatusHistory spec references `TenantMixin`. Assumption: create a simple `TenantMixin` that adds `organization_id` as a Mapped column. CaseStatusHistory will use it.

5. **Table names**: Using SQLAlchemy convention — `patient_cases`, `facilities`, `facility_capabilities`, etc. (plural snake_case).

6. **alembic env.py `run_sync`**: Research confirms async Alembic needs `run_sync` to run migrations synchronously against the direct URL.

7. **Seed data in migration vs separate script**: Spec says migration `0003_seed_data.py` or `seed.py` separately. Assumption: separate `alembic/seed.py` plus a `0003_seed_data.py` migration that calls the same data.

8. **check_case_not_closed as Depends()**: The spec says it should be injectable via FastAPI Depends. Assumption: implement as a dependency factory that takes `case_id: UUID` as a path parameter.

9. **PHI-safe logging**: The spec mentions PHI-safe logging config in middleware.py. Assumption: implement a log filter that redacts known PHI field names from log records.

10. **`server_settings: {"jit": "off"}`**: Research recommends this for Supavisor compatibility. Adding to connect_args.

## Build Progress

- [ ] requirements.txt
- [ ] .env.example
- [ ] docker-compose.yml
- [ ] placementops/__init__.py
- [ ] placementops/core/__init__.py
- [ ] placementops/core/database.py
- [ ] placementops/core/auth.py
- [ ] placementops/core/state_machine.py
- [ ] placementops/core/events.py
- [ ] placementops/core/middleware.py
- [ ] placementops/core/models/__init__.py
- [ ] placementops/core/models/patient_case.py
- [ ] placementops/core/models/facility.py
- [ ] placementops/core/models/facility_capabilities.py
- [ ] placementops/core/models/facility_insurance_rule.py
- [ ] placementops/core/models/facility_contact.py
- [ ] placementops/core/models/user.py
- [ ] placementops/core/models/outreach_action.py
- [ ] placementops/core/models/outreach_template.py
- [ ] placementops/core/models/clinical_assessment.py
- [ ] placementops/core/models/facility_match.py
- [ ] placementops/core/models/import_job.py
- [ ] placementops/core/models/placement_outcome.py
- [ ] placementops/core/models/audit_event.py
- [ ] placementops/core/models/case_status_history.py
- [ ] placementops/core/models/reference_tables.py
- [ ] main.py
- [ ] alembic.ini
- [ ] alembic/env.py
- [ ] alembic/versions/0001_initial_tables.py
- [ ] alembic/versions/0002_rls_policies.py
- [ ] alembic/versions/0003_seed_data.py
- [ ] alembic/seed.py
- [ ] tests/core/conftest.py
- [ ] tests/core/test_auth_middleware.py
- [ ] tests/core/test_tenant_isolation.py
- [ ] tests/core/test_transitions.py
- [ ] tests/core/test_audit_immutability.py
- [ ] tests/core/test_audit_events.py
- [ ] tests/core/test_closed_case.py
- [ ] tests/core/test_activity_events.py
- [ ] tests/core/test_no_phi_in_logs.py
- [2026-04-11T14:39:17.909Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/.forgeplan/conversations/nodes/core-infrastructure.md`
- [2026-04-11T14:39:25.096Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/requirements.txt`
- [2026-04-11T14:39:36.135Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/.env.example`
- [2026-04-11T14:39:42.165Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/docker-compose.yml`
- [2026-04-11T14:39:47.281Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/__init__.py`
- [2026-04-11T14:39:52.156Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/core/__init__.py`
- [2026-04-11T14:40:12.309Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/core/database.py`
- [2026-04-11T14:40:25.675Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/core/models/reference_tables.py`
- [2026-04-11T14:40:35.064Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/core/models/user.py`
- [2026-04-11T14:40:49.554Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/core/models/patient_case.py`
- [2026-04-11T14:41:52.252Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/core/models/facility.py`
- [2026-04-11T14:42:04.392Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/core/models/facility_capabilities.py`
- [2026-04-11T14:42:14.631Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/core/models/facility_insurance_rule.py`
- [2026-04-11T14:42:23.203Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/core/models/facility_contact.py`
- [2026-04-11T14:42:35.177Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/core/models/outreach_action.py`
- [2026-04-11T14:42:43.072Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/core/models/outreach_template.py`
- [2026-04-11T14:43:15.327Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/core/models/clinical_assessment.py`
- [2026-04-11T14:43:35.622Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/core/models/facility_match.py`
- [2026-04-11T14:43:53.162Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/core/models/import_job.py`
- [2026-04-11T14:44:07.112Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/core/models/placement_outcome.py`
- [2026-04-11T14:44:21.027Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/core/models/audit_event.py`
- [2026-04-11T14:44:32.050Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/core/models/case_status_history.py`
- [2026-04-11T14:44:57.319Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/core/models/__init__.py`
- [2026-04-11T14:45:30.111Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/core/auth.py`
- [2026-04-11T14:47:03.423Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/core/events.py`
- [2026-04-11T14:47:37.482Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/core/state_machine.py`
- [2026-04-11T14:47:59.969Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/core/middleware.py`
- [2026-04-11T14:48:14.951Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/main.py`
- [2026-04-11T14:48:23.629Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/alembic.ini`
- [2026-04-11T14:48:40.812Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/alembic/env.py`
- [2026-04-11T15:55:00.251Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/alembic/versions/0001_initial_tables.py`
- [2026-04-11T15:55:24.829Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/alembic/versions/0002_rls_policies.py`
- [2026-04-11T15:55:34.923Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/alembic/versions/0003_seed_data.py`
- [2026-04-11T15:55:55.364Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/alembic/seed.py`
- [2026-04-11T15:56:02.899Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/alembic/versions/0003_seed_data.py`
- [2026-04-11T15:57:28.743Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/tests/__init__.py`
- [2026-04-11T15:57:36.434Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/tests/core/__init__.py`
- [2026-04-11T15:58:09.411Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/tests/core/conftest.py`
- [2026-04-11T16:04:53.927Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/tests/core/test_auth_middleware.py`
- [2026-04-11T16:05:14.078Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/tests/core/test_tenant_isolation.py`
- [2026-04-11T16:07:58.250Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/tests/core/test_transitions.py`
- [2026-04-11T16:08:15.891Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/tests/core/test_audit_immutability.py`
- [2026-04-11T16:09:00.286Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/tests/core/test_audit_events.py`
- [2026-04-11T16:09:21.584Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/tests/core/test_closed_case.py`
- [2026-04-11T16:09:47.922Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/tests/core/test_activity_events.py`
- [2026-04-11T16:10:17.839Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/tests/core/test_no_phi_in_logs.py`
- [2026-04-11T16:10:31.642Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/tests/core/test_org_metadata_source.py`
- [2026-04-11T16:10:42.404Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/pyproject.toml`
- [2026-04-11T16:10:48.601Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/requirements.txt`
- [2026-04-11T16:11:25.455Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/placementops/core/database.py`
- [2026-04-11T16:11:39.992Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/Dockerfile`
- [2026-04-11T16:11:52.329Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/tests/core/conftest.py`
- [2026-04-11T16:12:20.434Z] Created: `../../../../../c/Users/drcra/Documents/Coding Projects/Placement-ops-careflow/tests/core/conftest.py`
- [2026-04-11T16:33:31.218Z] Edited: `alembic/seed.py`
- [2026-04-11T23:21:19.024Z] Edited: `tests/core/conftest.py`
- [2026-04-11T23:41:12.244Z] Edited: `placementops/core/state_machine.py`
- [2026-04-11T23:53:08.708Z] Edited: `placementops/core/models/outreach_template.py`
- [2026-04-11T23:53:12.321Z] Created: `placementops/core/models/outreach_template.py`
- [2026-04-11T23:53:17.347Z] Edited: `placementops/core/models/audit_event.py`
- [2026-04-11T23:53:20.723Z] Created: `placementops/core/models/audit_event.py`
- [2026-04-11T23:53:30.723Z] Edited: `placementops/core/models/import_job.py`
- [2026-04-11T23:53:33.809Z] Created: `placementops/core/models/import_job.py`
- [2026-04-11T23:53:40.695Z] Edited: `placementops/core/models/facility_match.py`
- [2026-04-11T23:53:44.035Z] Created: `placementops/core/models/facility_match.py`
- [2026-04-12T13:18:24.423Z] Edited: `main.py`
- [2026-04-12T13:19:42.477Z] Created: `placementops/core/state_machine.py`
- [2026-04-12T13:44:23.037Z] Edited: `placementops/core/models/clinical_assessment.py`
- [2026-04-12T13:45:34.052Z] Edited: `alembic/versions/0001_initial_tables.py`
- [2026-04-12T13:52:42.245Z] Created: `alembic/versions/0001_initial_tables.py`
- [2026-04-12T13:52:46.839Z] Created: `placementops/core/models/clinical_assessment.py`
- [2026-04-12T13:54:14.694Z] Created: `alembic/versions/0004_rename_clinical_assessment_flags.py`
- [2026-04-12T20:30:04.946Z] Edited: `alembic/versions/0002_rls_policies.py`
- [2026-04-12T20:30:13.672Z] Created: `alembic/versions/0002_rls_policies.py`
- [2026-04-12T20:30:21.698Z] Created: `alembic/versions/0002_rls_policies.py`
- [2026-04-12T20:30:26.102Z] Edited: `placementops/core/database.py`
- [2026-04-12T20:30:31.774Z] Created: `placementops/core/database.py`
- [2026-04-12T20:30:36.213Z] Edited: `placementops/core/auth.py`
- [2026-04-12T20:30:47.985Z] Created: `placementops/core/auth.py`
