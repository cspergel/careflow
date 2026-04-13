# Patient SMS Placement Options — Design

**Date:** 2026-04-13
**Status:** Approved, ready to build
**HIPAA note:** Internal testing only before production use. No real PHI in test data.

---

## What It Does

When a case reaches `facility_options_generated`, the coordinator can optionally
send the patient (or family) an AI-powered SMS conversation presenting their
placement options. The patient picks a preference; the choice is logged on the
case and the coordinator is notified. No case status is auto-advanced — the
coordinator retains full control.

---

## Data Model

### `patient_cases` — add one field
```
patient_phone  VARCHAR(20)  nullable
```
Entered by coordinator during intake or via quick-edit. Starting point — can
migrate to a `patient_contacts` table later if multiple contacts are needed.

### New table: `sms_conversations`
```
id                    UUID PK
patient_case_id       UUID FK → patient_cases
phone_number          VARCHAR(20)
state                 VARCHAR  -- consent_pending | active | completed | opted_out
conversation_json     JSONB    -- full message history for Claude context
chosen_facility_id    UUID FK → facilities  nullable
initiated_by_user_id  UUID FK → users
created_at            TIMESTAMP
updated_at            TIMESTAMP
```

One active conversation per case at a time. Re-initiating supersedes the previous
conversation.

---

## Conversation Flow

```
Coordinator clicks "Send Options to Patient"
  ↓
System sends opt-in SMS:
  "Hi [Patient Name], this is [Group Name] at [Hospital Name]. Should you need
   rehabilitation or care on discharge, we have some recommended options available
   to you. Reply YES to see them, or STOP at any time."
  ↓ state: consent_pending
Patient replies YES
  ↓ state: active
System sends options (from facility_matches on the case):
  "Here are some options we've arranged for you:
   1. Sunrise SNF – skilled nursing, 2.1 mi
   2. Valley IRF – inpatient rehab, 4.0 mi
   3. Riverside LTACH – long-term care, 3.3 mi
   Reply 1, 2, or 3, or ask us anything."
  ↓
Patient replies 1/2/3 → choice logged, coordinator notified
Patient asks a question → Claude handles with guardrails (no medical advice)
Patient replies unclear → Claude interprets + re-prompts politely
Patient replies STOP → state: opted_out, coordinator notified
  ↓ state: completed
Coordinator receives SMS + case timeline entry:
  "Patient [Name] selected [Facility X] for case [ID]."
```

---

## Backend Components

### New API endpoints
| Method | Path | Who |
|--------|------|-----|
| POST | `/api/v1/cases/{case_id}/sms-conversation` | Coordinator initiates |
| GET  | `/api/v1/cases/{case_id}/sms-conversation` | Get status + history |
| POST | `/api/v1/webhooks/twilio/sms` | Twilio inbound (public, sig-validated) |

### New files
- `placementops/core/models/sms_conversation.py` — ORM model
- `placementops/modules/sms/service.py` — conversation state machine
- `placementops/modules/sms/router.py` — API endpoints + Twilio webhook
- `alembic/versions/0007_sms_conversations.py` — migration

### Claude integration
System prompt includes:
- Group name, hospital name
- Patient first name
- Facility options with type + distance
- Hard rule: never give medical advice or make clinical recommendations
- Conversation history injected for context continuity

Handles: questions, unclear responses, hesitation, re-prompts. Structured
number picks (1/2/3) and YES/STOP are handled in code before Claude is called.

---

## Frontend Changes

### Case detail — Overview tab
- When status is `facility_options_generated` and `patient_phone` is set:
  → Show banner: "Patient options ready to send" + **Send SMS to Patient** button
- When `patient_phone` is missing:
  → Banner: "Add patient phone to send options" → inline edit
- After sending: live conversation status card showing state + last reply

### Intake page + quick-edit sheet
- Add `patient_phone` field to "New Case" form
- Add to case quick-edit sheet

---

## Notifications

When patient makes a choice:
1. Coordinator receives SMS: *"[Patient Name] selected [Facility X]. Case [ID] ready for next steps."*
2. `CaseActivityEvent` logged → appears in case timeline

When patient opts out:
1. Coordinator receives SMS: *"[Patient Name] opted out of SMS placement options for case [ID]."*
2. Activity event logged

---

## Testing Plan (Internal)

- Use personal/team phone numbers — no real patient numbers
- `OUTREACH_DELIVERY_MODE=log` for email/facility SMS
- Twilio SMS uses real numbers for internal test (Twilio test credentials available)
- Verify: opt-in flow, option selection, Claude fallback for questions, opt-out, coordinator notification
