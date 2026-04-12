# Node: admin-surfaces

## Operational Summary
- **Status:** reviewed
- **Node type:** service
- **Tracked files:** 10
- **Test files:** 0
- **Dependencies:** 4 | **Connections:** 4

## Decisions (from @forgeplan-decision markers)
- **D-admin-1-allowed-variables-allowlist**: Hard-coded allowlist in service constant. Why: template allowed_variables must be validated server-side to prevent unsafe variable injection into outreach templates; a central constant is the single source of truth. [placementops/modules/admin/service.py:38]

## Past Findings
| Pass | Agent | Finding | Resolution |
|------|-------|---------|------------|

## Cross-References
- Depends on: core-infrastructure
- Depends on: auth-module
- Depends on: intake-module
- Depends on: outreach-module
- Connected to: core-infrastructure
- Connected to: auth-module
- Connected to: intake-module
- Connected to: outreach-module
