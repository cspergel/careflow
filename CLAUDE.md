# ForgePlan Project — Claude Code Instructions

This project uses **ForgePlan Core**, an architecture-governed build harness. ForgePlan works **architecture down, not code up** — the architecture is defined first, then enforced as code is generated. The `.forgeplan/` directory contains the project manifest, node specs, and build state.

## Critical Rules

1. **Always check for an active operation** before writing code. Read `.forgeplan/state.json` to see if a node is currently being built, reviewed, revised, or swept.
2. **Never write files outside the active node's `file_scope`** directory. The manifest defines which directories belong to which node. Permitted exceptions depend on the active operation:
   - **Building:** `.forgeplan/conversations/nodes/[node].md`, `.forgeplan/state.json`, `src/shared/types/index.ts` (creation only), `.env.example`, `package.json`
   - **Reviewing:** `.forgeplan/reviews/[node].md` and `.forgeplan/state.json` only
   - **Revising:** `.forgeplan/specs/[node].yaml`, `.forgeplan/manifest.yaml`, `.forgeplan/state.json`, and `src/shared/types/index.ts`
   - **Sweeping:** `.forgeplan/sweeps/`, `.forgeplan/specs/`, `.forgeplan/manifest.yaml`, `.forgeplan/state.json`, and node files within the active node's scope
3. **Never redefine shared models locally.** Shared models are defined canonically in `.forgeplan/manifest.yaml`. Import them — do not create local copies.
4. **Follow the node spec exactly.** Each node's spec at `.forgeplan/specs/[node].yaml` defines what to build, what NOT to build (non_goals), and how to verify it (acceptance_criteria).
5. **Use anchor comments in source code files** (`.ts`, `.js`, `.tsx`, `.jsx`):
   - `// @forgeplan-node: [node-id]` at the top of every source file
   - `// @forgeplan-spec: [AC1]` on functions implementing acceptance criteria
   - Do not add anchor comments to non-source files (JSON, YAML, config)
6. **Phase enforcement:** Only build nodes in the current `build_phase`. Future-phase nodes are blocked by the enforcement layer. Use fail-closed stubs for security dependencies from future phases.

## Available Commands

| Command | What it does |
|---------|-------------|
| `/forgeplan:discover` | Architecture discovery — guided conversation, template, or `--from` document import |
| `/forgeplan:spec [node\|--all]` | Generate detailed specs (phase-aware depth) |
| `/forgeplan:build [node\|--all]` | Build a node with enforcement (phase-gated) |
| `/forgeplan:review [node]` | 7-dimension spec-diff review |
| `/forgeplan:sweep [--cross-check]` | Tier-aware parallel sweep (3-5 agents: Adversary, Contractualist, Pathfinder, Structuralist, Skeptic) |
| `/forgeplan:deep-build` | Full autonomous pipeline: build → verify → review → sweep → certify (tier-aware, phase-aware) |
| `/forgeplan:greenfield [description\|--from doc.md]` | Full pipeline: discover → design review → research → spec → plan review → build → code review → sweep → certify |
| `/forgeplan:ingest [--force]` | Bring existing codebase under ForgePlan governance |
| `/forgeplan:configure` | Set up cross-model review (Codex/GPT/Gemini) |
| `/forgeplan:next` | Dependency-aware next recommendation (phase-filtered) |
| `/forgeplan:revise [node]` | Change impact analysis + propagation |
| `/forgeplan:split [node]` | Decompose a node into finer-grained nodes |
| `/forgeplan:integrate` | Cross-node interface verification (same-phase and cross-phase) |
| `/forgeplan:recover` | Fix crashed/stuck operations |
| `/forgeplan:status` | Full project status with phase progress |
| `/forgeplan:research [topic]` | Research packages, licenses, patterns, architecture |
| `/forgeplan:measure` | Code quality metrics (broken refs, stubs, duplicates) |
| `/forgeplan:affected [model]` | Which nodes use a shared model — impact analysis |
| `/forgeplan:validate` | Check manifest/specs for cycles, orphans, consistency |
| `/forgeplan:regen-types` | Rebuild shared TypeScript types from manifest |
| `/forgeplan:guide` | Where am I? Best next step with explanations |
| `/forgeplan:help` | All available commands |

## Key Files

- `.forgeplan/manifest.yaml` — Central architecture file: nodes, shared models, tech stack, connections, phases
- `.forgeplan/state.json` — Current session state, active node, build progress, sweep state
- `.forgeplan/specs/[node].yaml` — Detailed spec for each node (the enforcement contract)
- `.forgeplan/config.yaml` — Cross-model review configuration (optional)
- `.forgeplan/plans/implementation-plan.md` — Implementation plan from Architect Planner mode
- `.forgeplan/conversations/discovery.md` — Architecture discovery rationale
- `.forgeplan/reviews/[node].md` — Review reports
- `.forgeplan/sweeps/` — Sweep and cross-model verification reports
- `.forgeplan/wiki/` — Compiled knowledge base (MEDIUM/LARGE only)
- `DESIGN.md` / `docs/DESIGN.md` — Optional product/design direction for frontend work
