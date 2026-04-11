# CareFlow AI — Realtime Voice Architecture & Build Resources

## The Problem

Traditional voice AI stacks (STT → LLM → TTS) add 1.5–3s round-trip latency across three separate network hops. This creates robotic, unnatural pauses that kill credibility in professional healthcare conversations. SNF admissions coordinators will hang up.

## The Solution

Speech-to-speech models that process audio natively — no intermediate text conversion. Sub-500ms response time with native interruption handling, identical to ChatGPT Advanced Voice Mode or Gemini Live.

---

## Architecture

```
CareFlow Backend (FastAPI + Supabase)
         ↕ function calls (bed status, placement updates, call logging)
Twilio SIP ←→ LiveKit Agents (media bridge) ←→ OpenAI Realtime API (speech-to-speech brain)
         ↕ alternatively
Twilio Media Streams ←→ FastAPI WebSocket ←→ OpenAI Realtime API (direct, no LiveKit)
         ↕ alternatively  
Twilio ConversationRelay ←→ FastAPI WebSocket ←→ Any LLM (managed STT/TTS by Twilio)
```

### Three Viable Approaches (pick one)

**Option A: Twilio + LiveKit + OpenAI Realtime (recommended for scale)**
- LiveKit SIP integration bridges Twilio telephony to OpenAI Realtime API
- Best call quality, WebRTC-grade media handling, noise cancellation (BVC/Krisp)
- Built-in session management, reconnection, semantic turn detection
- Self-hostable (Apache 2.0) or LiveKit Cloud managed
- Supports outbound dialing via SIP participants

**Option B: Twilio Media Streams + OpenAI Realtime (fastest to prototype)**
- Direct WebSocket bridge between Twilio and OpenAI — no middleware
- Fewer moving parts, FastAPI handles the bridge
- Less robust than LiveKit for production (no WebRTC, no noise cancellation)
- Twilio's official sample code makes this work in ~2 hours

**Option C: Twilio ConversationRelay + Any LLM (managed, lowest effort)**
- Twilio handles all STT/TTS orchestration (<0.5s median latency, <0.725s p95)
- You only send/receive text over WebSocket — Twilio manages the audio pipeline
- HIPAA eligible when configured properly
- Supports Deepgram, ElevenLabs, Google, Amazon for STT/TTS
- Not speech-to-speech (still cascaded), but Twilio optimizes the pipeline heavily
- BYO-LLM: works with OpenAI, Anthropic, DeepSeek, Mistral, etc.

### Outbound Call Flow (Options A or B)

1. CareFlow triggers outbound dial via Twilio REST API
2. Twilio SIP trunk connects to LiveKit server (or Media Streams to FastAPI)
3. Agent session pipes audio bidirectionally to OpenAI Realtime API
4. System prompt contains SNF outreach scripts (bed availability, insurance, admission criteria)
5. Function calls hit FastAPI/Supabase backend mid-conversation (check bed status, update placement records, log call outcomes)
6. Call summary + transcript auto-written to Supabase on hangup

### Key Integration Points

- **Twilio**: outbound dialing, number management, call recording, ConversationRelay
- **LiveKit Agents (Python SDK)**: session orchestration, SIP bridging, agent lifecycle
- **OpenAI Realtime API**: voice intelligence, conversation management, tool use
- **FastAPI + Supabase**: CareFlow backend for facility data, placement tracking, call logging

### Fallback Provider

- **Gemini Live (Multimodal Live API)**: secondary provider if OpenAI latency degrades or for cost optimization on high-volume runs
- **ElevenLabs Conversational AI**: end-to-end voice agent product, competitive latency

### Cost Model

~$0.06–0.10/min for OpenAI Realtime. Calls are short (2–5 min structured outreach). ConversationRelay adds ~$0.07/min for Twilio's orchestration layer.

---

## Starter Repos — Ranked by Relevance to CareFlow

### Tier 1: Start Here (closest to what you need)

| Repo | Stack | Why It Matters |
|------|-------|----------------|
| `twilio-samples/speech-assistant-openai-realtime-api-python` | Python/FastAPI + Twilio + OpenAI Realtime | Official Twilio sample. Inbound calls with OpenAI Realtime. FastAPI WebSocket bridge. Includes outbound calling demo. Closest to plug-and-play for your stack. |
| `openai/openai-realtime-twilio-demo` | Node/Express + Next.js + Twilio + OpenAI Realtime | OpenAI's own demo. NextJS webapp + Express WebSocket backend. Good reference for the Twilio↔Realtime bridge pattern. |
| `pBread/twilio-agentic-voice-assistant` | Node + Twilio ConversationRelay + OpenAI | Full agentic voice assistant using ConversationRelay. Includes debugging UI, tool calling, context system, dynamic language switching, Twilio Flex integration for human handoff. Most production-ready ConversationRelay example. |
| `livekit-examples/livekit-sip-agent-example` | TypeScript + LiveKit + Twilio SIP + OpenAI | Official LiveKit example. Shows SIP call answering with Twilio as SIP provider. Clean setup scripts for both LiveKit and Twilio config. |

### Tier 2: Production Patterns & Extensions

| Repo | Stack | Why It Matters |
|------|-------|----------------|
| `danieladdisonorg/livekit-voice-agent` | Python + LiveKit + Twilio SIP + OpenAI + ElevenLabs + Deepgram | Production-ready: function calling, noise cancellation, comprehensive logging, SIP telephony. Recommended Next.js frontend companion. Regional SIP config included. |
| `daily-co/pcc-openai-twilio` | Python + Pipecat + Twilio + OpenAI | Two bot variants: cascaded (STT→LLM→TTS) and speech-to-speech (OpenAI Realtime). Docker-deployable to Pipecat Cloud. Good for comparing approaches. |
| `pipecat-ai/pipecat-quickstart-phone-bot` | Python + Pipecat + Twilio | Simplest Pipecat phone bot. Complete Twilio telephony setup. Good for rapid prototyping. |
| `microsoft/call-center-ai` | Python + Azure + Twilio/ACS | Enterprise-grade: RAG, multi-language, conversation resumption, call recording, human handoff. Uses gpt-4.1. Azure-native but architecture patterns are transferable. |
| `Azure-Samples/realtime-call-center-accelerator` | Python + Azure OpenAI Realtime + ACS | One-click Azure deploy. Uses OpenAI Realtime models with Azure Communication Services. Knowledge base customization via storage. Good observability patterns. |
| `neural-maze/realtime-phone-agents-course` | Python + FastRTC + Twilio + Runpod | Full course repo: multi-avatar system, Opik tracing, prompt versioning, Qdrant vector search. Good for observability and multi-persona patterns. |

### Tier 3: Framework-Specific & Niche

| Repo | Stack | Why It Matters |
|------|-------|----------------|
| `ahmad2b/langgraph-voice-call-agent` | Python + LangGraph + LiveKit | Adapts any LangGraph agent into a full-duplex voice assistant via LiveKit. Good if you want LangGraph's state machine for complex call flows. |
| `Agentic-Insights/voice-bot` | Python + Vocode + Twilio + Deepgram + ElevenLabs | Opinionated Vocode telephony server. Docker Compose setup. Inbound + outbound. Good for Vocode evaluation. |
| `hkjarral/AVA-AI-Voice-Agent-for-Asterisk` | Python + Asterisk/FreePBX | No external telephony providers needed. MIT licensed. ~$0.001–0.003/min local hybrid. Full PBX control. Good if you want to own the entire stack. |
| `rehan-dev/ai-call-agent` | Python + FastAPI + Twilio + OpenAI Realtime | Minimal outbound calling agent. Clean structure: main.py + system_prompt.txt. Good reference for outbound-specific patterns. |
| `revolutionarybukhari/ai-calling-agent` | Python/Flask + Twilio + OpenAI + Pinecone + MongoDB | Inbound/outbound with vector DB for context. Healthcare personality (mental health consultant). Shows RAG integration in voice calls. |
| `agonza1/policy-aware-voice-ai-customer-support` | Python + Pipecat + Twilio + LangGraph | Policy guardrails for regulated industries. Separates voice, AI reasoning, and policy enforcement layers. Docker Compose one-liner setup. Relevant for healthcare compliance patterns. |
| `rosiefaulkner/langgraph-voice-agent` | Python + LangGraph + Supabase + OpenAI | Voice agent with Supabase PostgreSQL backend and MCP server tools. Closest stack match to CareFlow (LangGraph + Supabase). |

### Tier 4: Healthcare-Specific References

| Repo | Stack | Why It Matters |
|------|-------|----------------|
| `theaifutureguy/Healthcare-AI-Voice-agent` | Python/FastAPI + React + PostgreSQL + LangGraph + Gemini/GPT-4 | Full-stack healthcare voice app: triage, symptom analysis, specialist mapping, appointment booking. Architecture patterns directly applicable. |
| `AgenticHealthAI/Awesome-AI-Agents-for-Healthcare` | Curated list | Includes production-ready AI phone agent for patient outreach using LangGraph + Twilio. Voice calling and SMS skills for healthcare. FHIR tools, prior auth, clinical trial generation. |
| `mjunaidca/appointment-agent` | Python + LangGraph + Composio + Bland.com | Appointment booking agent with Google Calendar/Gmail integration, outbound calls. Customizable for Twilio/Vapi. Deployed on LangGraph Cloud. |

---

## Open-Source Telephony Frameworks (already evaluated)

| Framework | GitHub | Best For |
|-----------|--------|----------|
| **Pipecat** | `pipecat-ai/pipecat` | Flexible Python pipelines, Pipecat Cloud deployment, OpenAI Realtime plugin (`19-openai-realtime-beta.py`) |
| **LiveKit Agents** | `livekit/agents` | Production telephony via SIP, WebRTC media, semantic turn detection, MCP support, built-in test framework |
| **Bolna** | `bolna-ai/bolna` | Twilio/Plivo telephony, Docker setup, extensible provider architecture |
| **Vocode** | `vocodedev/vocode-core` | Modular Python library, Twilio/Zoom, full pipeline customization |

## Managed Platforms (non-open-source alternatives)

| Platform | Key Advantage | HIPAA |
|----------|---------------|-------|
| **Retell AI** | Natural turn-taking, pay-as-you-go | SOC 2 Type II, HIPAA compliant |
| **Vapi** | 100+ languages, hallucination testing, BYOK | Varies |
| **Bland AI** | Self-hosted models, custom voice cloning | Enterprise controls |
| **Synthflow** | No-code, in-house telephony, <100ms latency | SOC 2, HIPAA, PCI DSS, GDPR |
| **Twilio ConversationRelay** | Managed STT/TTS, <0.5s median, HIPAA eligible | HIPAA eligible |

## Key Latency Benchmarks (Twilio, Nov 2025)

- **Mouth-to-Ear Turn Gap (cascaded)**: ~0.5–0.725s median via ConversationRelay
- **Speech-to-speech (OpenAI Realtime)**: sub-500ms, single model, no intermediate hops
- **Traditional STT→LLM→TTS**: 1.5–3s (unacceptable for professional calls)

---

## Recommended Build Path for CareFlow

**Phase 1 — Proof of Concept (1–2 days)**
- Clone `twilio-samples/speech-assistant-openai-realtime-api-python`
- Swap system prompt for SNF outreach script
- Add outbound dialing endpoint (reference Twilio's outbound tutorial)
- Test with a real phone call to validate latency and conversation quality

**Phase 2 — Backend Integration (3–5 days)**
- Wire OpenAI Realtime function calling to your FastAPI/Supabase backend
- Functions: `check_bed_availability()`, `update_placement_status()`, `log_call_outcome()`
- Add call transcript storage to Supabase on hangup
- Reference `rosiefaulkner/langgraph-voice-agent` for Supabase + voice patterns

**Phase 3 — Production Hardening (1–2 weeks)**
- Migrate from direct Twilio Media Streams to LiveKit SIP for WebRTC quality
- Reference `danieladdisonorg/livekit-voice-agent` for production patterns
- Add noise cancellation (LiveKit BVC), reconnection handling, call recording
- Implement batch outbound dialing for multi-facility outreach campaigns
- Add observability (Langfuse or Opik for tracing, reference `neural-maze/realtime-phone-agents-course`)

**Phase 4 — Scale & Compliance**
- Evaluate Twilio ConversationRelay as managed alternative (HIPAA eligible)
- Reference `pBread/twilio-agentic-voice-assistant` for ConversationRelay + agentic patterns
- Add Gemini Live as fallback provider
- Implement policy guardrails (reference `agonza1/policy-aware-voice-ai-customer-support`)
- Human handoff workflows for complex placement scenarios
