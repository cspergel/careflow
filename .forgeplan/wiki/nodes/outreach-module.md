# Node: outreach-module

## Operational Summary
- **Status:** reviewed
- **Node type:** service
- **Tracked files:** 10
- **Test files:** 0
- **Dependencies:** 3 | **Connections:** 5

## Decisions (from @forgeplan-decision markers)
- **D-outreach-1-sandboxed-env**: jinja2.sandbox.SandboxedEnvironment for all template rendering. Why: bare Environment allows __class__.__mro__ traversal and other SSTI vectors; SandboxedEnvironment is the only safe choice for user-influenced template content. [placementops/modules/outreach/template_renderer.py:16]
- **D-outreach-2-system-role-advance**: Use actor_role="system" for outreach_pending_approval→outreach_in_progress and outreach_in_progress→pending_facility_response. Why: state machine only allows role "system" for these transitions; outreach service orchestrates internally, not via a human actor. [placementops/modules/outreach/service.py:33]
- **D-outreach-4-bypass-atomicity**: Defer commit until first transition_case_status call. Why: removing the early commit at this point means the OutreachAction and audit row are flushed (visible within the session) but not yet committed; the first transition_case_status call will commit them together with the first case-status change, achieving the atomicity required by F3. [placementops/modules/outreach/service.py:310]
- **D-outreach-3-405-explicit-handlers**: Explicit POST/PATCH/DELETE handlers on /templates/outreach return 405. Why: FastAPI does not automatically return 405 for unregistered methods; explicit handlers with raise HTTPException(405) are required to satisfy AC10's method-not-allowed constraint. [placementops/modules/outreach/router.py:27]

## Past Findings
| Pass | Agent | Finding | Resolution |
|------|-------|---------|------------|

## Cross-References
- Depends on: core-infrastructure
- Depends on: auth-module
- Depends on: matching-module
- Connected to: core-infrastructure
- Connected to: auth-module
- Connected to: matching-module
- Connected to: outcomes-module
- Connected to: admin-surfaces
