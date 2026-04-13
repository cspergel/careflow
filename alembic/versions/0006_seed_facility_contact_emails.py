# @forgeplan-node: core-infrastructure
"""
Alembic migration 0006 — Backfill demo facility contact emails.

Adds demo email addresses to the seeded facility contacts so the
outreach delivery layer has a recipient address for smoke testing.
"""

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from alembic import op
    op.execute("""
        UPDATE facility_contacts SET email = 'admissions@sunrisesnf1.demo'
        WHERE contact_name = 'Janet Smith' AND email IS NULL;
    """)
    op.execute("""
        UPDATE facility_contacts SET email = 'admissions@sunrisesnf2.demo'
        WHERE contact_name = 'Bob Johnson' AND email IS NULL;
    """)
    op.execute("""
        UPDATE facility_contacts SET email = 'admissions@sunrisesnf3.demo'
        WHERE contact_name = 'Carol Williams' AND email IS NULL;
    """)


def downgrade() -> None:
    from alembic import op
    op.execute("""
        UPDATE facility_contacts SET email = NULL
        WHERE contact_name IN ('Janet Smith', 'Bob Johnson', 'Carol Williams');
    """)
