# @forgeplan-node: core-infrastructure
"""
Alembic migration 0004 — no-op (changes folded into 0001).

The clinical_assessments column renames and accepts_peritoneal_dialysis addition
that were originally planned here have been folded into the initial migration
(0001_initial_tables.py). This migration is retained only to preserve the
revision chain for environments that may have run 0001-0003.
"""
# @forgeplan-spec: AC1

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
