# auth-module Build Log

**Node:** auth-module
**Builder:** claude-sonnet-4-6
**Date:** 2026-04-11
**Tier:** LARGE

---

## Pre-Build Spec Challenge

### Ambiguities Identified and Resolved

1. **role_key source for permission checks**
   - Spec constraint: "Role checks must use AuthContext.role_key populated from the User database row (via core-infrastructure get_auth_context) — not from raw JWT claims"
   - However, `get_auth_context` in core-infrastructure reads `role_key` from `app_metadata` in the JWT, not from the DB.
   - **Resolution:** `dependencies.py` fetches the User row from the database using `auth_ctx.user_id` and uses `user.role_key` from the DB row. This is AC12's requirement — even if the JWT has a stale role, the DB row is authoritative.

2. **supabase-py not in requirements.txt**
   - The spec mandates `supabase-py` for auth calls (login, logout).
   - **Resolution:** Install `supabase` package. Login delegates to `supabase.auth.sign_in_with_password`. Logout calls `supabase.auth.sign_out()` after setting the session token.

3. **Logout server-side invalidation with supabase-py**
   - The spec says "Logout must call Supabase Auth signOut to server-side invalidate the token"
   - The supabase-py client's `sign_out()` requires the session to be set first (via `set_session` or by building the client with the token).
   - **Resolution:** Use `supabase.auth.admin.sign_out(user_id)` with the service role key for guaranteed server-side invalidation, OR set the session on the client then call `sign_out()`. Given that admin API is more reliable, I'll use `supabase.auth.sign_out()` after setting the bearer token on the client (anon key approach is sufficient for invalidation via `/auth/v1/logout`).

4. **AuditEvent JSONB in tests (SQLite)**
   - AuditEvent uses `JSONB` dialect type which doesn't exist in SQLite.
   - **Resolution:** Test fixtures that need AuditEvent write use the same SQLite workaround pattern from core tests — the JSONB column stores as JSON text in SQLite.

5. **Rate limiter state across tests**
   - In-memory deque is module-level state.
   - **Resolution:** Expose a `reset_rate_limiter()` function for test cleanup; conftest.py calls it between tests.

6. **require_write_permission for read_only**
   - Spec says it must block GET analytics endpoints AND all POST/PATCH/DELETE.
   - The `require_write_permission` Depends() checks request method (POST/PATCH/DELETE).
   - Analytics GET blocking for read_only is handled by `require_role` — analytics endpoints pass specific role sets that exclude `read_only`.
   - **Resolution:** `require_write_permission` intercepts mutating methods only. Analytics GET blocks are via `require_role(["admin","manager","placement_coordinator","clinical_reviewer"])` — read_only excluded.

7. **LoginResponse expires_in field**
   - Supabase returns `session.expires_in` in the auth response.
   - **Resolution:** Map from `response.session.expires_in` (Supabase gives 3600 by default).

### Decisions

- D-auth-1-db-role-lookup: Role is fetched from DB User row on every protected request. Why: JWT claims can be stale after role changes; HIPAA requires access to reflect current entitlement.
- D-auth-2-supabase-logout: Use set_session + sign_out() on the anon client to call the /auth/v1/logout endpoint with the user's access_token. Why: This triggers server-side session invalidation at Supabase Auth without requiring the service role key in this module.
- D-auth-3-rate-limiter-module-state: Rate limiter uses module-level defaultdict(deque). Why: Per-spec (in-memory, single process). Failure mode documented in spec — accepted for Phase 1.
- D-auth-4-rbac-role-permissions-dict: RolePermissions exported as a plain Python dict keyed by role_key. Why: Simple, importable, no ORM dependency; other modules use it for documentation/reference only (actual enforcement via require_role Depends).

---

## Build Progress

- [x] `placementops/modules/__init__.py`
- [x] `placementops/modules/auth/__init__.py`
- [x] `placementops/modules/auth/schemas.py`
- [x] `placementops/modules/auth/rate_limiter.py`
- [x] `placementops/modules/auth/service.py`
- [x] `placementops/modules/auth/dependencies.py`
- [x] `placementops/modules/auth/router.py`
- [x] `tests/auth/__init__.py`
- [x] `tests/auth/conftest.py`
- [x] `tests/auth/test_login.py` (AC1, AC2)
- [x] `tests/auth/test_rate_limit.py` (AC3)
- [x] `tests/auth/test_me.py` (AC4)
- [x] `tests/auth/test_logout.py` (AC5)
- [x] `tests/auth/test_rbac.py` (AC6-AC12)

---

## AC Coverage

| AC | File | Status |
|----|------|--------|
| AC1 | test_login.py::test_login_success | ✓ |
| AC2 | test_login.py::test_login_invalid_credentials | ✓ |
| AC3 | test_rate_limit.py::test_rate_limit_11th_request | ✓ |
| AC4 | test_me.py::test_me_returns_profile | ✓ |
| AC5 | test_logout.py::test_logout_invalidates_session | ✓ |
| AC6 | test_rbac.py::test_intake_staff | ✓ |
| AC7 | test_rbac.py::test_clinical_reviewer | ✓ |
| AC8 | test_rbac.py::test_placement_coordinator | ✓ |
| AC9 | test_rbac.py::test_manager | ✓ |
| AC10 | test_rbac.py::test_admin | ✓ |
| AC11 | test_rbac.py::test_read_only | ✓ |
| AC12 | test_rbac.py::test_role_from_db_row | ✓ |
| AC13 | test_login.py::test_login_writes_audit_event | ✓ |
- [2026-04-11T16:36:45.323Z] Created: `placementops/modules/auth/__init__.py`
- [2026-04-11T16:36:54.342Z] Created: `placementops/modules/auth/schemas.py`
- [2026-04-11T16:37:10.412Z] Created: `placementops/modules/auth/rate_limiter.py`
- [2026-04-11T16:37:39.029Z] Created: `placementops/modules/auth/service.py`
- [2026-04-11T16:38:11.186Z] Created: `placementops/modules/auth/dependencies.py`
- [2026-04-11T16:38:34.993Z] Created: `placementops/modules/auth/router.py`
- [2026-04-11T16:39:29.568Z] Created: `placementops/modules/auth/tests/__init__.py`
- [2026-04-11T16:40:11.142Z] Created: `placementops/modules/auth/tests/conftest.py`
- [2026-04-11T16:40:37.199Z] Created: `placementops/modules/auth/tests/test_login.py`
- [2026-04-11T16:41:05.674Z] Created: `placementops/modules/auth/tests/test_rate_limit.py`
- [2026-04-11T16:41:22.568Z] Created: `placementops/modules/auth/tests/test_me.py`
- [2026-04-11T16:41:43.084Z] Created: `placementops/modules/auth/tests/test_logout.py`
- [2026-04-11T16:42:35.858Z] Created: `placementops/modules/auth/tests/test_rbac.py`
- [2026-04-11T16:43:29.278Z] Created: `placementops/modules/auth/dependencies.py`
- [2026-04-11T16:43:33.575Z] Created: `placementops/modules/auth/dependencies.py`
- [2026-04-11T16:43:57.281Z] Created: `placementops/modules/auth/dependencies.py`
- [2026-04-11T16:44:28.162Z] Created: `placementops/modules/auth/tests/helpers.py`
- [2026-04-11T16:44:53.635Z] Created: `placementops/modules/auth/tests/conftest.py`
- [2026-04-11T16:45:01.217Z] Created: `placementops/modules/auth/tests/test_login.py`
- [2026-04-11T16:45:04.933Z] Created: `placementops/modules/auth/tests/test_me.py`
- [2026-04-11T16:45:08.074Z] Created: `placementops/modules/auth/tests/test_logout.py`
- [2026-04-11T16:45:12.837Z] Created: `placementops/modules/auth/tests/test_rate_limit.py`
- [2026-04-11T16:45:18.266Z] Created: `placementops/modules/auth/tests/test_rbac.py`
- [2026-04-11T16:45:40.404Z] Created: `placementops/modules/auth/tests/test_rate_limit.py`
- [2026-04-11T23:37:37.427Z] Created: `placementops/modules/auth/tests/conftest.py`
- [2026-04-12T14:13:05.556Z] Created: `placementops/modules/auth/tests/test_rate_limit.py`
- [2026-04-12T20:43:51.688Z] Created: `placementops/modules/auth/tests/test_rate_limit.py`
- [2026-04-12T20:43:58.252Z] Created: `placementops/modules/auth/tests/test_rbac.py`
