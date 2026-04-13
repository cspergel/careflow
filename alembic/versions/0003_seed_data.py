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
    import importlib.util
    import os
    # Load alembic/seed.py directly to avoid conflict with the installed `alembic` package name
    seed_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "seed.py")
    spec = importlib.util.spec_from_file_location("alembic_seed", seed_path)
    seed_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed_module)
    seed_module.seed_all(op)


def downgrade() -> None:
    # Remove seeded data by known IDs — safe to use fixed IDs for reference data
    op.execute("DELETE FROM hospital_reference WHERE hospital_name = 'General Hospital (Demo)';")
    op.execute("DELETE FROM payer_reference WHERE payer_name IN ('Medicare', 'Medicaid', 'Medicare Advantage', 'Commercial', 'Self-Pay');")
    op.execute("DELETE FROM decline_reason_reference WHERE code IN ('no_bed', 'clinical_complexity', 'insurance', 'geography', 'family_declined', 'other');")
    op.execute("DELETE FROM user_roles WHERE role_key IN ('admin', 'intake_staff', 'clinical_reviewer', 'placement_coordinator', 'manager', 'read_only');")
