# PlacementOps — Unified Master Build Plan

## Document Purpose
This is the single source of truth for building PlacementOps. It consolidates the master product spec, database schema, API contracts, frontend architecture, workflow state machines, and the deferred Voice AI module (formerly CareFlow AI) into one engineering-ready document.

**Rule: If it's not in this document, it's not in scope.**

---

## Part 1: Product Definition

### 1.1 What PlacementOps Is
A post-acute placement operating system that turns daily hospital census data and clinician review into fast, trackable, facility-matched discharge workflows.

Simpler: Intake → Clinical Review → Facility Matching → Staff-Approved Outreach → Outcome Tracking.

### 1.2 What It Replaces
- Spreadsheets emailed from offshore intake staff
- Manual facility phone trees from placement coordinators
- Sticky-note tracking of who was called and what they said
- Institutional knowledge locked in individual staff members' heads
- Unstructured email chains between hospitals, facilities, and internal teams

### 1.3 What It Is Not (Phase 1)
- A fully autonomous clinical decision maker
- A replacement for clinician judgment
- A full EHR
- A fully automated PHI email robot
- A voice-calling-first product (voice is Phase 2)

### 1.4 Core Operating Model
1. Overnight staff in India log into PlacementOps and enter/update patient census and intake data directly via web forms
2. Spreadsheet upload remains as a fallback import path
3. U.S.-based clinical staff review hospital notes and enter structured placement recommendations
4. The system matches patients to best-fit SNF/IRF/LTACH facilities based on geography, payer, capabilities, and preferences
5. Placement coordinators review matches, approve outreach drafts, and send communications
6. The system tracks outreach, responses, declines, and final placement outcomes
7. Managers monitor queue health, performance metrics, and bottlenecks

---

## Part 2: Users & Roles

### 2.1 User Types

**Offshore Intake Staff** — Enter and maintain daily patient intake data from hospital sources. Default landing: Intake Workbench.

**Clinical Reviewers** — Read hospital notes, enter structured placement assessments. Default landing: Operations Queue filtered to "Needs Clinical Review."

**Placement Coordinators** — Review facility options, approve outreach, track responses. Default landing: Operations Queue filtered to active outreach states.

**Managers / Supervisors** — Operational oversight, reporting, bottleneck identification. Default landing: Manager Dashboard.

**Admins** — System configuration, user management, facility data, templates. Default landing: Admin Settings.

### 2.2 Role Permissions Summary

| Action | Intake Staff | Clinical Reviewer | Placement Coordinator | Manager | Admin |
|--------|:-----------:|:-----------------:|:--------------------:|:-------:|:-----:|
| Create/edit cases | ✓ | | | | ✓ |
| Mark intake complete | ✓ | | | | ✓ |
| Enter clinical assessment | | ✓ | | | ✓ |
| Generate facility matches | | ✓ | ✓ | | ✓ |
| Create outreach drafts | | | ✓ | | ✓ |
| Approve outreach | | | ✓ | ✓ | ✓ |
| Log outcomes | | | ✓ | ✓ | ✓ |
| View analytics | | | | ✓ | ✓ |
| Manage facilities/users | | | | | ✓ |
| Close/reopen cases | | | | ✓ | ✓ |

---

## Part 3: Technical Architecture

### 3.1 Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js, TypeScript, Tailwind CSS, shadcn/ui |
| Backend | FastAPI (Python), REST API |
| Database | PostgreSQL via Supabase |
| File Storage | Supabase Storage |
| Auth | Supabase Auth |
| Background Jobs | Celery or lightweight queue |
| Voice AI (Phase 2) | Twilio SIP + LiveKit Agents + OpenAI Realtime API |

### 3.2 Application Structure (Modular Monolith)

```
placementops/
├── modules/
│   ├── auth/           # users, roles, sessions
│   ├── intake/         # case creation, spreadsheet import, validation
│   ├── clinical/       # assessments, review workflow
│   ├── facilities/     # directory, capabilities, insurance rules, preferences
│   ├── matching/       # scoring engine, match generation, explanations
│   ├── outreach/       # drafts, approvals, templates, tracking
│   ├── outcomes/       # acceptance, decline, placement logging
│   ├── analytics/      # dashboards, KPIs, reporting queries
│   └── voice/          # Phase 2: Twilio/LiveKit/OpenAI Realtime
├── core/               # shared: db models, auth middleware, audit, events
├── api/                # FastAPI routers importing from modules
└── main.py
```

Each module owns its domain logic and models. Modules communicate through Python function calls, not HTTP. One database, one deployment, one repo.

**Exception:** The voice AI agent (Phase 2) runs as a separate process in the same repo — long-lived WebSocket audio streams have different runtime characteristics than request/response endpoints.

### 3.3 API Design Principles
- REST-first with JSON request/response
- UUID identifiers for all major entities
- Server-side validation for workflow transitions
- Role-aware authorization on all mutating endpoints
- Base path: `/api/v1`
- Content type: `application/json`
- Bearer token or secure session auth

**Success envelope:**
```json
{
  "data": {},
  "meta": {},
  "error": null
}
```

**Error envelope:**
```json
{
  "data": null,
  "meta": {},
  "error": {
    "code": "validation_error",
    "message": "insurance_primary is required",
    "details": { "field": "insurance_primary" }
  }
}
```

**Error codes:** `validation_error`, `not_found`, `unauthorized`, `forbidden`, `invalid_transition`, `conflict`, `duplicate_record`, `internal_error`

---

## Part 4: Database Schema

### 4.1 Tables Overview

**Identity & Access:** organizations, users, roles, user_roles

**Operational Case Data:** patient_cases, patient_case_identifiers, intake_submissions, intake_field_issues, clinical_assessments, case_assignments, case_status_history

**Facility Intelligence:** facilities, facility_contacts, facility_capabilities, facility_insurance_rules, facility_preferences

**Matching & Outreach:** facility_matches, outreach_actions, outreach_recipients, outreach_templates

**Outcomes & Activity:** placement_outcomes, case_activity_events, audit_events

**Imports & Reference:** import_jobs, import_row_results, payer_reference, decline_reason_reference, hospital_reference

### 4.2 Core Table Definitions

#### organizations
| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK |
| name | text | NOT NULL |
| slug | text | UNIQUE, NOT NULL |
| status | text | NOT NULL, default 'active' |
| created_at | timestamptz | NOT NULL |
| updated_at | timestamptz | NOT NULL |

#### users
| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK |
| organization_id | uuid | FK → organizations |
| email | text | UNIQUE, NOT NULL |
| full_name | text | NOT NULL |
| status | text | NOT NULL, default 'active' |
| timezone | text | NULL |
| default_hospital_id | uuid | FK → hospital_reference, NULL |
| created_at | timestamptz | NOT NULL |
| updated_at | timestamptz | NOT NULL |

#### roles
| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK |
| role_key | text | UNIQUE, NOT NULL |
| role_name | text | NOT NULL |
| description | text | NULL |

Seed: admin, intake_staff, clinical_reviewer, placement_coordinator, manager, read_only

#### user_roles
| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK |
| user_id | uuid | FK → users |
| role_id | uuid | FK → roles |
| created_at | timestamptz | NOT NULL |

Constraint: UNIQUE(user_id, role_id)

#### hospital_reference
| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK |
| organization_id | uuid | FK → organizations |
| hospital_name | text | NOT NULL |
| market_name | text | NULL |
| city | text | NULL |
| state | text | NULL |
| active_status | boolean | NOT NULL, default true |
| created_at | timestamptz | NOT NULL |
| updated_at | timestamptz | NOT NULL |

#### patient_cases
| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK |
| organization_id | uuid | FK → organizations |
| hospital_id | uuid | FK → hospital_reference |
| external_case_id | text | NULL |
| patient_name | text | NOT NULL |
| dob | date | NULL |
| mrn | text | NULL |
| hospital_unit | text | NULL |
| room_number | text | NULL |
| admission_date | date | NULL |
| primary_diagnosis_text | text | NULL |
| insurance_primary | text | NULL |
| insurance_secondary | text | NULL |
| patient_zip | text | NULL |
| preferred_geography_text | text | NULL |
| discharge_target_date | date | NULL |
| current_status | text | NOT NULL |
| priority_level | text | NULL |
| intake_complete | boolean | NOT NULL, default false |
| active_case_flag | boolean | NOT NULL, default true |
| created_by_user_id | uuid | FK → users, NULL |
| updated_by_user_id | uuid | FK → users, NULL |
| created_at | timestamptz | NOT NULL |
| updated_at | timestamptz | NOT NULL |

Indexes: (organization_id, current_status), (hospital_id, active_case_flag), (mrn), (patient_name, dob)

#### patient_case_identifiers
| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK |
| patient_case_id | uuid | FK → patient_cases |
| identifier_type | text | NOT NULL |
| identifier_value | text | NOT NULL |
| source_system | text | NULL |
| created_at | timestamptz | NOT NULL |

#### intake_submissions
| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK |
| patient_case_id | uuid | FK → patient_cases |
| source_type | text | NOT NULL (web_form, spreadsheet_import, api_feed) |
| import_job_id | uuid | FK → import_jobs, NULL |
| submitted_by_user_id | uuid | FK → users, NULL |
| raw_payload_json | jsonb | NOT NULL |
| normalized_payload_json | jsonb | NULL |
| submission_status | text | NOT NULL |
| submitted_at | timestamptz | NOT NULL |
| processed_at | timestamptz | NULL |

#### intake_field_issues
| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK |
| patient_case_id | uuid | FK → patient_cases |
| intake_submission_id | uuid | FK → intake_submissions, NULL |
| field_name | text | NOT NULL |
| issue_type | text | NOT NULL |
| issue_message | text | NOT NULL |
| resolved_flag | boolean | NOT NULL, default false |
| resolved_by_user_id | uuid | FK → users, NULL |
| resolved_at | timestamptz | NULL |
| created_at | timestamptz | NOT NULL |

#### clinical_assessments
| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK |
| patient_case_id | uuid | FK → patient_cases |
| reviewer_user_id | uuid | FK → users |
| recommended_level_of_care | text | NOT NULL |
| confidence_level | text | NULL |
| clinical_summary | text | NULL |
| rehab_tolerance | text | NULL |
| mobility_status | text | NULL |
| oxygen_required | boolean | NOT NULL, default false |
| trach | boolean | NOT NULL, default false |
| vent | boolean | NOT NULL, default false |
| dialysis_required | boolean | NOT NULL, default false |
| dialysis_type | text | NULL |
| in_house_hd_required | boolean | NOT NULL, default false |
| wound_care_needs | boolean | NOT NULL, default false |
| iv_antibiotics | boolean | NOT NULL, default false |
| tpn | boolean | NOT NULL, default false |
| isolation_precautions | text | NULL |
| psych_behavior_flags | text | NULL |
| bariatric_needs | boolean | NOT NULL, default false |
| special_equipment_needs | text | NULL |
| barriers_to_placement | text | NULL |
| payer_notes | text | NULL |
| family_preference_notes | text | NULL |
| review_status | text | NOT NULL, default 'draft' |
| created_at | timestamptz | NOT NULL |
| updated_at | timestamptz | NOT NULL |

Indexes: (patient_case_id, created_at DESC), (recommended_level_of_care)

#### case_assignments
| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK |
| patient_case_id | uuid | FK → patient_cases |
| assigned_user_id | uuid | FK → users |
| assignment_role | text | NOT NULL |
| active_flag | boolean | NOT NULL, default true |
| assigned_by_user_id | uuid | FK → users, NULL |
| assigned_at | timestamptz | NOT NULL |
| unassigned_at | timestamptz | NULL |

#### case_status_history
| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK |
| patient_case_id | uuid | FK → patient_cases |
| old_status | text | NULL |
| new_status | text | NOT NULL |
| changed_by_user_id | uuid | FK → users, NULL |
| reason_text | text | NULL |
| changed_at | timestamptz | NOT NULL |

#### facilities
| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK |
| organization_id | uuid | FK → organizations |
| facility_name | text | NOT NULL |
| facility_type | text | NOT NULL |
| address_line_1 | text | NULL |
| address_line_2 | text | NULL |
| city | text | NULL |
| county | text | NULL |
| state | text | NULL |
| zip | text | NULL |
| latitude | numeric | NULL |
| longitude | numeric | NULL |
| active_status | boolean | NOT NULL, default true |
| notes | text | NULL |
| created_at | timestamptz | NOT NULL |
| updated_at | timestamptz | NOT NULL |

Indexes: (facility_type, active_status), (county, state)

#### facility_contacts
| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK |
| facility_id | uuid | FK → facilities |
| contact_name | text | NULL |
| contact_role | text | NULL |
| email | text | NULL |
| phone | text | NULL |
| phone_extension | text | NULL |
| fax_number | text | NULL |
| preferred_contact_method | text | NULL |
| best_call_window | text | NULL |
| active_flag | boolean | NOT NULL, default true |
| notes | text | NULL |
| created_at | timestamptz | NOT NULL |
| updated_at | timestamptz | NOT NULL |

Note: `phone_extension` and `best_call_window` are additions for Phase 2 voice support — included now to avoid schema migration later.

#### facility_capabilities
| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK |
| facility_id | uuid | UNIQUE, FK → facilities |
| accepts_snf | boolean | NOT NULL, default false |
| accepts_irf | boolean | NOT NULL, default false |
| accepts_ltach | boolean | NOT NULL, default false |
| accepts_trach | boolean | NOT NULL, default false |
| accepts_vent | boolean | NOT NULL, default false |
| accepts_hd | boolean | NOT NULL, default false |
| in_house_hemodialysis | boolean | NOT NULL, default false |
| accepts_peritoneal_dialysis | boolean | NOT NULL, default false |
| accepts_wound_vac | boolean | NOT NULL, default false |
| accepts_iv_antibiotics | boolean | NOT NULL, default false |
| accepts_tpn | boolean | NOT NULL, default false |
| accepts_bariatric | boolean | NOT NULL, default false |
| accepts_behavioral_complexity | boolean | NOT NULL, default false |
| accepts_memory_care | boolean | NOT NULL, default false |
| accepts_isolation_cases | boolean | NOT NULL, default false |
| weekend_admissions | boolean | NOT NULL, default false |
| after_hours_admissions | boolean | NOT NULL, default false |
| last_verified_at | timestamptz | NULL |
| updated_by_user_id | uuid | FK → users, NULL |
| created_at | timestamptz | NOT NULL |
| updated_at | timestamptz | NOT NULL |

#### facility_insurance_rules
| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK |
| facility_id | uuid | FK → facilities |
| payer_name | text | NOT NULL |
| plan_name | text | NULL |
| plan_type | text | NULL |
| accepted_status | text | NOT NULL |
| prior_auth_required | boolean | NOT NULL, default false |
| notes | text | NULL |
| last_verified_at | timestamptz | NULL |
| updated_by_user_id | uuid | FK → users, NULL |
| created_at | timestamptz | NOT NULL |
| updated_at | timestamptz | NOT NULL |

#### facility_preferences
| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK |
| organization_id | uuid | FK → organizations |
| facility_id | uuid | FK → facilities |
| preference_scope | text | NOT NULL (global, market, hospital) |
| scope_reference_id | uuid | NULL |
| preference_rank | integer | NULL |
| preferred_flag | boolean | NOT NULL, default false |
| notes | text | NULL |
| created_at | timestamptz | NOT NULL |
| updated_at | timestamptz | NOT NULL |

#### facility_matches
| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK |
| patient_case_id | uuid | FK → patient_cases |
| facility_id | uuid | FK → facilities |
| assessment_id | uuid | FK → clinical_assessments, NULL |
| overall_score | numeric | NOT NULL |
| payer_fit_score | numeric | NULL |
| clinical_fit_score | numeric | NULL |
| geography_score | numeric | NULL |
| preference_score | numeric | NULL |
| availability_score | numeric | NULL |
| acceptance_probability | numeric | NULL |
| rank_order | integer | NOT NULL |
| is_recommended | boolean | NOT NULL, default false |
| blockers_json | jsonb | NULL |
| explanation_text | text | NULL |
| generated_by | text | NOT NULL, default 'rules_engine' |
| generated_at | timestamptz | NOT NULL |

Indexes: (patient_case_id, rank_order), (patient_case_id, generated_at DESC)

#### outreach_templates
| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK |
| organization_id | uuid | FK → organizations |
| template_key | text | UNIQUE, NOT NULL |
| template_name | text | NOT NULL |
| template_type | text | NOT NULL, default 'email' |
| channel | text | NOT NULL |
| audience_type | text | NOT NULL |
| subject_template | text | NULL |
| body_template | text | NOT NULL |
| active_flag | boolean | NOT NULL, default true |
| created_at | timestamptz | NOT NULL |
| updated_at | timestamptz | NOT NULL |

Note: `template_type` supports 'email', 'sms', 'voice_ai_script' (Phase 2). Added now for forward compatibility.

#### outreach_actions
| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK |
| patient_case_id | uuid | FK → patient_cases |
| facility_id | uuid | FK → facilities, NULL |
| template_id | uuid | FK → outreach_templates, NULL |
| action_type | text | NOT NULL |
| channel | text | NOT NULL |
| draft_subject | text | NULL |
| draft_body | text | NOT NULL |
| approval_status | text | NOT NULL |
| approved_by_user_id | uuid | FK → users, NULL |
| approved_at | timestamptz | NULL |
| sent_by_user_id | uuid | FK → users, NULL |
| sent_at | timestamptz | NULL |
| delivery_status | text | NULL |
| external_reference_id | text | NULL |
| call_transcript_url | text | NULL |
| call_duration_seconds | integer | NULL |
| call_outcome_summary | text | NULL |
| created_by_user_id | uuid | FK → users, NULL |
| created_at | timestamptz | NOT NULL |
| updated_at | timestamptz | NOT NULL |

Channel enum: email, sms, phone_manual, voicemail_drop, voice_ai, task, portal
Action type enum: facility_outreach, internal_alert, cm_update, follow_up_reminder
Approval status enum: draft, pending_approval, approved, sent, canceled, failed

Note: `call_transcript_url`, `call_duration_seconds`, `call_outcome_summary` are Phase 2 voice fields — included now to avoid migration.

#### outreach_recipients
| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK |
| outreach_action_id | uuid | FK → outreach_actions |
| recipient_type | text | NOT NULL |
| recipient_name | text | NULL |
| recipient_address | text | NOT NULL |
| created_at | timestamptz | NOT NULL |

#### placement_outcomes
| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK |
| patient_case_id | uuid | FK → patient_cases |
| facility_id | uuid | FK → facilities, NULL |
| outcome_type | text | NOT NULL |
| source_channel | text | NULL |
| decline_reason_code | text | NULL |
| decline_reason_text | text | NULL |
| event_notes | text | NULL |
| effective_at | timestamptz | NOT NULL |
| recorded_by_user_id | uuid | FK → users, NULL |
| created_at | timestamptz | NOT NULL |

Outcome types: pending_review, accepted, declined, placed, family_declined, withdrawn
Source channel: email, phone_manual, voice_ai, sms, portal (Phase 2 addition — included now)

#### case_activity_events
| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK |
| patient_case_id | uuid | FK → patient_cases |
| event_type | text | NOT NULL |
| event_summary | text | NOT NULL |
| event_payload_json | jsonb | NULL |
| actor_user_id | uuid | FK → users, NULL |
| created_at | timestamptz | NOT NULL |

#### audit_events
| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK |
| organization_id | uuid | FK → organizations |
| entity_type | text | NOT NULL |
| entity_id | uuid | NOT NULL |
| event_type | text | NOT NULL |
| old_value_json | jsonb | NULL |
| new_value_json | jsonb | NULL |
| actor_user_id | uuid | FK → users, NULL |
| created_at | timestamptz | NOT NULL |

#### import_jobs
| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK |
| organization_id | uuid | FK → organizations |
| uploaded_by_user_id | uuid | FK → users |
| source_name | text | NULL |
| original_filename | text | NOT NULL |
| mapping_template_name | text | NULL |
| job_status | text | NOT NULL |
| total_rows | integer | NULL |
| rows_created | integer | NULL |
| rows_updated | integer | NULL |
| rows_failed | integer | NULL |
| started_at | timestamptz | NOT NULL |
| completed_at | timestamptz | NULL |
| created_at | timestamptz | NOT NULL |

#### import_row_results
| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK |
| import_job_id | uuid | FK → import_jobs |
| row_number | integer | NOT NULL |
| action_taken | text | NOT NULL |
| patient_case_id | uuid | FK → patient_cases, NULL |
| error_message | text | NULL |
| raw_row_json | jsonb | NOT NULL |
| normalized_row_json | jsonb | NULL |
| created_at | timestamptz | NOT NULL |

#### payer_reference
| Column | Type | Constraints |
|--------|------|-------------|
| id | uuid | PK |
| payer_name | text | UNIQUE, NOT NULL |
| payer_category | text | NULL |
| active_flag | boolean | NOT NULL, default true |
| created_at | timestamptz | NOT NULL |

#### decline_reason_reference
| Column | Type | Constraints |
|--------|------|-------------|
| code | text | PK |
| display_name | text | NOT NULL |
| description | text | NULL |
| active_flag | boolean | NOT NULL, default true |
| sort_order | integer | NULL |

Seed: payer_not_accepted, no_bed_available, wrong_level_of_care, dialysis_not_supported, trach_not_supported, vent_not_supported, behavior_too_complex, acuity_too_high, documentation_incomplete, auth_pending, family_declined, unknown

### 4.3 Key Relationships
- organizations 1:N users, patient_cases, facilities
- hospital_reference 1:N patient_cases
- patient_cases 1:N intake_submissions, clinical_assessments, case_assignments, case_status_history, facility_matches, outreach_actions, placement_outcomes, case_activity_events
- facilities 1:1 facility_capabilities
- facilities 1:N facility_contacts, facility_insurance_rules, facility_matches, outreach_actions, placement_outcomes

### 4.4 Schema Design Rules
- UUID primary keys everywhere
- Text fields for enums initially (migrate to DB enums once stable)
- created_at and updated_at on every mutable table
- Preserve raw intake payloads for debugging
- Keep multiple assessment versions rather than destructive overwrite
- Add partial indexes later based on real usage patterns

### 4.5 Future Schema Extensions (Not In Scope Now)
bed_availability_snapshots, hospital_api_sync_runs, referral_packets, document_uploads, insurance_authorizations, patient_preference_contacts, distance_cache, facility_performance_metrics (materialized views), voice_call_recordings, voice_call_transcripts

---

## Part 5: Workflow State Machine

### 5.1 Patient Case States

```
new → intake_in_progress → intake_complete → needs_clinical_review
→ under_clinical_review → ready_for_matching → facility_options_generated
→ outreach_pending_approval → outreach_in_progress → pending_facility_response
→ accepted → placed
                                                    → declined_retry_needed (loops back to ready_for_matching)
Any active state → closed
```

### 5.2 State Definitions

| State | Meaning | Allowed Actors |
|-------|---------|---------------|
| new | Case created, intake not started | intake_staff, admin |
| intake_in_progress | Intake team actively entering data | intake_staff, admin |
| intake_complete | Minimum required info provided | intake_staff, admin |
| needs_clinical_review | Ready for clinician review | system (auto from intake_complete) |
| under_clinical_review | Reviewer actively working | clinical_reviewer, admin |
| ready_for_matching | Finalized assessment exists | clinical_reviewer, admin |
| facility_options_generated | Matching engine has run | system, placement_coordinator |
| outreach_pending_approval | Drafts created, awaiting review | placement_coordinator, admin |
| outreach_in_progress | Approved drafts being sent | placement_coordinator, admin |
| pending_facility_response | Waiting for facility replies | placement_coordinator, admin |
| accepted | At least one facility accepted | placement_coordinator, manager, admin |
| declined_retry_needed | All paths declined, needs new approach | placement_coordinator, manager, admin |
| placed | Final placement confirmed | placement_coordinator, manager, admin |
| closed | Case closed for any reason | manager, admin |

### 5.3 Required Conditions for Key Transitions

| Transition | Required Conditions |
|-----------|-------------------|
| intake_in_progress → intake_complete | Required intake fields present, duplicate warning acknowledged |
| needs_clinical_review → under_clinical_review | Reviewer assigned or active session |
| under_clinical_review → ready_for_matching | Finalized assessment exists, level of care set |
| ready_for_matching → facility_options_generated | Valid assessment, matching engine run, at least one candidate or explicit no-match |
| facility_options_generated → outreach_pending_approval | At least one facility selected, at least one draft created |
| outreach_pending_approval → outreach_in_progress | All required drafts approved |
| outreach_in_progress → pending_facility_response | At least one outreach marked sent |
| pending_facility_response → accepted | Accepted outcome logged |
| pending_facility_response → declined_retry_needed | All active paths resolved negatively |
| accepted → placed | Final facility recorded, placement event documented |
| Any → closed | Closure reason provided, user has close permission |

### 5.4 Backward Transitions (Always Require Reason + Audit Log)
- Missing insurance discovered → intake_in_progress
- Clinical status worsens → under_clinical_review
- Matches become invalid → ready_for_matching
- Accepted placement collapses → declined_retry_needed

### 5.5 Outreach Action States

```
draft → pending_approval → approved → sent
draft → canceled
pending_approval → canceled
approved → failed → draft (if regenerated)
```

### 5.6 SLA / Aging Rules
- needs_clinical_review > 4 hours: yellow flag
- under_clinical_review > 8 hours: yellow flag
- outreach_pending_approval > 2 hours: yellow flag
- pending_facility_response > 24 hours: yellow flag
- pending_facility_response > 48 hours: red flag
- declined_retry_needed > 8 hours: red flag

### 5.7 Automated System Events
- Auto-move new → intake_in_progress on first save
- Auto-move intake_complete → needs_clinical_review when validation passes
- Auto-generate stale-case reminders if pending_facility_response exceeds threshold
- Auto-flag outreach as failed if send service returns error

---

## Part 6: API Contract

### 6.1 Authentication
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | /api/v1/auth/login | Authenticate user |
| POST | /api/v1/auth/logout | Invalidate session |
| GET | /api/v1/auth/me | Current user + roles |

### 6.2 Cases
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | /api/v1/cases | Create case |
| GET | /api/v1/cases | List with filters (status, hospital_id, assigned_user_id, priority, search, page) |
| GET | /api/v1/cases/{case_id} | Full case detail |
| PATCH | /api/v1/cases/{case_id} | Update editable fields |
| POST | /api/v1/cases/{case_id}/mark-intake-complete | Advance to intake_complete |
| POST | /api/v1/cases/{case_id}/assign | Assign to user + role |
| POST | /api/v1/cases/{case_id}/status-transition | Move through state machine |

### 6.3 Intake
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | /api/v1/cases/{case_id}/intake-submissions | Create intake record |
| GET | /api/v1/cases/{case_id}/intake-submissions | List intake records |
| GET | /api/v1/queues/intake | Intake queue |

### 6.4 Imports
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | /api/v1/imports | Create import job |
| POST | /api/v1/imports/{import_id}/map-columns | Save column mappings |
| POST | /api/v1/imports/{import_id}/validate | Validate rows |
| POST | /api/v1/imports/{import_id}/commit | Commit to create/update cases |
| GET | /api/v1/imports/{import_id} | Import summary |

### 6.5 Clinical Review
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | /api/v1/cases/{case_id}/assessments | Create assessment |
| PATCH | /api/v1/assessments/{assessment_id} | Update assessment |
| GET | /api/v1/cases/{case_id}/assessments | List assessments |

### 6.6 Facilities
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | /api/v1/facilities | List with filters |
| POST | /api/v1/facilities | Create facility |
| GET | /api/v1/facilities/{facility_id} | Facility detail |
| PATCH | /api/v1/facilities/{facility_id} | Update profile |
| PUT | /api/v1/facilities/{facility_id}/capabilities | Set capability matrix |
| GET | /api/v1/facilities/{facility_id}/insurance-rules | List payer rules |
| POST | /api/v1/facilities/{facility_id}/insurance-rules | Add payer rule |
| PATCH | /api/v1/insurance-rules/{rule_id} | Update payer rule |

### 6.7 Matching
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | /api/v1/cases/{case_id}/matches/generate | Generate ranked matches |
| GET | /api/v1/cases/{case_id}/matches | Get latest/historical matches |

### 6.8 Outreach
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | /api/v1/cases/{case_id}/outreach-actions | Create draft(s) |
| GET | /api/v1/cases/{case_id}/outreach-actions | List outreach for case |
| PATCH | /api/v1/outreach-actions/{action_id} | Edit draft |
| POST | /api/v1/outreach-actions/{action_id}/submit-for-approval | Move to pending |
| POST | /api/v1/outreach-actions/{action_id}/approve | Approve |
| POST | /api/v1/outreach-actions/{action_id}/mark-sent | Mark sent |
| POST | /api/v1/outreach-actions/{action_id}/cancel | Cancel |

### 6.9 Outcomes & Timeline
| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | /api/v1/cases/{case_id}/outcomes | Log acceptance/decline/placement |
| GET | /api/v1/cases/{case_id}/timeline | Chronological activity feed |

### 6.10 Queues
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | /api/v1/queues/operations | Main daily queue (filterable) |
| GET | /api/v1/queues/outreach | Cases with pending outreach |
| GET | /api/v1/queues/manager-summary | Manager metrics + aging |

### 6.11 Admin & Reference
| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | /api/v1/reference/hospitals | List hospitals |
| GET | /api/v1/reference/decline-reasons | List decline codes |
| GET | /api/v1/reference/payers | List payers |
| GET | /api/v1/templates/outreach | List templates |
| POST | /api/v1/templates/outreach | Create template |
| PATCH | /api/v1/templates/outreach/{template_id} | Update template |

---

## Part 7: Frontend Architecture

### 7.1 Navigation Structure

**Left sidebar:**
1. Dashboard
2. Intake Workbench
3. Operations Queue
4. Facilities
5. Outreach
6. Analytics
7. Admin

**Top bar:** Global search, hospital/market filter, notifications, user menu

### 7.2 Screen Inventory

| Screen | Primary Users | Purpose |
|--------|--------------|---------|
| Dashboard | Managers, coordinators | KPIs, queue widgets, alerts, bottlenecks |
| Intake Workbench | Offshore intake staff | Daily census table, create/edit patients, spreadsheet import |
| Spreadsheet Import | Intake staff, admins | Upload, map, validate, commit CSV/XLSX |
| Operations Queue | Reviewers, coordinators, managers | Central queue with status tabs, dense case table |
| Patient Case Detail | All operational users | Single source of truth: tabs for Overview, Clinical Review, Matches, Outreach, Timeline, Audit |
| Facility Directory | Coordinators, admins | Searchable facility list with capability/payer/preference filters |
| Facility Detail | Coordinators, admins | Full profile: Overview, Capabilities, Insurance, Contacts, Notes |
| Outreach Dashboard | Coordinators, managers | Cross-case outreach queue by status |
| Analytics Dashboard | Managers | Queue aging, acceptance rates, decline reasons, turnaround times |
| Admin Settings | Admins | Users, roles, facilities, templates, decline reasons, hospitals |

### 7.3 Patient Case Detail Tabs

**Overview** — Summary cards: intake, clinical, best facilities, outreach status, recent timeline

**Clinical Review** — 2-column form: level of care selector, confidence, rehab tolerance, mobility, payer notes, family preferences (left); special needs checklist, barriers, clinical summary textarea (right)

**Facility Matches** — Generate/Regenerate button, ranked facility cards (name, type, distance, score, fit indicators, preferred badge, blockers, explanation, select-for-outreach), optional table comparison view

**Outreach** — Create button, draft list (facility, type, channel, approval status, sent status), draft editor (subject, body, recipients, approve/send/cancel)

**Timeline** — Event filter chips, chronological feed with actor, type, summary, expandable details

**Audit** — Technical before/after change table for admins

### 7.4 Persistent Action Bar (Case Detail)
Every case detail screen shows: Save, Change Status, Assign, Generate Matches, Create Outreach, Log Outcome

### 7.5 Reusable Component Inventory
StatusBadge, PriorityBadge, AgingFlag, CaseTable, FacilityCard, ActivityTimeline, DraftEditor, FilterBar, AssignmentPicker, ActionToolbar, EmptyStatePanel, DuplicateWarningCard, CompletenessChecklist

### 7.6 UX Principles
- Desktop-first, dense operational UI
- Minimize clicks for repetitive daily tasks
- Drawers for quick edits (don't lose queue position)
- Make blockers and required fields visually obvious
- Match explanations must be transparent (no black box)
- Separate audit trail from human-friendly timeline
- Role-specific default views

---

## Part 8: Matching Engine

### 8.1 Matching Inputs
- Recommended level of care (from clinical assessment)
- Insurance acceptance (from facility insurance rules)
- Required clinical capabilities (from assessment structured fields)
- Geography/distance (patient zip vs facility location)
- Preferred facility status (from facility preferences)
- Patient/family preference (from assessment notes)

### 8.2 Scoring Weights
| Factor | Weight | Type |
|--------|--------|------|
| Payer accepted | Very high | Hard filter or heavy score |
| Required capability present | Mandatory | Hard exclusion if missing |
| Level of care fit | Very high | Hard filter |
| Geography fit | Medium-high | Distance-based score |
| Preferred facility bonus | Medium | Additive |
| Historical acceptance rate | Later bonus | Phase 2+ |
| Bed availability | Later strong bonus | Phase 2+ |

### 8.3 Hard Exclusions
- Facility does not accept patient's payer
- Facility lacks mandatory clinical capability (e.g., patient needs HD, facility has no HD)
- Facility type doesn't match recommended level of care

### 8.4 Output Per Match
- Facility name, type, location, distance
- Overall score + component scores
- Rank order
- is_recommended flag
- Blockers/caveats (structured JSON)
- Explanation text (human-readable)
- Select-for-outreach action

---

## Part 9: Communication & Outreach Model

### 9.1 Core Principle
Nothing patient-specific goes out automatically without staff confirmation (Phase 1). Structured facility inquiry calls may be AI-automated (Phase 2).

### 9.2 Supported Channels
| Channel | Phase | Approval Required |
|---------|-------|:-----------------:|
| email | 1 | Yes |
| phone_manual | 1 | No (coordinator calls directly, logs result) |
| task | 1 | No (internal) |
| sms | 2 | Yes |
| voicemail_drop | 2 | Configurable |
| voice_ai | 2 | Configurable (auto for structured inquiries, approval for PHI) |

### 9.3 Outreach Approval Flow
1. System or coordinator creates draft
2. Staff reviews and edits
3. Staff approves
4. Staff sends or marks sent
5. System tracks delivery + response

### 9.4 Outreach Templates
Support template types: email (Phase 1), sms (Phase 2), voice_ai_script (Phase 2). Templates use variable substitution for patient/facility/case data.

---

## Part 10: Phase 2 — Voice AI Module

### 10.1 Purpose
Replace manual phone calls to facility admissions with AI-driven real-time voice calls that ask structured questions and report results back to PlacementOps automatically.

### 10.2 Architecture
```
PlacementOps Backend (FastAPI + Supabase)
         ↕ function calls (bed status, placement updates, call logging)
Twilio SIP ←→ LiveKit Agents (media bridge) ←→ OpenAI Realtime API (speech-to-speech)
```

### 10.3 Why Speech-to-Speech
Traditional STT → LLM → TTS adds 1.5–3s latency per turn. OpenAI Realtime API processes audio natively at sub-500ms, creating natural conversation flow that facility admissions staff won't hang up on.

### 10.4 Voice Call Flow
1. Coordinator selects facility from match results
2. Clicks "Call via AI" (or batch-calls multiple facilities)
3. System creates outreach_action with channel: "voice_ai"
4. Voice agent dials facility admissions phone (from facility_contacts)
5. Agent uses system prompt built from: patient clinical summary (de-identified as needed), insurance, required capabilities
6. Agent asks: bed availability, payer acceptance, admission timeline, required documents
7. Call transcript + structured outcome auto-logged to PlacementOps
8. Case status updated based on facility response

### 10.5 What the Voice Agent Does NOT Do
- Disclose PHI without explicit approval workflow
- Make autonomous placement decisions
- Send referral packets
- Commit to admissions dates

### 10.6 Starter Repos for Build
| Repo | Why |
|------|-----|
| twilio-samples/speech-assistant-openai-realtime-api-python | FastAPI + OpenAI Realtime, closest to PlacementOps stack |
| pBread/twilio-agentic-voice-assistant | ConversationRelay + agentic patterns, HIPAA eligible |
| danieladdisonorg/livekit-voice-agent | Production LiveKit + Twilio SIP, function calling |
| livekit-examples/livekit-sip-agent-example | Official LiveKit SIP example |
| openai/openai-realtime-twilio-demo | OpenAI's own reference implementation |

### 10.7 Cost Model
~$0.06–0.10/min for OpenAI Realtime. Calls are 2–5 minutes (structured facility inquiry). At 50 calls/day = ~$15–25/day.

---

## Part 11: Build Sequence

### Phase 1 — Core Platform (Sprints 1-8)

**Sprint 1:** Auth, database schema, facility model, basic case model, intake harness skeleton

**Sprint 2:** Intake workbench UI, patient creation/edit flows, required field validation, spreadsheet upload fallback, column mapping, import review/commit, work queue page

**Sprint 3:** Patient case detail page, clinical assessment form, status model, audit logging

**Sprint 4:** Facility directory, capability matrix, insurance matrix, search/filter

**Sprint 5:** Matching engine v1, case-to-facility ranking, explanations and blockers

**Sprint 6:** Outreach draft generation, approval workflow, outreach tracking dashboard

**Sprint 7:** Decline reason logging, analytics dashboard v1, manager views

**Sprint 8:** Polish, QA, permission controls, export/reporting

### Phase 2 — Voice AI + Extended Outreach (Sprints 9-14)

**Sprint 9:** SMS outreach channel, voicemail drop integration (Twilio + Slybroadcast)

**Sprint 10:** Voice AI agent prototype — Twilio + OpenAI Realtime, single facility call, structured inquiry script

**Sprint 11:** Voice agent → PlacementOps integration — function calling for bed queries, outcome logging, transcript storage

**Sprint 12:** Batch outreach — call multiple facilities from match results, aggregate responses

**Sprint 13:** Patient-side communication — discharge updates via SMS, TCM scheduling reminders

**Sprint 14:** Voice observability — Langfuse/Opik tracing, call quality monitoring, prompt optimization

### Future Phases
- Facility preference hierarchy by group/market
- Better insurance matrices
- Bed availability fields + dynamic ranking
- Historical acceptance modeling
- AI-generated clinical summaries from notes
- Hospital API/FHIR integration
- Referral packet automation

---

## Part 12: MVP Success Criteria

A successful Phase 1 should allow the team to:
- Maintain the daily hospital patient list directly in the web app
- Use spreadsheet import only as fallback
- Maintain one live case record per patient
- Capture clinician disposition recommendations consistently
- Generate a ranked list of realistic facility options
- Draft and approve communications from within the system
- Track accept/decline outcomes and reasons
- Replace major parts of the spreadsheet-plus-email workflow

A successful Phase 2 should additionally:
- Automate structured facility inquiry calls via voice AI
- Reduce average outreach-to-response time from hours to minutes
- Log call transcripts and outcomes automatically
- Support batch facility outreach from match results

---

## Part 13: Compliance & Safety

### Key Principles
- PHI stays inside the secure application
- Staff approval required before sending outbound communications containing PHI
- All outbound actions logged
- Role-based access control with least privilege
- Encrypted storage and transport
- Voice AI calls use de-identified or minimum-necessary clinical information
- Full audit trail for all case actions

### Voice-Specific Compliance (Phase 2)
- Twilio ConversationRelay is HIPAA eligible when configured with BAA
- Voice call recordings stored in HIPAA-compliant storage
- Transcripts treated as PHI
- AI system prompts reviewed for minimum-necessary PHI disclosure
