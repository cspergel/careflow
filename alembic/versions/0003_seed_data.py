# @forgeplan-node: core-infrastructure
"""
Alembic migration 0003 — Seed reference data.

Seeds: 6 user roles, decline reason codes, payer reference, hospital reference.
"""
# @forgeplan-spec: AC10

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    import sys
    import os
    # Add project root to path so alembic/seed.py can be imported
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from alembic.seed import seed_all
    seed_all(op)


def downgrade() -> None:
    # Remove seeded data by known IDs — safe to use fixed IDs for reference data
    op.execute("DELETE FROM hospital_reference WHERE hospital_name = 'General Hospital (Demo)';")
    op.execute("DELETE FROM payer_reference WHERE payer_name IN ('Medicare', 'Medicaid', 'Medicare Advantage', 'Commercial', 'Self-Pay');")
    op.execute("DELETE FROM decline_reason_reference WHERE code IN ('no_bed', 'clinical_complexity', 'insurance', 'geography', 'family_declined', 'other');")
    op.execute("DELETE FROM user_roles WHERE role_key IN ('admin', 'intake_staff', 'clinical_reviewer', 'placement_coordinator', 'manager', 'read_only');")
