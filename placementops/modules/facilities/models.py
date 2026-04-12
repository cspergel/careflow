# @forgeplan-node: facilities-module
"""
Module-local ORM models for the facilities module.

FacilityPreference is defined here (not in core models) because it is
facilities-specific and not yet required by any other module.

Registers with the shared Base from placementops.core.database so that
create_all() in tests picks up the table automatically.
"""
# @forgeplan-spec: AC11
# @forgeplan-decision: D-facilities-1-preference-local-model -- FacilityPreference defined in facilities module not core. Why: model absent from core/models/__init__.py and no other module depends on it; avoids circular imports and keeps facilities concerns self-contained

from uuid import uuid4
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from placementops.core.database import Base


class FacilityPreference(Base):
    """
    Ranked facility preference scoped to global, market, or hospital context.

    One row per (facility_id, scope, scope_reference_id) combination.
    preference_rank drives ordering within a scope for the matching engine.

    RLS constraint: facility must belong to caller's organization_id.
    """

    __tablename__ = "facility_preferences"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )
    facility_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("facilities.id"), nullable=False, index=True
    )
    # @forgeplan-spec: AC11
    scope: Mapped[str] = mapped_column(
        String, nullable=False
    )  # global | market | hospital
    scope_reference_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True
    )  # hospital_reference.id for hospital scope; market id for market scope
    preference_rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )
