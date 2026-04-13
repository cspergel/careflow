# Node: facilities-module

## Operational Summary
- **Status:** reviewed
- **Node type:** service
- **Tracked files:** 11
- **Test files:** 0
- **Dependencies:** 2 | **Connections:** 4

## Decisions (from @forgeplan-decision markers)
- **D-facilities-1-preference-local-model**: FacilityPreference defined in facilities module not core. Why: model absent from core/models/__init__.py and no other module depends on it; avoids circular imports and keeps facilities concerns self-contained. [placementops/modules/facilities/models.py:12]
- **D-facilities-2-org-filter**: All list/get queries filter by organization_id. Why: defense-in-depth alongside RLS; prevents data leakage when RLS is disabled in dev/test environments. [placementops/modules/facilities/service.py:24]
- **D-facilities-3-upsert-pattern**: SELECT then INSERT/UPDATE for upsert. Why: SQLite in tests does not support PostgreSQL ON CONFLICT syntax; merge() does SELECT+INSERT which works across both backends. [placementops/modules/facilities/service.py:378]

## Past Findings
| Pass | Agent | Finding | Resolution |
|------|-------|---------|------------|

## Cross-References
- Depends on: core-infrastructure
- Depends on: auth-module
- Connected to: core-infrastructure
- Connected to: auth-module
- Connected to: matching-module
- Connected to: outreach-module
