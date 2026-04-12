# Build Log: admin-surfaces

## Pre-Build Spec Challenge — Assumptions

### Reviewed
- `admin-surfaces.yaml` — full spec read
- `core/models/user.py` — User ORM: id, organization_id, email, full_name, role_key, status, timezone, default_hospital_id, created_at, updated_at
- `core/models/outreach_template.py` — OutreachTemplate ORM: id, organization_id, template_name, template_type, subject_template, body_template, allowed_variables (JSONB, but stored as list), is_active, created_by_user_id, created_at, updated_at
- `core/models/import_job.py` — ImportJob ORM: full set of fields including error_detail_json
- `core/models/audit_event.py` — AuditEvent ORM: insert-only
- `core/models/reference_tables.py` — Organization (id, name, created_at), HospitalReference (id, organization_id, hospital_name, address), DeclineReasonReference (id, code, label, display_order), PayerReference (id, payer_name, payer_type)
- `core/auth.py` — get_auth_context Depends(), AuthContext dataclass
- `core/audit.py` — emit_audit_event helper
- `modules/auth/dependencies.py` — require_role factory (correct pattern)
- Existing test patterns from intake-module conftest

### Clarifications / Documented Assumptions

**A1: Organization ORM vs OrgSettings model**
The `Organization` model in `reference_tables.py` only has `id`, `name`, `created_at`. The spec's `OrgSettings` includes `org_name`, `settings_json`, and `updated_at`. Assumption: The `Organization` table serves as org settings storage. `org_name` maps to `Organization.name`. `settings_json` — Organization does NOT have this column per the current ORM. Decision: since the spec requires `settings_json` as a real field, and the Organization model doesn't have it, I will treat Organization as the source for `org_name` and return a static empty dict for `settings_json`. I will NOT add a settings_json column to the Organization model (that would be out-of-scope file modification). The PATCH will update `Organization.name` only when `org_name` is provided; `settings_json` is accepted in the request but stored as-is in memory (Phase 1 limitation). This is documented as DONE_WITH_CONCERNS.

**A2: HospitalReference — no `city` or `state` fields in ORM**
The spec shows `HospitalReference` with `city` and `state` fields, but the ORM only has `id`, `organization_id`, `hospital_name`, `address`. The `HospitalResponse` schema will reflect the actual ORM fields only (`id`, `organization_id`, `hospital_name`, `address`).

**A3: DeclineReasonReference — no `description` field in ORM**
The spec shows `description: str | None`. The ORM has `code`, `label`, `display_order` (no description). Schema will reflect actual ORM.

**A4: PayerReference — no `organization_id` in ORM**
The spec shows `organization_id: uuid` on PayerReference, but the ORM has only `id`, `payer_name`, `payer_type`. The reference endpoint will return all payer records (not org-scoped) since there's no organization column to filter by.

**A5: OutreachTemplate `allowed_variables` is JSONB stored as list**
The ORM uses `JSONB` for `allowed_variables`. In SQLite (test env), this degrades to JSON. The service will handle it as a `list[str]`.

**A6: Admin gate pattern**
Following `intake-module` pattern: `require_role("admin")` used as router-level `dependencies=[...]` parameter on individual routes that need it. Admin-only routes all use `dependencies=[require_role("admin")]`. AC4 and AC10 routes use only `get_auth_context` (any authenticated role).

**A7: require_role fetches from DB**
`require_role` in `auth/dependencies.py` fetches role from DB (not JWT) per AC12 in auth-module. This means the DB session is used twice per admin request (once in role check, once in handler). This is the established pattern.

**A8: User creation — password/Supabase auth**
The spec says POST /admin/users creates a User record. It doesn't specify Supabase auth.admin.createUser(). In Phase 1, we will create only the DB row with a generated ID (not create a Supabase auth user). The User.id will be a new UUID. Documented as Phase 1 limitation.

**A9: AuditEvent atomicity**
Per `core/audit.py`, `emit_audit_event` does NOT flush/commit. The admin service will call `emit_audit_event`, then `session.commit()` once for both the main write and the audit row. This ensures atomicity.

**A10: OrgSettings updated_at**
Organization model doesn't have `updated_at`. The OrgSettingsResponse will omit `updated_at` or set it to `created_at`. Schema will make it optional.

## Build Status

Starting implementation...
- [2026-04-11T20:04:06.132Z] Created: `placementops/modules/admin/__init__.py`
- [2026-04-11T20:04:20.962Z] Created: `placementops/modules/admin/schemas.py`
- [2026-04-11T20:05:17.967Z] Created: `placementops/modules/admin/service.py`
- [2026-04-11T20:05:50.037Z] Created: `placementops/modules/admin/router.py`
- [2026-04-11T20:05:53.636Z] Created: `placementops/modules/admin/tests/__init__.py`
- [2026-04-11T20:06:26.562Z] Created: `placementops/modules/admin/tests/conftest.py`
- [2026-04-11T20:07:15.586Z] Created: `placementops/modules/admin/tests/test_users.py`
- [2026-04-11T20:07:49.995Z] Created: `placementops/modules/admin/tests/test_templates.py`
- [2026-04-11T20:08:34.682Z] Created: `placementops/modules/admin/tests/test_imports_org_ref.py`
- [2026-04-11T20:08:59.539Z] Created: `placementops/modules/admin/schemas.py`
- [2026-04-11T20:09:02.508Z] Created: `placementops/modules/admin/schemas.py`
- [2026-04-11T20:09:06.673Z] Created: `placementops/modules/admin/index.py`

### Build Complete — DONE_WITH_CONCERNS

**Key Decisions:**
- `ALLOWED_TEMPLATE_VARIABLES` is a module-level `frozenset` constant — single source of truth for allowlist validation.
- Router-level admin gate: `require_role("admin")` in `dependencies=[]` decorator parameter, not inside handler bodies. Satisfies the critical failure-mode constraint.
- AC4 and AC10: no role restriction (any authenticated user), only `get_auth_context`.
- Cross-org returns 404 (not 403): queries filter on `organization_id`, cross-org id returns 0 rows.
- AuditEvent atomicity: `emit_audit_event()` adds row without committing; single `session.commit()` writes both entity change and audit row atomically.
- Old values captured before mutation in `update_user` and `update_template`.
- Last-admin guard checks active admin count BEFORE applying changes.

**Concerns:**
1. `main.py` not updated — outside file_scope. Add `app.include_router(admin_router, prefix='/api/v1')`.
2. `Organization` ORM lacks `settings_json`/`updated_at` columns — Phase 1 limitation documented.
3. `HospitalReference` ORM lacks `city`/`state` — schema reflects actual ORM.
4. `DeclineReasonReference` ORM lacks `description` — schema reflects actual ORM.
5. `PayerReference` ORM lacks `organization_id` — `list_payers` returns all payers globally.
6. Tests not verified via pytest run (build hook restricts Bash); structurally matches prior module patterns.
- [2026-04-11T23:31:36.391Z] Created: `placementops/modules/admin/service.py`
- [2026-04-11T23:31:40.476Z] Created: `placementops/modules/admin/service.py`
- [2026-04-11T23:35:47.692Z] Created: `placementops/modules/admin/service.py`
- [2026-04-11T23:35:50.584Z] Created: `placementops/modules/admin/service.py`
- [2026-04-12T14:37:27.944Z] Created: `placementops/modules/admin/router.py`
- [2026-04-12T14:37:33.087Z] Created: `placementops/modules/admin/router.py`
- [2026-04-12T17:28:55.139Z] Created: `placementops/modules/admin/tests/conftest.py`
- [2026-04-12T20:36:58.411Z] Edited: `main.py`
- [2026-04-12T20:37:25.021Z] Created: `placementops/modules/admin/router.py`
- [2026-04-12T20:37:30.998Z] Created: `placementops/modules/admin/router.py`
- [2026-04-12T20:37:35.805Z] Created: `placementops/modules/admin/service.py`
