# @forgeplan-node: core-infrastructure
"""
Canonical export of all ORM model classes.

All other modules MUST import models from this package:
    from placementops.core.models import PatientCase, User, ...

Do NOT redefine any of these models in downstream modules.
"""
# @forgeplan-spec: AC1

from placementops.core.models.reference_tables import (
    Organization,
    UserRole,
    DeclineReasonReference,
    PayerReference,
    HospitalReference,
)
from placementops.core.models.user import User
from placementops.core.models.patient_case import PatientCase, CASE_STATUSES
from placementops.core.models.facility import Facility
from placementops.core.models.facility_capabilities import FacilityCapabilities
from placementops.core.models.facility_insurance_rule import FacilityInsuranceRule
from placementops.core.models.facility_contact import FacilityContact
from placementops.core.models.outreach_action import OutreachAction
from placementops.core.models.outreach_template import OutreachTemplate
from placementops.core.models.clinical_assessment import ClinicalAssessment
from placementops.core.models.facility_match import FacilityMatch
from placementops.core.models.import_job import ImportJob
from placementops.core.models.placement_outcome import PlacementOutcome
from placementops.core.models.audit_event import AuditEvent
from placementops.core.models.case_status_history import CaseStatusHistory

__all__ = [
    # Reference tables
    "Organization",
    "UserRole",
    "DeclineReasonReference",
    "PayerReference",
    "HospitalReference",
    # Core entities
    "User",
    "PatientCase",
    "CASE_STATUSES",
    "Facility",
    "FacilityCapabilities",
    "FacilityInsuranceRule",
    "FacilityContact",
    # Workflow
    "OutreachAction",
    "OutreachTemplate",
    "ClinicalAssessment",
    "FacilityMatch",
    "ImportJob",
    "PlacementOutcome",
    # Audit / compliance
    "AuditEvent",
    "CaseStatusHistory",
]
