# Prior Art Research: Post-Acute Care Placement Operations Software

**Research date:** 2026-04-10
**Project:** PlacementOps (CareFlow) — FastAPI + Next.js + Supabase
**Topic:** Post-acute care placement operations — commercial prior art, architecture patterns, HIPAA compliance, FHIR standards

---

## Executive Summary

The post-acute placement market is dominated by a small number of consolidated SaaS platforms (WellSky CarePort, Aidin, Ensocare/ABOUT) that all converged on the same core architecture: a multi-tenant referral hub where hospitals send patients and post-acute facilities receive them. None of these vendors expose technical architecture publicly, but their product surfaces reveal consistent workflow state machines, HL7/ADT integration, and provider network matching. The open-source FHIR ecosystem (Medplum) provides the most complete reference implementation for the underlying data model. The field is ripe for disruption: over 75% of referrals still travel by fax in 2024, and hospital length-of-stay for placement-waiting patients grew 24% between 2019-2022.

---

## 1. Commercial Landscape

### 1.1 WellSky CarePort (market leader)

**Origin:** Consolidation of Curaspan (acquired by naviHealth 2016) + CarePort Health (acquired by WellSky) into a single platform.

**Scale:** 2,000+ hospitals, 130,000+ post-acute providers, 25+ years of market data.

**Core product surfaces:**
- **CarePort Referral Intake** (2025): Centralizes eFax, direct secure messaging, and third-party portals into one worklist with AI document extraction and clinical summarization.
- **CarePort Connect**: The original hospital-to-PAC provider referral network.
- **Curaspan Intake / ReviewCentral / OutreachCentral**: Payer-facing tools for UR review and post-discharge outreach.

**Workflow states (inferred from product documentation):**
```
Referral Received → Document Extraction → Clinical Review →
Provider Match → Outreach Sent → Provider Accepted/Rejected →
Patient Placed → Post-discharge Tracking
```

**Matching algorithm signals:**
- Reads admission risk + post-acute level-of-care prediction from ML model
- 360° Risk Summary: clinical diagnosis data + prior hospitalizations + social determinants of health + SNF quality scores
- CarePort Quality Score: monthly-updated SNF performance data (readmit rate, avg LOS) — not claims-based like CMS Star ratings
- Patient-record matching uses probabilistic scoring (nicknames, abbreviations, manual errors, address history, utilization history)

**Integration protocols:** HL7, FHIR, web services, SFTP. HL7 ADT (Admission/Discharge/Transfer) messages seed the system with real-time patient census.

**Lesson for PlacementOps:** The AI-assisted "level of care recommendation" (SNF vs Home Health vs IRF) is a differentiator, but it is also the source of the industry's biggest legal and ethical controversy (see Section 5). PlacementOps should provide data-informed guidance without automating the clinical decision itself.

---

### 1.2 Aidin

**Focus:** Hospital-side case management and discharge planning workflow.

**Core workflow:**
- Per-patient daily task checklists with staff assignment
- Visual flags for incomplete tasks, at-risk flows, overdue assignments
- Document sorting from printers/faxes/email with patient assignment
- Prior authorization integration (PreCert product, 2021)
- Epic bi-directional integration (CRN — Care Referral Network)

**Matching approach (inferred):**
- Case managers build "Patient Choice" lists filtered by payer, clinical need, and geography
- Real-time availability and insurance compatibility signals from PAC network
- Coordinator sends referral to a curated shortlist, not broadcast

**Key insight:** Aidin's value proposition is workflow efficiency on the *hospital* side — reducing the manual burden on case managers/coordinators. PlacementOps has a similar angle but adds the internal census and clinical review layers before the outreach phase.

---

### 1.3 Ensocare / ABOUT

**Current state:** Ensocare was acquired by ABOUT, which provides hospital-wide operational workflows. Ensocare Choice is now the post-acute placement component.

**Technical architecture (partial):**
- HL7 ADT inbound interface to seed patient data (exactly the same pattern as CarePort)
- Web-based, browser-only for end users
- Network of 50,000+ PAC providers
- Patient Choice documentation to satisfy CMS Conditions of Participation

**Workflow:** Hospital discharge planner selects post-acute providers → patient reviews options digitally → choice is documented → referral sent.

---

### 1.4 naviHealth (now part of Optum/UnitedHealth)

**What it is:** Originally a care transition company; its technology (nH Predict) became the center of a 2024-2025 class action lawsuit.

**nH Predict algorithm:**
- Database of 6 million patient records collected since the mid-1990s
- Inputs: patient diagnosis, age, living situation, physical function
- Outputs: predicted care setting + predicted length of stay
- Blue Cross Blue Shield of Michigan deployment: 13% reduction in SNF LOS; >30-day stays dropped 56%

**Critical warning:** CMS issued guidance in 2024 clarifying that an algorithm which determines coverage based on a population database rather than individual patient medical history is non-compliant with federal law. A federal court (Feb 2025) allowed a class action lawsuit to proceed. The Senate report (Oct 2024) found UnitedHealthcare's post-acute denial rate was 3x its overall prior authorization denial rate.

**Lesson for PlacementOps:** Clinical decision support = good. Automated coverage denial based on population benchmarks = regulatory and legal risk. The system must present recommendations with supporting data, not make binding decisions.

---

### 1.5 Other relevant tools

| Vendor | Focus | Notable Feature |
|--------|-------|-----------------|
| Qventus | AI inpatient discharge planning | ML auto-populates EDD and disposition on Day 1 post-admission, embedded in EHR |
| Rovicare | SNF-side discharge coordination | One-click referral send + EMR integration (PointClickCare); 148% time reduction documented |
| TeleTracking | Hospital patient flow + bed management | Care transitions as part of broader operational platform |
| Watershed Health | Care transitions with social needs | Competing with Aidin on case management workflow |

---

## 2. Architecture Patterns

### 2.1 Universal patterns across all vendors

Every successful placement platform converges on the same three-layer architecture:

```
Layer 1: Census/Patient Layer
  - Real-time patient list (seeded by HL7 ADT from hospital EHR)
  - Admission status, clinical flags, anticipated discharge date
  - Per-patient workflow state tracking

Layer 2: Clinical Operations Layer
  - Clinical review / utilization review workflows
  - Task assignment by role (case manager, coordinator, clinical reviewer)
  - Document management (referral packets, clinical summaries)
  - Prior authorization tracking

Layer 3: Provider Network Layer
  - PAC provider directory with availability + quality signals
  - Referral routing and outreach tracking
  - Accept/decline tracking and response time metrics
  - Outcome feedback (readmission rates, LOS actuals vs predicted)
```

---

### 2.2 Workflow State Machine Pattern

Every referral in these systems follows a finite state machine. The canonical states (synthesized across vendors):

```
Patient Level:
  admitted → assessment_pending → plan_in_progress →
  placement_pending → placed → discharged → tracking

Referral/Outreach Level:
  draft → sent → viewed → accepted | declined | no_response →
  patient_confirmed → cancelled

Clinical Review Level:
  pending → in_review → approved | denied | pending_info
```

**Implementation recommendation for PlacementOps:** Use `python-statemachine` (v3.0.0, MIT, released Feb 2026) for the Python/FastAPI backend state machine. It supports async callbacks, compound states, history states, and integrates cleanly with Pydantic.

For the Next.js frontend, XState v5 (MIT, 4.1M downloads/week) provides statechart-based UI state management that can mirror backend states, making it natural to reflect the current workflow step in the UI without prop drilling.

---

### 2.3 HL7 ADT Integration Pattern

All commercial platforms use an inbound HL7 v2 ADT (Admission/Discharge/Transfer) interface as the primary data ingestion mechanism:

```
Hospital EHR → HL7 ADT A01/A02/A03/A04/A08 messages →
  Integration Engine (Mirth/Rhapsody) →
  Normalized patient record →
  Platform patient census
```

**For PlacementOps:** Because you are building an internal tool (not an EHR replacement), you will likely receive CSV/Excel census exports or a direct database feed rather than live HL7. Design the Patient/Encounter data model to be HL7-compatible from the start (using FHIR resource shapes) so you can upgrade to real-time ADT feeds later without a schema redesign.

---

### 2.4 FHIR Resource Model for Placement Workflows

Based on Medplum's reference implementation and HL7 PAO (Post-Acute Orders) Implementation Guide:

```
Patient           — demographics, insurance, preferences
Encounter         — the current inpatient stay (links everything)
EpisodeOfCare     — groups related encounters across settings
ServiceRequest    — the referral/placement request
  └─ basedOn: CarePlan
Task              — individual workflow steps tracking the ServiceRequest
  ├─ Task.status: draft | requested | received | accepted | in-progress | completed | cancelled
  ├─ Task.businessStatus: custom operational states (e.g., "awaiting clinical review")
  └─ Task.owner: assigned staff member or role queue
Communication     — messages between hospital and PAC provider
DocumentReference — referral packet documents, clinical summaries
Observation       — clinical assessments (Barthel index, FIM scores, diagnoses)
Organization      — hospital system + PAC facility directory
```

**Key insight from Medplum documentation:** `Task.focus` (the focal resource a Task operates on) is critical for data hygiene and analytics. Every Task should have a populated focus reference — this enables turning-time metrics, conversion rates, and bottleneck identification without complex joins.

**For PlacementOps:** You do not need to implement full FHIR REST endpoints on day one. Use the FHIR resource shapes as your database schema design inspiration. This gives you interoperability headroom without the overhead of a full FHIR server.

---

### 2.5 Matching / Facility Recommendation Pattern

CarePort's matching approach (inferred from public documentation):

```
Input signals:
  - Patient: diagnosis codes (ICD-10), acuity, insurance/payer,
             geographic preference, social determinants, prior PAC history
  - Facility: availability (real-time), quality score, distance,
              payer network participation, specialty capabilities,
              historical accept rate for this hospital

Matching algorithm outputs:
  1. Level-of-care recommendation: SNF | IRF | LTACH | Home Health
  2. Ranked shortlist of facilities meeting criteria
  3. Readmission risk score for overall discharge planning context

Outreach pattern:
  - Coordinator sends referral packet to top N facilities simultaneously
  - System tracks response time (30-min benchmark in some studies)
  - Accept/decline captured, next facility on list contacted if declined
```

**Warning from the industry:** Privacy-preserving matching (match on anonymized clinical criteria before sharing PII) is emerging as a best practice to accelerate placement while reducing premature PHI disclosure.

---

### 2.6 Event Sourcing for Audit Trail

This is the most important architectural decision for HIPAA compliance. Commercial platforms require an immutable audit log of every action. The cleanest implementation for FastAPI + PostgreSQL is a lightweight event sourcing pattern:

```python
# Event store table (append-only, no UPDATE/DELETE permitted)
CREATE TABLE audit_events (
    event_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    tenant_id       UUID NOT NULL,           -- multi-tenant isolation
    user_id         UUID NOT NULL,           -- who did it
    user_role       TEXT NOT NULL,           -- role at time of event
    event_type      TEXT NOT NULL,           -- e.g. 'patient.placement_status_changed'
    resource_type   TEXT NOT NULL,           -- e.g. 'Patient', 'Referral'
    resource_id     UUID NOT NULL,           -- the affected record
    before_value    JSONB,                   -- previous state snapshot
    after_value     JSONB,                   -- new state snapshot
    source_ip       INET,
    session_id      UUID,
    -- Immutability enforcement
    hash            TEXT NOT NULL            -- SHA-256 of (prev_hash + event data)
);
-- No RLS UPDATE/DELETE policies on this table
-- Separate DB role with INSERT-only access
```

**HIPAA requirements for audit logs:**
- Minimum 6-year retention from creation date (state law may require longer)
- Millisecond-accurate timestamps in UTC
- Log: all PHI access (reads, not just writes), all state changes, all authentication events, all administrative changes
- Immutable storage: append-only table + periodic export to S3/Glacier for long-term retention
- Annual review now mandatory under 2026 HIPAA Security Rule updates

**Async logging pattern for FastAPI:**
```python
# FastAPI middleware — async, non-blocking
@app.middleware("http")
async def audit_middleware(request: Request, call_next):
    response = await call_next(request)
    # Fire-and-forget audit event (don't block the response)
    background_tasks.add_task(write_audit_event, request, response)
    return response
```

---

## 3. Multi-Tenancy Architecture (Supabase + PostgreSQL)

### 3.1 The pattern to use

For a healthcare SaaS serving multiple hospital systems, use **shared tables with `tenant_id` + Row-Level Security (RLS)** — not separate schemas per tenant. Separate schemas add operational complexity without meaningfully stronger isolation for this threat model.

```sql
-- Every data table carries tenant_id
ALTER TABLE patients ADD COLUMN tenant_id UUID NOT NULL
  REFERENCES organizations(id);

-- RLS policy extracts tenant from JWT claims (set by Supabase Auth)
CREATE POLICY tenant_isolation ON patients
  FOR ALL
  USING (tenant_id = (auth.jwt() -> 'app_metadata' ->> 'tenant_id')::uuid);

-- Enable RLS on every table with PHI
ALTER TABLE patients ENABLE ROW LEVEL SECURITY;
```

**JWT structure for Supabase:**
- Store `tenant_id` and `role` in `app_metadata` (server-set, not user-editable)
- User's JWT is issued by Supabase Auth; FastAPI validates it using Supabase's JWKS endpoint
- PostgreSQL RLS policies read `auth.jwt()` to extract the tenant context

### 3.2 Defense-in-depth layering

```
Layer 1: Supabase Auth — JWT issuance and validation
Layer 2: FastAPI — middleware validates JWT + extracts tenant_id
Layer 3: PostgreSQL RLS — enforces isolation at query execution time
Layer 4: Application — never passes raw user input as tenant_id
Layer 5: Audit log — immutable record of cross-tenant access attempts
```

### 3.3 Supabase HIPAA considerations

- HIPAA add-on is available on Team Plan or above; requires a signed BAA with Supabase
- Supabase itself signs a BAA with AWS (their infrastructure provider)
- Supabase undergoes annual HIPAA + SOC 2 combined audits
- Self-hosted Supabase does NOT include the HIPAA controls — use managed Supabase if this is a requirement
- Customer responsibility: configure RLS correctly, implement audit logging, sign BAA, follow Security Advisor recommendations

---

## 4. Reference Implementations

### 4.1 Medplum (medplum/medplum)

**URL:** https://github.com/medplum/medplum
**Stars:** 2,300+
**License:** Apache 2.0
**Stack:** TypeScript, Node.js, PostgreSQL, React, AWS

**What it is:** Open-source "headless EHR" built on FHIR. Not a placement platform, but the best available reference for healthcare workflow data modeling.

**Architecture pattern:** Modular monolith with FHIR as the canonical data format. Every clinical concept maps to a FHIR resource; the platform is essentially a FHIR server + workflow automation (Bots) + auth + UI components.

**File structure (relevant packages):**
```
packages/
  server/       — Express backend, FHIR REST API, PostgreSQL
  app/          — React frontend (Medplum App)
  core/         — Shared FHIR utilities, type definitions
  react/        — UI component library (ResourceTable, Timeline, etc.)
  fhirtypes/    — TypeScript types for all FHIR R4 resources
  cdk/          — AWS CDK infrastructure
```

**What to learn:**

1. **Task-based workflow pattern:** Medplum's Task management is the closest open-source reference to what PlacementOps needs. Task.status (coarse FHIR states) + Task.businessStatus (fine-grained operational states like "awaiting clinical review") is the right two-level status model.

2. **ServiceRequest as the referral anchor:** Every referral is a ServiceRequest. Tasks are created to track the steps needed to fulfill that ServiceRequest. This separation of "what was requested" from "what work is being done to fulfill it" is the key architectural insight.

3. **Project-based multi-tenancy:** Medplum uses "Projects" as the tenant unit. Each Project has its own users, access policies, and resource namespace. Worth studying `packages/server/src/admin/` for how they implement this.

4. **FHIR SearchParameter indexing:** Medplum indexes FHIR resources into a flat PostgreSQL table with JSONB for the resource body and indexed columns for searchable fields. This avoids the impedance mismatch of mapping FHIR resources to relational schemas.

**What to avoid:**
- Full FHIR compliance is overkill for an internal tool. Don't implement FHIR REST endpoints unless you need EHR integration.
- The Bot system (serverless function execution) is powerful but complex; Celery workers are a simpler equivalent.

**Reference:** https://www.medplum.com/docs/careplans/tasks — "Using Tasks to Manage Clinical Workflow"

---

### 4.2 FHIR Post-Acute Orders (PAO) Implementation Guide

**URL:** https://confluence.hl7.org/spaces/FHIR/pages/80119117
**Status:** HL7 standard (not open source code, but defines the canonical data model)

**What it covers:** Electronic ordering of post-acute services (DME, Home Health Agency, SNFs). Based on CMS EMDI pilot program (now closed but documented).

**FHIR resources for a placement order:**
- `ServiceRequest` — the placement request (ordering provider, receiving facility, service type, clinical indication)
- `Task` — tracks fulfillment workflow
- `Questionnaire/QuestionnaireResponse` — structured clinical data collection
- `DocumentReference` — referral packet documents
- `Coverage` — insurance/payer information

**For PlacementOps:** The PAO IG defines what data should exist on a placement request. Use it as a checklist for your `Referral` or `PlacementRequest` database table columns.

---

### 4.3 Relevant open-source Python state machine libraries

| Library | Version | License | Downloads/wk | Last Release | Status |
|---------|---------|---------|-------------|-------------|--------|
| python-statemachine | 3.0.0 | MIT | unknown | Feb 2026 | APPROVED |
| transitions | 0.9.3 | MIT | unknown | Jul 2025 | APPROVED |

**Recommendation:** Use `python-statemachine` for PlacementOps workflow states. It is more actively maintained (v3.0.0 released Feb 2026), has better async support, and uses a declarative DSL that is easier to read when defining complex placement state graphs. The statechart support (compound states, parallel regions, history) directly models the two-level status pattern (coarse + fine-grained).

```python
# Example: Placement workflow state machine
from statemachine import StateMachine, State

class PlacementStateMachine(StateMachine):
    # Coarse states
    admitted = State(initial=True)
    assessment = State()
    planning = State()
    outreach = State()
    placed = State()
    discharged = State()

    # Transitions
    begin_assessment = admitted.to(assessment)
    complete_assessment = assessment.to(planning)
    begin_outreach = planning.to(outreach)
    confirm_placement = outreach.to(placed)
    discharge = placed.to(discharged)
    escalate = outreach.to(planning)  # no placement found, back to planning

    def on_enter_outreach(self):
        # Trigger: create referral tasks, notify coordinator
        pass

    def on_confirm_placement(self):
        # Trigger: write audit event, notify family, update census
        pass
```

---

## 5. Key Lessons Learned from the Industry

### 5.1 The fax problem is real and persistent

Over 75% of North American healthcare providers still use fax for referrals as of 2024. This is not ignorance — it is locked in by regulatory workflow requirements, legal defensibility habits, and the fact that eFax satisfies HIPAA while modern APIs require BAAs from every participant. PlacementOps should support fax-equivalent workflows (PDF packet generation, document upload) from day one, even if the internal workflow is digital.

### 5.2 Response time is the primary metric

Studies show that a discharge planner's response time to a referral directly determines placement success. CarePort tracks "end-to-end transparency across entire referral pipeline" because providers who respond faster get patients. PlacementOps should surface response time prominently in coordinator dashboards.

### 5.3 Predictive LOC recommendations: build carefully

The naviHealth/nH Predict experience is a cautionary tale. CMS guidance (2024) is explicit: coverage decisions must be based on individual patient clinical history, not population benchmarks. The federal class action lawsuit (Estate of Lokken v. UnitedHealth, 2025) is pending. If PlacementOps surfaces "predicted SNF days" or "suggested level of care," it must:
- Label these as clinical decision support tools, not coverage decisions
- Allow clinical override with documented rationale
- Never auto-deny or auto-approve based on the algorithm alone
- Maintain a complete audit trail of every recommendation shown and every override made

### 5.4 Algorithmic bias in facility matching

The MedCity News analysis (Dec 2025) documented cases where algorithmic discharge recommendations didn't account for social context (family caregiver availability, transportation, ADL support). PlacementOps matching should expose the factors used in ranking and allow coordinators to override them with documented reasons.

### 5.5 The referral completion gap

50% of specialty referrals never complete. 25-50% of referring physicians lack confirmation the patient saw the specialist. This is the fundamental broken-loop problem. PlacementOps should track "confirmed placement" (facility accepted) vs "confirmed admission" (patient actually admitted) as separate milestone events.

### 5.6 Real-time tracking is the high-ROI feature

Studies show 45% efficiency improvement and 30% reduction in placement leakage from real-time referral tracking. The "package tracking model" (bidirectional visibility: both hospital and facility see identical timeline) is the key feature that separates modern platforms from email/fax workflows.

### 5.7 Regulatory floor: CMS Conditions of Participation

Hospitals are federally required (42 CFR 482.43) to:
- Include a list of available SNFs/IRFs/LTCHs in every discharge plan
- Document patient choice of facility
- Allow patients to choose any Medicare-participating PAC provider in their area

PlacementOps must capture and document "patient choice" as a data model entity, not just an informal note.

---

## 6. Recommended Packages for PlacementOps

### Python / FastAPI backend

| Package | Version | License | Use |
|---------|---------|---------|-----|
| python-statemachine | 3.0.0 | MIT | Placement workflow state machines |
| transitions | 0.9.3 | MIT | Alternative; more battle-tested, slightly older API |
| celery | latest | BSD-3 | Background tasks: fax generation, notification dispatch, audit event writing |
| pydantic | v2 | MIT | Data validation for FHIR-shaped models |
| python-jose | latest | MIT | JWT validation against Supabase JWKS |

### Next.js / React frontend

| Package | Version | License | Downloads/wk | Use |
|---------|---------|---------|-------------|-----|
| xstate | 5.30.0 | MIT | 4.17M | Frontend workflow state management |
| @xstate/react | 6.1.0 | MIT | 2.44M | React hooks for XState machines |

**Note:** XState v5 on the frontend does NOT need to mirror the Python state machine exactly. Use it to manage complex UI state (multi-step referral forms, coordinator outreach flows). The canonical workflow state lives in the database (Python backend).

### License Report

| Package | License | Status |
|---------|---------|--------|
| python-statemachine | MIT | APPROVED |
| transitions | MIT | APPROVED |
| xstate | MIT | APPROVED |
| @xstate/react | MIT | APPROVED |
| celery | BSD-3-Clause | APPROVED |
| pydantic | MIT | APPROVED |

All recommended packages carry permissive licenses. No FLAGGED packages identified.

---

## 7. Recommended Database Schema Patterns

### 7.1 Core tables (Supabase / PostgreSQL)

```sql
-- Tenant / Organization
CREATE TABLE organizations (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    npi         TEXT,                    -- National Provider Identifier
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Users belong to an org with a role
CREATE TABLE users (
    id          UUID PRIMARY KEY REFERENCES auth.users,
    tenant_id   UUID NOT NULL REFERENCES organizations(id),
    role        TEXT NOT NULL            -- 'intake', 'clinical_reviewer', 'coordinator', 'admin'
);

-- Daily census entry (the intake-staff-facing data)
CREATE TABLE census_entries (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id      UUID NOT NULL REFERENCES organizations(id),
    patient_id     UUID NOT NULL REFERENCES patients(id),
    census_date    DATE NOT NULL,
    bed_unit       TEXT,
    attending_md   TEXT,
    insurance_type TEXT,
    anticipated_discharge_date DATE,
    disposition_target TEXT,            -- 'SNF' | 'IRF' | 'LTACH' | 'Home' | 'Hospice'
    created_by     UUID REFERENCES users(id),
    created_at     TIMESTAMPTZ DEFAULT now()
);

-- Placement workflow state per patient per episode
CREATE TABLE placement_cases (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES organizations(id),
    patient_id      UUID NOT NULL REFERENCES patients(id),
    encounter_id    UUID,               -- links to hospital encounter
    status          TEXT NOT NULL DEFAULT 'admitted',
    business_status TEXT,               -- fine-grained operational state
    assigned_coordinator UUID REFERENCES users(id),
    target_level_of_care TEXT,          -- 'SNF' | 'IRF' | 'LTACH'
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Referral / outreach to a specific facility
CREATE TABLE referrals (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES organizations(id),
    placement_case_id UUID NOT NULL REFERENCES placement_cases(id),
    facility_id     UUID NOT NULL REFERENCES facilities(id),
    status          TEXT NOT NULL DEFAULT 'draft',
                    -- draft | sent | viewed | accepted | declined | no_response | cancelled
    sent_at         TIMESTAMPTZ,
    responded_at    TIMESTAMPTZ,
    response_notes  TEXT,
    sent_by         UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ DEFAULT now()
);
```

### 7.2 Audit log table (append-only)

See Section 2.6 for the full `audit_events` schema. Apply RLS: only INSERT permitted for application role; SELECT permitted for audit/compliance role; no UPDATE or DELETE for any role.

---

## 8. Research Gaps

The following could not be fully verified from publicly available sources:

1. **CarePort / WellSky internal schema**: No technical documentation is public. The workflow state inference is from product marketing and user guide PDFs.

2. **Python library weekly download counts**: PyPI does not expose weekly download counts on the package page. The npm ecosystem is better documented here. Both `python-statemachine` and `transitions` are production-used with strong GitHub star counts (6.5k for transitions), but exact download volumes are unverified.

3. **Supabase HIPAA tier specifics**: The HIPAA compliance doc confirms a BAA and annual audits exist but does not detail which specific controls (encryption algorithms, audit log infrastructure) are Supabase-managed vs customer-configured. Recommend a direct pre-sales conversation with Supabase if PHI will be stored.

4. **Medplum's exact multi-tenancy implementation**: The "Projects" concept is documented at a high level. The source code in `packages/server/src/admin/` would need to be read for implementation details.

5. **Real-world performance of python-statemachine v3 in production**: This is a new major version (Feb 2026). The API is significantly improved but large-scale production adoption data is limited. `transitions` (v0.9.3, Jul 2025) has longer production history if stability is preferred over API ergonomics.

6. **FHIR PAO IG adoption rate**: The CMS EMDI pilot concluded without producing a widely-deployed implementation. Real-world post-acute FHIR order exchange remains minimal; most commercial platforms still use proprietary APIs + HL7 v2.

---

## 9. Actionable Recommendations for PlacementOps

### Architecture decisions

1. **Use a two-level status model everywhere:** A coarse `status` field (matching FHIR Task.status values) + a fine-grained `business_status` field (operational states specific to your workflow). This gives you FHIR compatibility and operational flexibility without over-engineering.

2. **Seed from ADT, not manual entry (eventually):** Design your `census_entries` and `patients` tables to be compatible with HL7 ADT A01-A08 message fields. Intake staff log census manually at first, but the schema should support automated ADT feed upgrade later.

3. **Event sourcing for audit, not for application state:** Full CQRS/event sourcing is overkill. Use a simple `audit_events` append-only table that your middleware writes to on every state change and PHI access. This satisfies HIPAA without the complexity of rebuilding state from events.

4. **Multi-tenancy via RLS, defense-in-depth:** Store `tenant_id` in JWT `app_metadata` (Supabase-controlled, not user-editable). Apply RLS policies on every PHI-bearing table. Enforce `tenant_id` in FastAPI middleware as a second layer. Never pass user-supplied `tenant_id` to queries directly.

5. **Use python-statemachine for workflow transitions:** Declare placement case and referral state machines explicitly. Wire `on_enter_*` callbacks to write audit events and fire background tasks (Celery). This prevents silent state mutations and makes the workflow self-documenting.

6. **Build the "package tracking" view first:** The highest-ROI feature is bidirectional real-time visibility. Coordinators and clinical reviewers should see the same timeline for a patient. Build this view before building matching algorithms.

7. **Document patient choice explicitly:** CMS CoP requires it. Create a `patient_choice_records` table linked to each placement case. Capture: options presented, patient/family decision, documented date, staff who obtained consent.

### What NOT to build initially

- Do not build automated level-of-care determination that makes binding decisions. Surface clinical criteria checklists and historical data; let the clinical reviewer make the call.
- Do not build a full FHIR server. Model your schemas after FHIR resources, but expose your own API.
- Do not build real-time HL7 ADT integration in Phase 1. Build a clean CSV/Excel import that populates the same tables the ADT integration will use later.
