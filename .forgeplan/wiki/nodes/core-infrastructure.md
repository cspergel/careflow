# Node: core-infrastructure

## Operational Summary
- **Status:** reviewed
- **Node type:** database
- **Tracked files:** 62
- **Test files:** 0
- **Dependencies:** 0 | **Connections:** 9
- **Recent issues:** review/reviewer: AC8 (partial) | review/reviewer: 3

## Decisions (from @forgeplan-decision markers)
- **D-core-4-select-for-update**: SELECT FOR UPDATE on PatientCase before transition. Why: prevents lost updates under concurrent transitions (two coordinators racing to close the same case). [placementops/core/state_machine.py:15]
- **D-core-1-nullpool-supavisor**: NullPool with statement_cache_size=0 and prepared_statement_cache_size=0. Why: Supavisor transaction mode (port 6543) cannot maintain prepared statements across transactions; NullPool hands connection management to Supavisor entirely. [placementops/core/database.py:8]
- **D-core-2-jwt-alg-detection**: Determine algorithm from JWT header alg field. Why: Supabase project may use either HS256 (pre-Oct-2025) or ES256 (post-Oct-2025); checking the header allows a single middleware to support both without config changes. [placementops/core/auth.py:12]

## Past Findings
| Pass | Agent | Finding | Resolution |
|------|-------|---------|------------|
| review | reviewer | AC8 (partial) | `placementops/core/` (entire scope) |
| review | reviewer | 3 | AC10 (partial) |

## Cross-References
- Connected to: auth-module
- Connected to: intake-module
- Connected to: clinical-module
- Connected to: facilities-module
- Connected to: matching-module
- Connected to: outreach-module
- Connected to: outcomes-module
- Connected to: analytics-module
- Connected to: admin-surfaces
