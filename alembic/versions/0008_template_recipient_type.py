"""Add recipient_type to outreach_templates

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "outreach_templates",
        sa.Column(
            "recipient_type",
            sa.String(32),
            nullable=False,
            server_default="facility",
        ),
    )


def downgrade() -> None:
    op.drop_column("outreach_templates", "recipient_type")
