# @forgeplan-node: outcomes-module
# @forgeplan-spec: AC1, AC2, AC3, AC4, AC5, AC6, AC7, AC8, AC9, AC10, AC11, AC12, AC13
"""
Pydantic schemas for the outcomes module.

Request and response models for:
  - PlacementOutcomeCreate
  - PlacementOutcomeResponse
  - OutcomeHistoryResponse
  - CaseTimelineResponse
  - StatusTransitionRequest
  - CaseActivityEventResponse
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class PlacementOutcomeCreate(BaseModel):
    """
    Payload for recording a placement outcome.

    facility_id is required for accepted/declined/placed; nullable for
    family_declined/withdrawn (AC7 — outcome_type-conditional validation).
    decline_reason_code is required when outcome_type=declined (AC4).
    """

    # @forgeplan-spec: AC2
    # @forgeplan-spec: AC4
    # @forgeplan-spec: AC7
    outcome_type: str = Field(
        ...,
        description="One of: accepted | declined | placed | family_declined | withdrawn",
    )
    facility_id: Optional[UUID] = Field(
        default=None,
        description="Required for accepted/declined/placed; nullable for family_declined/withdrawn",
    )
    decline_reason_code: Optional[str] = Field(
        default=None,
        description="Required when outcome_type=declined; must match decline_reason_reference.code",
    )
    decline_reason_text: Optional[str] = Field(
        default=None,
        description="Optional free-text supplement to decline_reason_code",
    )

    @model_validator(mode="after")
    def validate_outcome_type_rules(self) -> "PlacementOutcomeCreate":
        """
        Enforce outcome_type-conditional field requirements at the schema level.

        - accepted/declined/placed: facility_id required
        - family_declined/withdrawn: facility_id nullable
        - declined: decline_reason_code required
        """
        # @forgeplan-spec: AC4
        # @forgeplan-spec: AC7
        VALID_TYPES = {"accepted", "declined", "placed", "family_declined", "withdrawn"}
        if self.outcome_type not in VALID_TYPES:
            raise ValueError(
                f"outcome_type must be one of {sorted(VALID_TYPES)}, got '{self.outcome_type}'"
            )

        requires_facility = {"accepted", "declined", "placed"}
        if self.outcome_type in requires_facility and self.facility_id is None:
            raise ValueError(
                f"facility_id is required for outcome_type='{self.outcome_type}'"
            )

        if self.outcome_type == "declined" and not self.decline_reason_code:
            raise ValueError("decline_reason_code is required when outcome_type=declined")

        return self


class StatusTransitionRequest(BaseModel):
    """
    Payload for POST /api/v1/cases/{case_id}/status-transition.

    Used for retry routing (declined_retry_needed → ready_for_matching or
    outreach_pending_approval) and case closure (→ closed).

    transition_reason is required (non-empty) when to_status=closed (AC11).
    """

    # @forgeplan-spec: AC9
    # @forgeplan-spec: AC11
    to_status: str = Field(..., description="Target case status")
    transition_reason: Optional[str] = Field(
        default=None,
        description="Required (non-empty) when to_status=closed",
    )


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class PlacementOutcomeResponse(BaseModel):
    """Full representation of a PlacementOutcome record."""

    id: UUID
    patient_case_id: UUID
    facility_id: Optional[UUID]
    outcome_type: str
    decline_reason_code: Optional[str]
    decline_reason_text: Optional[str]
    recorded_by_user_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class OutcomeHistoryResponse(BaseModel):
    """Paginated outcome history for a case (AC13)."""

    # @forgeplan-spec: AC13
    items: list[PlacementOutcomeResponse]
    total: int


class CaseActivityEventResponse(BaseModel):
    """A single entry in the case timeline, sourced from CaseStatusHistory."""

    # @forgeplan-spec: AC12
    case_id: UUID
    actor_user_id: Optional[UUID]
    event_type: str
    old_status: Optional[str]
    new_status: Optional[str]
    occurred_at: datetime


class CaseTimelineResponse(BaseModel):
    """Chronological timeline of case activity events (AC12)."""

    # @forgeplan-spec: AC12
    events: list[CaseActivityEventResponse]
    total: int
