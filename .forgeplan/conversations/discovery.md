# Discovery Conversation — PlacementOps
**Date:** 2026-04-10
**Mode:** Document Import (`--from Planning Docs/PlacementOps_Master_Build_Plan.md`)
**Tier:** LARGE

## Source Documents
- `Planning Docs/PlacementOps_Master_Build_Plan.md` (primary — full product spec, DB schema, API contracts, state machine, wireframes)
- `Planning Docs/PlacementOps_vs_CareFlow_Synthesis.md` (synthesis — PlacementOps as master platform, CareFlow AI as Phase 2 voice module)
- `Planning Docs/CareFlow_AI_Realtime_Voice_Architecture.md` (Phase 2 reference — Twilio + LiveKit + OpenAI Realtime stack)

## Resolved Ambiguities

| Ambiguity | Resolution |
|-----------|-----------|
| Email delivery provider | Stubbed for Phase 1. Provider (SendGrid/SES/Resend) wired in Phase 2. |
| Background jobs | FastAPI BackgroundTasks. No external broker for Phase 1. |
| Deployment target | Docker only. Host TBD. |
| Admin module structure | Consolidated `admin-surfaces` module with admin-scoped endpoints. |
| JWT handling | Next.js forwards Supabase JWT Bearer directly to FastAPI middleware. |
| Multi-tenancy | organization_id enforced at Supabase RLS + FastAPI middleware (both). |
| Operations Queue | Cross-module frontend view. Not a backend module. |
| Import formats | XLSX + CSV both supported. |
| Decline retry routing | Manual coordinator choice to re-enter matching or outreach phase. |
| Scoring algorithm | Weighted rules engine: capability match + payer fit + geography + preferences. |

## Architecture Summary
11 nodes, 7 shared models, Phase 1 only (voice AI deferred to Phase 2).
Backend: Python modular monolith (FastAPI + SQLAlchemy + Supabase).
Frontend: Next.js + shadcn/ui + Tailwind (16 wireframed screens).
