# Node: auth-module

## Operational Summary
- **Status:** reviewed
- **Node type:** service
- **Tracked files:** 14
- **Test files:** 0
- **Dependencies:** 1 | **Connections:** 9
- **Recent issues:** review/reviewer: `router.py` | review/reviewer: `dependencies.py` | review/reviewer: `service.py`

## Decisions (from @forgeplan-decision markers)
- **D-auth-3-rate-limiter-module-state**: In-process defaultdict(deque) per spec. Why: spec explicitly describes in-memory sliding window; distributed state is a non-goal for Phase 1. [placementops/modules/auth/rate_limiter.py:12]
- **D-auth-4-rbac-role-permissions-dict**: RolePermissions exported as plain dict keyed by role_key. Why: importable, no ORM dependency; actual enforcement via require_role Depends. [placementops/modules/auth/service.py:14]
- **D-auth-2-supabase-logout**: Direct httpx POST to /auth/v1/logout. Why: supabase-py set_session() requires both access+refresh tokens; we only have the access token at logout time; direct REST call is simpler and more reliable. [placementops/modules/auth/service.py:115]
- **D-auth-1-db-role-lookup**: require_role fetches User row from DB on every call. Why: JWT role_key in app_metadata can be stale after a role change; DB row is always authoritative per AC12. [placementops/modules/auth/dependencies.py:30]

## Past Findings
_Showing latest 10 of 14 findings._
| Pass | Agent | Finding | Resolution |
|------|-------|---------|------------|
| review | reviewer | `router.py` | Present (line 1) |
| review | reviewer | `dependencies.py` | Present (line 1) |
| review | reviewer | `service.py` | Present (line 1) |
| review | reviewer | `schemas.py` | Present (line 1) |
| review | reviewer | `rate_limiter.py` | Present (line 1) |
| review | reviewer | `__init__.py` | Present (line 1) |
| review | reviewer | `tests/__init__.py` | Present (line 1) |
| review | reviewer | `tests/conftest.py` | Present (line 1) |
| review | reviewer | `tests/helpers.py` | Present (line 1) |
| review | reviewer | `tests/test_login.py` | Present (line 1) |

## Cross-References
- Depends on: core-infrastructure
- Connected to: core-infrastructure
- Connected to: intake-module
- Connected to: clinical-module
- Connected to: facilities-module
- Connected to: matching-module
- Connected to: outreach-module
- Connected to: outcomes-module
- Connected to: analytics-module
- Connected to: admin-surfaces
