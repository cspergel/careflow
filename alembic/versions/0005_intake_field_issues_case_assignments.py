# @forgeplan-node: core-infrastructure
"""
Alembic migration 0005 — Create intake_field_issues and case_assignments tables.

intake_field_issues: per-field validation failures for PatientCase records during intake.
case_assignments: assignment event log for coordinators and clinical reviewers.
"""
# @forgeplan-spec: AC1

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "intake_field_issues",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("patient_case_id", sa.String(36), sa.ForeignKey("patient_cases.id"), nullable=False, index=True),
        sa.Column("field_name", sa.String, nullable=False),
        sa.Column("issue_description", sa.String, nullable=False),
        sa.Column("resolved_flag", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "case_assignments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("patient_case_id", sa.String(36), sa.ForeignKey("patient_cases.id"), nullable=False, index=True),
        sa.Column("assigned_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assigned_role", sa.String, nullable=False),
        sa.Column("assigned_by_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Composite index for duplicate detection query performance (AC14)
    op.create_index(
        "ix_patient_cases_dup_detect",
        "patient_cases",
        ["organization_id", "patient_name", "dob", "hospital_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_patient_cases_dup_detect", "patient_cases")
    op.drop_table("case_assignments")
    op.drop_table("intake_field_issues")
