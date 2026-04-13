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
# Only tables with a *direct* organization_id column are included here.
# Tables that derive org membership via patient_case_id FK
# (facility_matches, clinical_assessments, outreach_actions, placement_outcomes)
# are handled separately below via a subquery join through patient_cases.
# F32 fix: facility_matches has no organization_id column — only patient_case_id.
_PHI_TABLES = [
    "patient_cases",
    "import_jobs",
    "case_status_history",
    "audit_events",
]

# Tables whose org scope must be derived by joining through patient_cases
# (no direct organization_id column — only patient_case_id FK).
_PHI_TABLES_VIA_CASE = [
    "clinical_assessments",   # has patient_case_id, no organization_id
    "facility_matches",       # has patient_case_id, no organization_id — F32
    "outreach_actions",       # has patient_case_id, no organization_id
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

    # ── Enable RLS on tables with a direct organization_id column ────────────
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
        if table != "audit_events":
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

    # ── RLS for tables without a direct organization_id column ───────────────
    # @forgeplan-spec: AC5
    # These tables reference patient_cases via patient_case_id FK.
    # Org scoping is derived through that join rather than a direct column.
    # Applies to: clinical_assessments, facility_matches, outreach_actions,
    #             placement_outcomes  (F32 fix: facility_matches was incorrectly
    #             included in the direct-column loop above).
    _via_case_tables = list(_PHI_TABLES_VIA_CASE) + ["placement_outcomes"]
    for table in _via_case_tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;")

        op.execute(f"""
            CREATE POLICY {table}_org_select ON {table}
                FOR SELECT
                USING (
                    patient_case_id IN (
                        SELECT id FROM patient_cases
                        WHERE organization_id = (auth.jwt() -> 'app_metadata' ->> 'organization_id')::text
                    )
                );
        """)

        op.execute(f"""
            CREATE POLICY {table}_org_insert ON {table}
                FOR INSERT
                WITH CHECK (
                    patient_case_id IN (
                        SELECT id FROM patient_cases
                        WHERE organization_id = (auth.jwt() -> 'app_metadata' ->> 'organization_id')::text
                    )
                );
        """)

        # placement_outcomes is intentionally insert-only (no UPDATE policy).
        if table != "placement_outcomes":
            op.execute(f"""
                CREATE POLICY {table}_org_update ON {table}
                    FOR UPDATE
                    USING (
                        patient_case_id IN (
                            SELECT id FROM patient_cases
                            WHERE organization_id = (auth.jwt() -> 'app_metadata' ->> 'organization_id')::text
                        )
                    )
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
    # Drop join-based policies (via patient_case_id) — placement_outcomes + _PHI_TABLES_VIA_CASE
    _via_case_tables = list(_PHI_TABLES_VIA_CASE) + ["placement_outcomes"]
    for table in _via_case_tables:
        if table != "placement_outcomes":
            op.execute(f"DROP POLICY IF EXISTS {table}_org_update ON {table};")
        op.execute(f"DROP POLICY IF EXISTS {table}_org_insert ON {table};")
        op.execute(f"DROP POLICY IF EXISTS {table}_org_select ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    # Drop direct organization_id column policies
    for table in _PHI_TABLES:
        if table != "audit_events":
            op.execute(f"DROP POLICY IF EXISTS {table}_org_update ON {table};")
        op.execute(f"DROP POLICY IF EXISTS {table}_org_insert ON {table};")
        op.execute(f"DROP POLICY IF EXISTS {table}_org_select ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    op.execute("DROP TRIGGER IF EXISTS audit_events_immutable_trigger ON audit_events;")
    op.execute("DROP FUNCTION IF EXISTS audit_events_immutable();")
