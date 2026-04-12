# @forgeplan-node: core-infrastructure
"""
Seed reference data for PlacementOps.

Idempotent: uses INSERT ... ON CONFLICT DO NOTHING where possible.
Run after `alembic upgrade head`:
    python -m alembic.seed
Or called from migration 0003.
"""
# @forgeplan-spec: AC10

from uuid import uuid4

# Seed data constants — fixed IDs for stability across environments
SEED_ORG_ID = "00000000-0000-0000-0000-000000000001"
SEED_HOSPITAL_ID = "00000000-0000-0000-0000-000000000010"


def seed_all(op) -> None:
    """
    Insert all reference seed data using the Alembic op object.
    Idempotent: safe to run multiple times.
    """
    _seed_user_roles(op)
    _seed_decline_reasons(op)
    _seed_payers(op)
    _seed_demo_org_and_hospital(op)


def _seed_user_roles(op) -> None:
    """Seed 6 required roles in user_roles table (AC10)."""
    roles = [
        {
            "id": "00000000-0000-0000-0001-000000000001",
            "role_key": "admin",
            "display_name": "Administrator",
            "description": "Full system access; user and org management",
        },
        {
            "id": "00000000-0000-0000-0001-000000000002",
            "role_key": "intake_staff",
            "display_name": "Intake Staff",
            "description": "Creates and manages intake workflow",
        },
        {
            "id": "00000000-0000-0000-0001-000000000003",
            "role_key": "clinical_reviewer",
            "display_name": "Clinical Reviewer",
            "description": "Performs clinical assessments and reviews",
        },
        {
            "id": "00000000-0000-0000-0001-000000000004",
            "role_key": "placement_coordinator",
            "display_name": "Placement Coordinator",
            "description": "Manages facility matching and outreach",
        },
        {
            "id": "00000000-0000-0000-0001-000000000005",
            "role_key": "manager",
            "display_name": "Manager",
            "description": "Can close cases; operational oversight",
        },
        {
            "id": "00000000-0000-0000-0001-000000000006",
            "role_key": "read_only",
            "display_name": "Read Only",
            "description": "View access only; cannot modify data",
        },
    ]

    for role in roles:
        op.execute(
            f"""
            INSERT INTO user_roles (id, role_key, display_name, description)
            VALUES ('{role["id"]}', '{role["role_key"]}', '{role["display_name"]}', '{role["description"]}')
            ON CONFLICT (role_key) DO NOTHING;
            """
        )


def _seed_decline_reasons(op) -> None:
    """Seed decline reason reference codes (AC10)."""
    reasons = [
        {"id": str(uuid4()), "code": "no_bed", "label": "No Available Bed", "display_order": 1},
        {"id": str(uuid4()), "code": "clinical_complexity", "label": "Clinical Complexity Too High", "display_order": 2},
        {"id": str(uuid4()), "code": "insurance", "label": "Insurance Not Accepted", "display_order": 3},
        {"id": str(uuid4()), "code": "geography", "label": "Geographic Distance", "display_order": 4},
        {"id": str(uuid4()), "code": "family_declined", "label": "Family Declined", "display_order": 5},
        {"id": str(uuid4()), "code": "other", "label": "Other", "display_order": 6},
    ]

    for reason in reasons:
        op.execute(
            f"""
            INSERT INTO decline_reason_reference (id, code, label, display_order)
            VALUES ('{reason["id"]}', '{reason["code"]}', '{reason["label"]}', {reason["display_order"]})
            ON CONFLICT (code) DO NOTHING;
            """
        )


def _seed_payers(op) -> None:
    """Seed payer reference data (AC10). Stable UUIDs ensure idempotency via ON CONFLICT (id)."""
    payers = [
        {"id": "00000000-0000-0000-0002-000000000001", "payer_name": "Medicare", "payer_type": "government"},
        {"id": "00000000-0000-0000-0002-000000000002", "payer_name": "Medicaid", "payer_type": "government"},
        {"id": "00000000-0000-0000-0002-000000000003", "payer_name": "Medicare Advantage", "payer_type": "managed_care"},
        {"id": "00000000-0000-0000-0002-000000000004", "payer_name": "Commercial", "payer_type": "commercial"},
        {"id": "00000000-0000-0000-0002-000000000005", "payer_name": "Self-Pay", "payer_type": "self_pay"},
    ]

    for payer in payers:
        op.execute(
            f"""
            INSERT INTO payer_reference (id, payer_name, payer_type)
            VALUES ('{payer["id"]}', '{payer["payer_name"]}', '{payer["payer_type"]}')
            ON CONFLICT (id) DO NOTHING;
            """
        )


def _seed_demo_org_and_hospital(op) -> None:
    """Seed a demo organization and hospital for development (AC10)."""
    op.execute(
        f"""
        INSERT INTO organizations (id, name)
        VALUES ('{SEED_ORG_ID}', 'Demo Health System')
        ON CONFLICT (id) DO NOTHING;
        """
    )

    op.execute(
        f"""
        INSERT INTO hospital_reference (id, organization_id, hospital_name, address)
        VALUES ('{SEED_HOSPITAL_ID}', '{SEED_ORG_ID}', 'General Hospital (Demo)', '123 Main St, Anytown, USA')
        ON CONFLICT (id) DO NOTHING;
        """
    )
