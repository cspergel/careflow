# Architectural Decisions

## ADR-001: Modular Monolith Backend
All Python modules share one process, one database, and communicate via function calls (not HTTP). The voice AI worker (Phase 2) is the only exception — it runs as a separate process in the same repo due to long-lived WebSocket streams.

## ADR-002: Supabase Auth + JWT forwarding
The Next.js frontend forwards Supabase JWT Bearer tokens directly to FastAPI. FastAPI validates them via Supabase's public key. No separate session layer.

## ADR-003: Email delivery stubbed for Phase 1
No real email provider integrated in Phase 1. The `send` action logs the outreach as sent but does not deliver. Provider (SendGrid/SES/Resend) wired in Phase 2.

## ADR-004: FastAPI BackgroundTasks for async work
No external message broker (Celery/Redis) for Phase 1. Spreadsheet import and other async tasks run via FastAPI BackgroundTasks. Celery can be adopted if queue depth becomes a problem.

## ADR-005: Multi-tenancy via organization_id
Row-level isolation enforced at both Supabase RLS policies and FastAPI middleware. Both layers required — defense in depth for PHI data.

## ADR-006: Admin surfaces as a separate module
Admin functionality (user mgmt, templates, import jobs, org settings) consolidated into `admin-surfaces` module rather than scattered across modules. Reduces cross-cutting surface area for role enforcement.

## ADR-007: Voice AI deferred to Phase 2
Voice module (Twilio + LiveKit + OpenAI Realtime) is designed into the data model (channel enum includes voice_ai, facility_contacts has best_call_window) but not built in Phase 1.
