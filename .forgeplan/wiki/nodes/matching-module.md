# Node: matching-module

## Operational Summary
- **Status:** reviewed
- **Node type:** service
- **Tracked files:** 15
- **Test files:** 0
- **Dependencies:** 4 | **Connections:** 5

## Decisions (from @forgeplan-decision markers)
- **D-matching-1-haversine-step-function**: Haversine step function (≤10mi=1.0, ≤25mi=0.7, ≤50mi=0.4, >50mi=0.1). Why: spec mandates discrete bins for predictable, auditable geography scoring rather than continuous decay. [placementops/modules/matching/engine.py:32]
- **D-matching-2-lru-cache-zip-lookup**: @functools.lru_cache on zip_to_latlon to avoid redundant zipcodes I/O within one scoring run. Why: a single match generation iterates N facilities per case; ZIP lookup is per-case not per-facility so caching avoids N identical lookups. [placementops/modules/matching/engine.py:33]

## Past Findings
| Pass | Agent | Finding | Resolution |
|------|-------|---------|------------|

## Cross-References
- Depends on: core-infrastructure
- Depends on: auth-module
- Depends on: clinical-module
- Depends on: facilities-module
- Connected to: core-infrastructure
- Connected to: auth-module
- Connected to: clinical-module
- Connected to: facilities-module
- Connected to: outreach-module
