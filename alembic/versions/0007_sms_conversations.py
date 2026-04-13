# @forgeplan-node: core-infrastructure
"""
Alembic migration 0007 — Patient SMS conversations.

Adds:
  - patient_phone column to patient_cases
  - sms_conversations table for tracking AI-driven patient SMS flows
"""

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from alembic import op
    import sqlalchemy as sa

    # Add patient_phone to patient_cases
    op.add_column(
        "patient_cases",
        sa.Column("patient_phone", sa.String(20), nullable=True),
    )

    # Create sms_conversations table
    op.create_table(
        "sms_conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "patient_case_id",
            sa.String(36),
            sa.ForeignKey("patient_cases.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("phone_number", sa.String(20), nullable=False),
        # state: consent_pending | active | completed | opted_out
        sa.Column("state", sa.String(20), nullable=False, default="consent_pending"),
        # Full message history as [{role, content, ts}] for Claude context
        sa.Column(
            "conversation_json",
            sa.JSON,
            nullable=False,
            server_default="[]",
        ),
        sa.Column(
            "chosen_facility_id",
            sa.String(36),
            sa.ForeignKey("facilities.id"),
            nullable=True,
        ),
        sa.Column(
            "initiated_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime,
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    from alembic import op
    op.drop_table("sms_conversations")
    op.drop_column("patient_cases", "patient_phone")
