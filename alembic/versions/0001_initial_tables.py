# @forgeplan-node: core-infrastructure
"""
Alembic migration 0001 — Create all 20+ initial tables.

Creates: organizations, user_roles, hospital_reference, payer_reference,
         decline_reason_reference, users, patient_cases, facilities,
         facility_capabilities, facility_insurance_rules, facility_contacts,
         outreach_templates, outreach_actions, clinical_assessments,
         facility_matches, import_jobs, placement_outcomes,
         audit_events, case_status_history.
"""
# @forgeplan-spec: AC1

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Reference / lookup tables ─────────────────────────────────────────────
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "user_roles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("role_key", sa.String, unique=True, nullable=False),
        sa.Column("display_name", sa.String, nullable=False),
        sa.Column("description", sa.String, nullable=True),
    )

    op.create_table(
        "payer_reference",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("payer_name", sa.String, nullable=False),
        sa.Column("payer_type", sa.String, nullable=True),
    )

    op.create_table(
        "decline_reason_reference",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String, unique=True, nullable=False),
        sa.Column("label", sa.String, nullable=False),
        sa.Column("display_order", sa.Integer, nullable=False, server_default="0"),
    )

    op.create_table(
        "hospital_reference",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("hospital_name", sa.String, nullable=False),
        sa.Column("address", sa.String, nullable=True),
    )
    op.create_index("ix_hospital_reference_org", "hospital_reference", ["organization_id"])

    # ── Users ─────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("email", sa.String, unique=True, nullable=False),
        sa.Column("full_name", sa.String, nullable=False),
        sa.Column("role_key", sa.String, nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="active"),
        sa.Column("timezone", sa.String, nullable=True),
        sa.Column("default_hospital_id", sa.String(36), sa.ForeignKey("hospital_reference.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_users_organization_id", "users", ["organization_id"])

    # ── Patient cases ─────────────────────────────────────────────────────────
    op.create_table(
        "patient_cases",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("hospital_id", sa.String(36), sa.ForeignKey("hospital_reference.id"), nullable=True),
        sa.Column("patient_name", sa.String, nullable=False),
        sa.Column("dob", sa.Date, nullable=True),
        sa.Column("mrn", sa.String, nullable=True),
        sa.Column("hospital_unit", sa.String, nullable=True),
        sa.Column("room_number", sa.String, nullable=True),
        sa.Column("admission_date", sa.Date, nullable=True),
        sa.Column("primary_diagnosis_text", sa.String, nullable=True),
        sa.Column("insurance_primary", sa.String, nullable=True),
        sa.Column("insurance_secondary", sa.String, nullable=True),
        sa.Column("patient_zip", sa.String, nullable=True),
        sa.Column("preferred_geography_text", sa.String, nullable=True),
        sa.Column("discharge_target_date", sa.Date, nullable=True),
        sa.Column("current_status", sa.String, nullable=False, server_default="new"),
        sa.Column("priority_level", sa.String, nullable=True),
        sa.Column("intake_complete", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("active_case_flag", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("assigned_coordinator_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_patient_cases_org_status", "patient_cases", ["organization_id", "current_status"])
    op.create_index("ix_patient_cases_active", "patient_cases", ["organization_id", "active_case_flag"])

    # ── Facilities ────────────────────────────────────────────────────────────
    op.create_table(
        "facilities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("facility_name", sa.String, nullable=False),
        sa.Column("facility_type", sa.String, nullable=False),
        sa.Column("address_line_1", sa.String, nullable=True),
        sa.Column("city", sa.String, nullable=True),
        sa.Column("county", sa.String, nullable=True),
        sa.Column("state", sa.String, nullable=True),
        sa.Column("zip", sa.String, nullable=True),
        sa.Column("latitude", sa.Numeric(10, 6), nullable=True),
        sa.Column("longitude", sa.Numeric(10, 6), nullable=True),
        sa.Column("active_status", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("notes", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_facilities_organization_id", "facilities", ["organization_id"])

    op.create_table(
        "facility_capabilities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("facilities.id"), unique=True, nullable=False),
        sa.Column("accepts_snf", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("accepts_irf", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("accepts_ltach", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("accepts_trach", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("accepts_vent", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("accepts_hd", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("in_house_hemodialysis", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("accepts_peritoneal_dialysis", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("accepts_wound_vac", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("accepts_iv_antibiotics", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("accepts_tpn", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("accepts_bariatric", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("accepts_behavioral_complexity", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("accepts_memory_care", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("accepts_isolation_cases", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("accepts_oxygen_therapy", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("weekend_admissions", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("after_hours_admissions", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "facility_insurance_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("payer_id", sa.String(36), sa.ForeignKey("payer_reference.id"), nullable=False),
        sa.Column("payer_name", sa.String, nullable=False),
        sa.Column("accepted_status", sa.String, nullable=False),
        sa.Column("notes", sa.String, nullable=True),
        sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_facility_insurance_rules_facility", "facility_insurance_rules", ["facility_id"])

    op.create_table(
        "facility_contacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("contact_name", sa.String, nullable=False),
        sa.Column("title", sa.String, nullable=True),
        sa.Column("phone", sa.String, nullable=True),
        sa.Column("phone_extension", sa.String, nullable=True),
        sa.Column("best_call_window", sa.String, nullable=True),
        sa.Column("phone_contact_name", sa.String, nullable=True),
        sa.Column("email", sa.String, nullable=True),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_facility_contacts_facility", "facility_contacts", ["facility_id"])

    # ── Outreach ──────────────────────────────────────────────────────────────
    op.create_table(
        "outreach_templates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("template_name", sa.String, nullable=False),
        sa.Column("template_type", sa.String, nullable=False),
        sa.Column("subject_template", sa.String, nullable=True),
        sa.Column("body_template", sa.String, nullable=False),
        sa.Column("allowed_variables", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_outreach_templates_org", "outreach_templates", ["organization_id"])

    op.create_table(
        "outreach_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("patient_case_id", sa.String(36), sa.ForeignKey("patient_cases.id"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("facilities.id"), nullable=True),
        sa.Column("template_id", sa.String(36), sa.ForeignKey("outreach_templates.id"), nullable=True),
        sa.Column("action_type", sa.String, nullable=False),
        sa.Column("channel", sa.String, nullable=False),
        sa.Column("draft_subject", sa.String, nullable=True),
        sa.Column("draft_body", sa.String, nullable=False),
        sa.Column("approval_status", sa.String, nullable=False, server_default="draft"),
        sa.Column("approved_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivery_status", sa.String, nullable=True),
        sa.Column("call_transcript_url", sa.String, nullable=True),
        sa.Column("call_duration_seconds", sa.Integer, nullable=True),
        sa.Column("call_outcome_summary", sa.String, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_outreach_actions_case", "outreach_actions", ["patient_case_id"])

    # ── Clinical assessments ──────────────────────────────────────────────────
    op.create_table(
        "clinical_assessments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("patient_case_id", sa.String(36), sa.ForeignKey("patient_cases.id"), nullable=False),
        sa.Column("reviewer_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("recommended_level_of_care", sa.String, nullable=False),
        sa.Column("confidence_level", sa.String, nullable=True),
        sa.Column("clinical_summary", sa.String, nullable=True),
        sa.Column("rehab_tolerance", sa.String, nullable=True),
        sa.Column("mobility_status", sa.String, nullable=True),
        sa.Column("accepts_oxygen_therapy", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("accepts_trach", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("accepts_vent", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("accepts_hd", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("in_house_hemodialysis", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("accepts_peritoneal_dialysis", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("accepts_wound_vac", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("accepts_iv_antibiotics", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("accepts_tpn", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("accepts_isolation_cases", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("psych_behavior_flags", sa.String, nullable=True),
        sa.Column("accepts_behavioral_complexity", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("accepts_bariatric", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("accepts_memory_care", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("special_equipment_needs", sa.String, nullable=True),
        sa.Column("barriers_to_placement", sa.String, nullable=True),
        sa.Column("payer_notes", sa.String, nullable=True),
        sa.Column("family_preference_notes", sa.String, nullable=True),
        sa.Column("review_status", sa.String, nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_clinical_assessments_case", "clinical_assessments", ["patient_case_id"])

    # ── Facility matches ──────────────────────────────────────────────────────
    op.create_table(
        "facility_matches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("patient_case_id", sa.String(36), sa.ForeignKey("patient_cases.id"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("facilities.id"), nullable=False),
        sa.Column("assessment_id", sa.String(36), sa.ForeignKey("clinical_assessments.id"), nullable=True),
        sa.Column("overall_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("payer_fit_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("clinical_fit_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("geography_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("preference_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("level_of_care_fit_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("rank_order", sa.Integer, nullable=False),
        sa.Column("is_recommended", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("selected_for_outreach", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("blockers_json", JSONB, nullable=True),
        sa.Column("explanation_text", sa.String, nullable=True),
        sa.Column("generated_by", sa.String, nullable=False, server_default="rules_engine"),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_facility_matches_case", "facility_matches", ["patient_case_id"])

    # ── Import jobs ───────────────────────────────────────────────────────────
    op.create_table(
        "import_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("created_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("file_name", sa.String, nullable=False),
        sa.Column("file_size_bytes", sa.Integer, nullable=False),
        sa.Column("status", sa.String, nullable=False, server_default="uploaded"),
        sa.Column("column_mapping_json", JSONB, nullable=True),
        sa.Column("total_rows", sa.Integer, nullable=True),
        sa.Column("created_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("updated_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error_detail_json", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_import_jobs_org", "import_jobs", ["organization_id"])

    # ── Placement outcomes ────────────────────────────────────────────────────
    op.create_table(
        "placement_outcomes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("patient_case_id", sa.String(36), sa.ForeignKey("patient_cases.id"), nullable=False),
        sa.Column("facility_id", sa.String(36), sa.ForeignKey("facilities.id"), nullable=True),
        sa.Column("outcome_type", sa.String, nullable=False),
        sa.Column("decline_reason_code", sa.String, nullable=True),
        sa.Column("decline_reason_text", sa.String, nullable=True),
        sa.Column("recorded_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_placement_outcomes_case", "placement_outcomes", ["patient_case_id"])

    # ── Audit events (INSERT-ONLY) ────────────────────────────────────────────
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("entity_type", sa.String, nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String, nullable=False),
        sa.Column("old_value_json", JSONB, nullable=True),
        sa.Column("new_value_json", JSONB, nullable=True),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_events_org", "audit_events", ["organization_id"])
    op.create_index("ix_audit_events_entity", "audit_events", ["entity_id"])

    # ── Case status history ───────────────────────────────────────────────────
    op.create_table(
        "case_status_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("patient_case_id", sa.String(36), sa.ForeignKey("patient_cases.id"), nullable=False),
        sa.Column("from_status", sa.String, nullable=True),
        sa.Column("to_status", sa.String, nullable=False),
        sa.Column("actor_user_id", sa.String(36), nullable=False),
        sa.Column("transition_reason", sa.String, nullable=True),
        sa.Column("entered_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_case_status_history_org", "case_status_history", ["organization_id"])
    op.create_index("ix_case_status_history_case", "case_status_history", ["patient_case_id"])


def downgrade() -> None:
    op.drop_table("case_status_history")
    op.drop_table("audit_events")
    op.drop_table("placement_outcomes")
    op.drop_table("import_jobs")
    op.drop_table("facility_matches")
    op.drop_table("clinical_assessments")
    op.drop_table("outreach_actions")
    op.drop_table("outreach_templates")
    op.drop_table("facility_contacts")
    op.drop_table("facility_insurance_rules")
    op.drop_table("facility_capabilities")
    op.drop_table("facilities")
    op.drop_table("patient_cases")
    op.drop_table("users")
    op.drop_table("hospital_reference")
    op.drop_table("decline_reason_reference")
    op.drop_table("payer_reference")
    op.drop_table("user_roles")
    op.drop_table("organizations")
