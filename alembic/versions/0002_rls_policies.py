# @forgeplan-node: core-infrastructure
"""
Alembic migration 0002 — RLS policies + AuditEvent immutability trigger.

Enables Row Level Security on all PHI tables using auth.jwt() -> 'app_metadata'.
Creates the Postgres trigger that blocks UPDATE/DELETE on audit_events (AC5, AC7).
"""
# @forgeplan-spec: AC5
# @forgeplan-spec: AC7

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

# PHI tables that need RLS — these contain patient or org-sensitive data.
# placement_outcomes is excluded here because it has no organization_id column;
# it is handled separately below via a subquery join through patient_cases.
_PHI_TABLES = [
    "patient_cases",
    "clinical_assessments",
    "facility_matches",
    "outreach_actions",
    "import_jobs",
    "case_status_history",
    "audit_events",
]


def upgrade() -> None:
    # ── AuditEvent immutability trigger ──────────────────────────────────────
    # @forgeplan-spec: AC7
    op.execute("""
        CREATE OR REPLACE FUNCTION audit_events_immutable()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events rows are immutable — attempted % on %',
                TG_OP, TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER audit_events_immutable_trigger
            BEFORE UPDATE OR DELETE ON audit_events
            FOR EACH ROW EXECUTE FUNCTION audit_events_immutable();
    """)

    # ── Enable RLS on all PHI tables ─────────────────────────────────────────
    # @forgeplan-spec: AC5
    for table in _PHI_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")

        # SELECT policy — uses app_metadata NOT user_metadata (AC12)
        op.execute(f"""
            CREATE POLICY {table}_org_select ON {table}
                FOR SELECT
                USING (
                    organization_id = (
                        auth.jwt() -> 'app_metadata' ->> 'organization_id'
                    )::text
                );
        """)

        # INSERT policy — restrict inserts to same org
        op.execute(f"""
            CREATE POLICY {table}_org_insert ON {table}
                FOR INSERT
                WITH CHECK (
                    organization_id = (
                        auth.jwt() -> 'app_metadata' ->> 'organization_id'
                    )::text
                );
        """)

        # UPDATE policy (except audit_events — the trigger prevents it anyway)
        if table != "audit_events" and table != "placement_outcomes":
            op.execute(f"""
                CREATE POLICY {table}_org_update ON {table}
                    FOR UPDATE
                    USING (
                        organization_id = (
                            auth.jwt() -> 'app_metadata' ->> 'organization_id'
                        )::text
                    )
                    WITH CHECK (
                        organization_id = (
                            auth.jwt() -> 'app_metadata' ->> 'organization_id'
                        )::text
                    );
            """)

    # ── RLS for placement_outcomes (no organization_id column — join via patient_cases) ──
    # @forgeplan-spec: AC5
    # placement_outcomes references patient_cases via patient_case_id; org scoping
    # is derived through that FK rather than a direct organization_id column.
    op.execute("ALTER TABLE placement_outcomes ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE placement_outcomes FORCE ROW LEVEL SECURITY;")

    op.execute("""
        CREATE POLICY placement_outcomes_org_select ON placement_outcomes
            FOR SELECT
            USING (
                patient_case_id IN (
                    SELECT id FROM patient_cases
                    WHERE organization_id = (auth.jwt() -> 'app_metadata' ->> 'organization_id')::text
                )
            );
    """)

    op.execute("""
        CREATE POLICY placement_outcomes_org_insert ON placement_outcomes
            FOR INSERT
            WITH CHECK (
                patient_case_id IN (
                    SELECT id FROM patient_cases
                    WHERE organization_id = (auth.jwt() -> 'app_metadata' ->> 'organization_id')::text
                )
            );
    """)

    # ── Bypass RLS for service role ───────────────────────────────────────────
    # Supabase service role bypasses RLS by default; no additional config needed.
    # Application role (anon / authenticated) subject to RLS policies above.


def downgrade() -> None:
    # Drop join-based placement_outcomes policies first (not in _PHI_TABLES loop)
    op.execute("DROP POLICY IF EXISTS placement_outcomes_org_insert ON placement_outcomes;")
    op.execute("DROP POLICY IF EXISTS placement_outcomes_org_select ON placement_outcomes;")
    op.execute("ALTER TABLE placement_outcomes DISABLE ROW LEVEL SECURITY;")

    for table in _PHI_TABLES:
        if table != "audit_events":
            op.execute(f"DROP POLICY IF EXISTS {table}_org_update ON {table};")
        op.execute(f"DROP POLICY IF EXISTS {table}_org_insert ON {table};")
        op.execute(f"DROP POLICY IF EXISTS {table}_org_select ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.execute("DROP TRIGGER IF EXISTS audit_events_immutable_trigger ON audit_events;")
    op.execute("DROP FUNCTION IF EXISTS audit_events_immutable();")
