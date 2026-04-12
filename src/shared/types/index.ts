// @forgeplan-node: shared
/**
 * Shared type definitions generated from manifest.yaml shared_models.
 * This is the canonical source of truth for shared models across the codebase.
 * Frontend imports via: import { ... } from 'src/shared/types'
 * Note: In the Next.js project (frontend/), use the path alias configured in tsconfig.json.
 */

// ─── PatientCase ────────────────────────────────────────────────────────────

export type CaseStatus =
  | "new"
  | "intake_in_progress"
  | "intake_complete"
  | "needs_clinical_review"
  | "under_clinical_review"
  | "ready_for_matching"
  | "facility_options_generated"
  | "outreach_pending_approval"
  | "outreach_in_progress"
  | "pending_facility_response"
  | "accepted"
  | "declined_retry_needed"
  | "placed"
  | "closed"

export type PriorityLevel = "routine" | "urgent" | "emergent"

export interface PatientCase {
  id: string
  organization_id: string
  /** References hospital_reference.id */
  hospital_id: string
  patient_name: string
  dob?: string | null
  mrn?: string | null
  hospital_unit?: string | null
  room_number?: string | null
  admission_date?: string | null
  primary_diagnosis_text?: string | null
  insurance_primary?: string | null
  insurance_secondary?: string | null
  patient_zip?: string | null
  preferred_geography_text?: string | null
  discharge_target_date?: string | null
  current_status: CaseStatus
  priority_level?: PriorityLevel | null
  intake_complete: boolean
  active_case_flag: boolean
  /** References users.id */
  assigned_coordinator_user_id?: string | null
  /** References users.id */
  created_by_user_id?: string | null
  /** References users.id */
  updated_by_user_id?: string | null
  created_at: string
  updated_at: string
}

// ─── Facility ────────────────────────────────────────────────────────────────

export type FacilityType = "snf" | "irf" | "ltach"

export interface Facility {
  id: string
  organization_id: string
  facility_name: string
  facility_type: FacilityType
  address_line_1?: string | null
  city?: string | null
  county?: string | null
  state?: string | null
  zip?: string | null
  latitude?: number | null
  longitude?: number | null
  active_status: boolean
  notes?: string | null
  created_at: string
  updated_at: string
}

// ─── FacilityCapabilities ────────────────────────────────────────────────────

export interface FacilityCapabilities {
  id: string
  /** References facilities.id */
  facility_id: string
  accepts_snf: boolean
  accepts_irf: boolean
  accepts_ltach: boolean
  accepts_trach: boolean
  accepts_vent: boolean
  accepts_hd: boolean
  in_house_hemodialysis: boolean
  accepts_peritoneal_dialysis: boolean
  accepts_wound_vac: boolean
  accepts_iv_antibiotics: boolean
  accepts_tpn: boolean
  accepts_bariatric: boolean
  accepts_behavioral_complexity: boolean
  accepts_memory_care: boolean
  accepts_isolation_cases: boolean
  accepts_oxygen_therapy: boolean
  weekend_admissions: boolean
  after_hours_admissions: boolean
  last_verified_at?: string | null
  updated_at: string
}

// ─── FacilityInsuranceRule ───────────────────────────────────────────────────

export type InsuranceAcceptedStatus = "accepted" | "conditional" | "not_accepted"

export interface FacilityInsuranceRule {
  id: string
  /** References facilities.id */
  facility_id: string
  /** References payer_reference.id */
  payer_id: string
  payer_name: string
  accepted_status: InsuranceAcceptedStatus
  notes?: string | null
  last_verified_at?: string | null
  created_at: string
  updated_at: string
}

// ─── FacilityContact ─────────────────────────────────────────────────────────

export interface FacilityContact {
  id: string
  /** References facilities.id */
  facility_id: string
  contact_name: string
  title?: string | null
  phone?: string | null
  phone_extension?: string | null
  best_call_window?: string | null
  phone_contact_name?: string | null
  email?: string | null
  is_primary: boolean
  created_at: string
  updated_at: string
}

// ─── User ────────────────────────────────────────────────────────────────────

export type UserRole =
  | "admin"
  | "intake_staff"
  | "clinical_reviewer"
  | "placement_coordinator"
  | "manager"
  | "read_only"

export type UserStatus = "active" | "inactive"

export interface User {
  id: string
  organization_id: string
  email: string
  full_name: string
  role_key: UserRole
  status: UserStatus
  timezone?: string | null
  /** References hospital_reference.id */
  default_hospital_id?: string | null
  created_at: string
  updated_at: string
}

// ─── OutreachAction ──────────────────────────────────────────────────────────

export type OutreachActionType =
  | "facility_outreach"
  | "internal_alert"
  | "cm_update"
  | "follow_up_reminder"

export type OutreachChannel =
  | "email"
  | "phone_manual"
  | "task"
  | "sms"
  | "voicemail_drop"
  | "voice_ai"

export type OutreachApprovalStatus =
  | "draft"
  | "pending_approval"
  | "approved"
  | "sent"
  | "canceled"
  | "failed"

export interface OutreachAction {
  id: string
  /** References patient_cases.id */
  patient_case_id: string
  /** References facilities.id */
  facility_id?: string | null
  /** References outreach_templates.id */
  template_id?: string | null
  action_type: OutreachActionType
  channel: OutreachChannel
  draft_subject?: string | null
  draft_body: string
  approval_status: OutreachApprovalStatus
  /** References users.id */
  approved_by_user_id?: string | null
  approved_at?: string | null
  /** References users.id */
  sent_by_user_id?: string | null
  sent_at?: string | null
  delivery_status?: string | null
  call_transcript_url?: string | null
  call_duration_seconds?: number | null
  call_outcome_summary?: string | null
  created_at: string
  updated_at: string
}

// ─── OutreachTemplate ────────────────────────────────────────────────────────

export type OutreachTemplateType =
  | "email"
  | "phone_manual"
  | "task"
  | "voice_ai_script"

export interface OutreachTemplate {
  id: string
  organization_id: string
  template_name: string
  template_type: OutreachTemplateType
  subject_template?: string | null
  body_template: string
  allowed_variables?: string[] | null
  is_active: boolean
  /** References users.id */
  created_by_user_id: string
  created_at: string
  updated_at: string
}

// ─── ClinicalAssessment ──────────────────────────────────────────────────────

export type RecommendedLevelOfCare = "snf" | "irf" | "ltach"
export type ReviewStatus = "draft" | "finalized"

export interface ClinicalAssessment {
  id: string
  /** References patient_cases.id */
  patient_case_id: string
  /** References users.id */
  reviewer_user_id: string
  recommended_level_of_care: RecommendedLevelOfCare
  confidence_level?: string | null
  clinical_summary?: string | null
  rehab_tolerance?: string | null
  mobility_status?: string | null
  /** Clinical capability flags — names match backend ORM and FacilityCapabilities exactly */
  accepts_oxygen_therapy: boolean
  accepts_trach: boolean
  accepts_vent: boolean
  accepts_hd: boolean
  in_house_hemodialysis: boolean
  accepts_peritoneal_dialysis: boolean
  accepts_wound_vac: boolean
  accepts_iv_antibiotics: boolean
  accepts_tpn: boolean
  accepts_isolation_cases: boolean
  accepts_behavioral_complexity: boolean
  accepts_bariatric: boolean
  accepts_memory_care: boolean
  psych_behavior_flags?: string | null
  special_equipment_needs?: string | null
  barriers_to_placement?: string | null
  payer_notes?: string | null
  family_preference_notes?: string | null
  review_status: ReviewStatus
  created_at: string
  updated_at: string
}

// ─── FacilityMatch ───────────────────────────────────────────────────────────

export type MatchGeneratedBy = "rules_engine" | "voice_ai"

export interface FacilityMatch {
  id: string
  /** References patient_cases.id */
  patient_case_id: string
  /** References facilities.id */
  facility_id: string
  /** References clinical_assessments.id */
  assessment_id?: string | null
  overall_score: number
  payer_fit_score?: number | null
  clinical_fit_score?: number | null
  geography_score?: number | null
  preference_score?: number | null
  rank_order: number
  is_recommended: boolean
  selected_for_outreach: boolean
  level_of_care_fit_score?: number | null
  blockers_json?: Record<string, unknown>[] | null
  explanation_text?: string | null
  generated_by: MatchGeneratedBy
  generated_at: string
}

// ─── ImportJob ───────────────────────────────────────────────────────────────

export type ImportJobStatus =
  | "uploaded"
  | "mapping"
  | "validating"
  | "ready"
  | "committing"
  | "complete"
  | "failed"

export interface ImportJob {
  id: string
  organization_id: string
  /** References users.id */
  created_by_user_id: string
  file_name: string
  file_size_bytes: number
  status: ImportJobStatus
  column_mapping_json?: Record<string, unknown> | null
  total_rows?: number | null
  created_count: number
  updated_count: number
  failed_count: number
  error_detail_json?: Record<string, unknown>[] | null
  created_at: string
  updated_at: string
}

// ─── PlacementOutcome ────────────────────────────────────────────────────────

export type OutcomeType =
  | "pending_review"
  | "accepted"
  | "declined"
  | "placed"
  | "family_declined"
  | "withdrawn"

export interface PlacementOutcome {
  id: string
  /** References patient_cases.id */
  patient_case_id: string
  /** References facilities.id */
  facility_id?: string | null
  outcome_type: OutcomeType
  /** References decline_reason_reference.code */
  decline_reason_code?: string | null
  decline_reason_text?: string | null
  /** References users.id */
  recorded_by_user_id: string
  created_at: string
}

// ─── AuditEvent ──────────────────────────────────────────────────────────────

export interface AuditEvent {
  id: string
  organization_id: string
  entity_type: string
  entity_id: string
  event_type: string
  old_value_json?: Record<string, unknown> | null
  new_value_json?: Record<string, unknown> | null
  /** References users.id — null means system action */
  actor_user_id?: string | null
  created_at: string
}
