# PlacementOps vs CareFlow AI — Comparison & Unified Synthesis

## TL;DR

PlacementOps and CareFlow AI are building toward the same end state from different starting points. PlacementOps is a **deeply specified workflow platform** — the operational backbone. CareFlow AI was conceived as an **intelligent outreach and automation layer** — the patient-facing communication engine. The best path forward is to treat PlacementOps as the master platform and integrate CareFlow's voice/SMS automation as a Phase 4 module within it, not as a separate product.

---

## 1. Side-by-Side Comparison

| Dimension | PlacementOps (3 docs) | CareFlow AI (prior conversations) |
|-----------|----------------------|-----------------------------------|
| **Core function** | Full placement workflow: intake → clinical review → facility matching → outreach → tracking → outcomes | Outbound patient/facility communication: discharge outreach, TCM scheduling, facility bed queries |
| **Primary users** | Offshore intake staff, clinical reviewers, placement coordinators, managers | Placement coordinators, patients/families, facility admissions |
| **Data model** | Comprehensive: 20+ tables, cases, assessments, facilities, capabilities, insurance matrices, matches, outreach, outcomes, audit | Lighter: patient records, facility directory, outreach logs, call transcripts |
| **Facility intelligence** | Deep: capability matrix, insurance rules, preference hierarchy, geographic scoring, historical outcomes | Basic: facility list, bed availability queries, geographic matching |
| **Matching engine** | Weighted rules engine with transparent scoring, blockers, explanations, manual overrides | Weighted algorithm for geographic matching, less detailed |
| **Outreach model** | Human-approved email drafts with full state machine (draft → approval → sent → tracked) | Automated multi-channel: SMS (Twilio), voicemail (Slybroadcast), voice AI, email — automation-first |
| **Voice/telephony** | Explicitly deferred: "Not a voice-calling-first product" at launch. Listed as Phase 4. | Core feature: realtime voice AI for outbound facility calls, patient discharge coordination |
| **Clinical review** | Structured assessment form with 20+ clinical fields (trach, vent, dialysis, wound care, isolation, etc.) | Not addressed — assumes clinical decisions are made upstream |
| **Intake** | Web-based intake harness + spreadsheet import fallback. Offshore staff enter data directly. | Not addressed — assumes patient data arrives from hospital systems |
| **State machine** | 13 case states + 6 outreach states with role-based transition permissions, backward flows, audit | Simpler: referral stages without formal state machine |
| **Compliance** | PHI controls, role-based access, audit trails, staff approval before any outbound communication | HIPAA considerations mentioned but less formalized |
| **Tech stack** | Next.js + FastAPI + PostgreSQL (Supabase) + Tailwind/shadcn | Next.js/Vercel + FastAPI (Railway/Render) + Supabase + shadcn + Twilio + Slybroadcast |
| **API design** | 50+ endpoints fully specified with request/response examples | Not formally specified |
| **Frontend** | 16 screens fully wireframed with component inventory, role-based navigation, dense operational UI | Not formally designed |
| **Build maturity** | Production-ready spec: DB schema, API contracts, state machines, sprint plan, wireframes | Conceptual: architecture scoped, stack chosen, no formal specs |

---

## 2. What PlacementOps Gets Right (Keep Everything)

PlacementOps is dramatically more complete as a product specification. These are strengths that CareFlow doesn't replicate:

**Operational workflow depth.** The 13-state case machine with role-based transition permissions, backward flows, and required conditions is exactly what a real placement operation needs. CareFlow had no equivalent.

**Clinical review module.** The structured assessment form (trach, vent, dialysis, wound care, isolation, bariatric, etc.) feeds directly into the matching engine. This is the connective tissue between clinical judgment and facility selection. CareFlow assumed this happened elsewhere.

**Facility intelligence system.** Capability matrices, insurance acceptance rules, preference hierarchies, last-verified dates, and contact management — this is institutional knowledge that typically lives in someone's head or a spreadsheet. PlacementOps captures it systematically.

**Transparent matching engine.** Weighted scoring with explanation text ("Accepts payer, supports wound care, within preferred geography") builds trust. CareFlow's matching was less specified.

**Human-in-the-loop outreach.** The draft → approval → sent → tracked pattern with audit logging is the right approach for healthcare communications involving PHI. CareFlow leaned more toward automation-first, which creates compliance risk.

**Intake harness.** The web-based intake workbench with spreadsheet fallback solves the real operational problem: offshore staff in India need a structured, reliable way to enter daily census data. CareFlow didn't address intake at all.

**Frontend architecture.** 16 wireframed screens with role-based navigation, component inventory, and dense operational design patterns. CareFlow had no frontend spec.

**API contract.** 50+ endpoints with full request/response examples, error envelopes, and validation patterns. CareFlow had no API spec.

---

## 3. What CareFlow AI Gets Right (Integrate Into PlacementOps)

CareFlow brings capabilities that PlacementOps explicitly defers:

**Realtime voice AI for facility outreach.** Instead of email drafts that facilities may ignore for hours, a voice agent can call facility admissions directly, ask about bed availability, confirm payer acceptance, and report back in real time. This collapses the outreach → response cycle from hours/days to minutes.

**Multi-channel outreach automation.** SMS, voicemail drops, and voice calls alongside email. PlacementOps only specifies email drafts. Real placement operations use phone calls constantly — the spec acknowledges this by listing voice as Phase 4.

**Patient/family communication hub.** Outbound SMS/voice for discharge disposition updates, TCM visit scheduling, and family preference collection. PlacementOps focuses on facility-side outreach but doesn't address patient-side communication.

**Closed referral pipeline concept.** CareFlow's insight that outbound communication can funnel patients toward your own SNF facilities while triggering early chart prep is a business model advantage, not just a feature.

**Realtime architecture thinking.** The Twilio + LiveKit + OpenAI Realtime stack, latency analysis, and starter repo evaluation represent real implementation research that PlacementOps hasn't done yet for its Phase 4 voice module.

---

## 4. Conflicts and Decisions

### Outreach Model: Automation vs. Approval
**PlacementOps says:** Nothing goes out without human approval. Draft → review → approve → send.
**CareFlow says:** Automate outreach from admission, multi-channel, configurable rules.

**Resolution:** PlacementOps is right for email/written communications containing PHI. CareFlow is right for structured voice calls where the AI is asking standardized questions (bed availability, payer acceptance) that don't require PHI disclosure. The answer is both: human-approved for PHI-containing outreach, AI-automated for structured facility inquiry calls.

### Voice: Core vs. Deferred
**PlacementOps says:** "Not a voice-calling-first product." Voice is Phase 4.
**CareFlow says:** Voice is the core differentiator.

**Resolution:** PlacementOps is right about MVP priorities — you need the workflow backbone first. But CareFlow's voice architecture should be designed into PlacementOps from the start, not bolted on later. Specifically: the outreach action model should support `channel: "voice_ai"` from day one even if the voice engine isn't built yet. The facility contact model already has `admissions_phone`. The matching engine already generates ranked facility lists. The plumbing is there.

### Naming
**PlacementOps** is the better product name for the full platform. **CareFlow AI** can be the name of the voice/automation module within it, or retired entirely.

---

## 5. Unified Product Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     PlacementOps Platform                     │
│                                                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  Intake   │  │ Clinical │  │ Facility │  │ Matching │   │
│  │Workbench │→│  Review  │→│  Intel   │→│  Engine  │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│                                                    ↓         │
│  ┌──────────────────────────────────────────────────────┐   │
│  │              Outreach & Communication Layer           │   │
│  │                                                       │   │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────────────────┐  │   │
│  │  │  Email   │  │  SMS /  │  │   Voice AI Module   │  │   │
│  │  │ Drafts   │  │Voicemail│  │   (CareFlow AI)     │  │   │
│  │  │(Phase 1) │  │(Phase 3)│  │   (Phase 4)         │  │   │
│  │  └─────────┘  └─────────┘  └─────────────────────┘  │   │
│  │                                                       │   │
│  │  Human approval gate for PHI-containing outreach      │   │
│  │  AI-automated for structured facility inquiry calls   │   │
│  └──────────────────────────────────────────────────────┘   │
│                            ↓                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Response │  │ Outcome  │  │Analytics │  │  Audit   │   │
│  │ Tracking │  │ Logging  │  │Dashboard │  │  Trail   │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## 6. What to Add to PlacementOps Specs Now

These additions integrate CareFlow's best ideas into the PlacementOps framework without disrupting the existing spec quality:

### 6.1 Outreach Action Model — Add Voice Channel Support
In the `outreach_actions` table, the `channel` field already exists. Ensure the enum includes:
- `email` (MVP)
- `phone_manual` (MVP — coordinator calls, logs result)
- `sms` (Phase 3)
- `voicemail_drop` (Phase 3)
- `voice_ai` (Phase 4)

### 6.2 Facility Contact Model — Add Structured Phone Data
The facility model already has `admissions_phone`. Add:
- `admissions_phone_extension`
- `best_call_window` (e.g., "8am-4pm ET")
- `phone_contact_name`
- `phone_notes` (e.g., "Ask for charge nurse for bed availability")

### 6.3 Outreach Template Model — Add Voice Script Templates
Alongside email templates, support:
- `template_type: "voice_ai_script"`
- System prompt fragments for the voice AI agent
- Structured data requirements (what the AI needs to ask/confirm)

### 6.4 Outcome Logging — Add Voice Call Results
The `placement_outcomes` table should support:
- `source_channel: "voice_ai" | "email" | "phone_manual" | "sms"`
- `call_transcript_url` (for voice AI calls)
- `call_duration_seconds`
- `call_outcome_summary` (AI-generated)

### 6.5 Case Status Machine — Add Voice-Specific Transitions
No new states needed, but add automated transition triggers:
- Voice AI call completes with bed confirmation → auto-log outcome event
- Voice AI call completes with decline → auto-log decline with reason
- These feed into existing `pending_facility_response` → `accepted` or `declined_retry_needed` transitions

### 6.6 Phase 4 Build Spec — Voice AI Module
When Phase 4 arrives, the architecture is:

**Stack:** Twilio SIP → LiveKit Agents → OpenAI Realtime API
**Integration point:** PlacementOps outreach action with `channel: "voice_ai"`
**Flow:**
1. Coordinator selects facility from match results
2. Clicks "Call via AI" (or batch-call multiple facilities)
3. System creates outreach action with `channel: "voice_ai"`
4. Voice AI agent dials facility admissions phone
5. Agent uses system prompt built from: patient clinical summary (de-identified), insurance, required capabilities
6. Agent asks: bed availability, payer acceptance, admission timeline, required documents
7. Call transcript + structured outcome auto-logged to PlacementOps
8. Case status updated based on facility response

**Starter repos:** (from our earlier research)
- `twilio-samples/speech-assistant-openai-realtime-api-python` — FastAPI + OpenAI Realtime
- `pBread/twilio-agentic-voice-assistant` — ConversationRelay + agentic patterns
- `danieladdisonorg/livekit-voice-agent` — production LiveKit + Twilio SIP

---

## 7. Patient-Side Communication (CareFlow's Other Contribution)

PlacementOps focuses entirely on the facility side. CareFlow identified a patient-side communication gap:

**Problem:** After a placement is accepted, someone needs to tell the patient/family, coordinate transport, schedule follow-up visits (TCM), and confirm the plan.

**Solution within PlacementOps:** Add a `patient_communication_actions` concept in Phase 3:
- Outbound SMS to patient/family with placement update
- Automated TCM visit scheduling reminder
- Discharge instruction delivery confirmation
- Family preference collection (geography, facility preferences)

This doesn't require a separate product. It's another channel in the outreach layer with a different audience (patient/family vs. facility admissions).

---

## 8. Recommended Build Sequence (Updated)

| Phase | Focus | Timeline |
|-------|-------|----------|
| **MVP (Sprints 1-8)** | PlacementOps core: intake workbench, clinical review, facility intelligence, matching engine, email outreach with approval, outcome tracking, audit trail | 8-10 weeks |
| **Phase 2** | Facility preference hierarchy, insurance matrices, decline taxonomy, internal reminders, CM update templates, basic analytics | 4-6 weeks |
| **Phase 3** | SMS/voicemail outreach channels, patient-side communication, bed availability fields, dynamic ranking, better document handling | 4-6 weeks |
| **Phase 4** | Voice AI module (CareFlow engine): Twilio + LiveKit + OpenAI Realtime for automated facility inquiry calls, batch outreach, call transcripts, AI-generated outcome logging | 4-6 weeks |
| **Phase 5** | AI-generated clinical summaries from notes, facility acceptance prediction, hospital API/FHIR integration, referral packet automation | Ongoing |

---

## 9. Final Recommendation

**Use PlacementOps as the master product.** The three uploaded specs represent a seriously well-thought-out operational platform. The domain model, state machine, API contracts, and frontend architecture are all production-quality specifications.

**Absorb CareFlow AI as the voice/automation module.** Don't build it separately. The outreach action model in PlacementOps already supports multiple channels — voice AI is just another channel. The matching engine already generates ranked facility lists with phone numbers. The outcome logging already supports structured decline reasons. The infrastructure is designed for it.

**Design for voice from day one, build it in Phase 4.** Add the `voice_ai` channel enum, facility phone metadata, and voice script template type to the data model now. Don't build the Twilio/LiveKit/OpenAI integration until the core workflow is solid and being used daily. When you're ready, you have 17+ starter repos and a fully specified architecture to move fast.

**One product, one codebase, one data model.** PlacementOps with CareFlow as an internal module name (or just "Voice Outreach") is cleaner than two separate products sharing data.
