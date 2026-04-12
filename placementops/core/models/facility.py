# @forgeplan-node: core-infrastructure
"""Facility ORM model — post-acute care facility master record."""
# @forgeplan-spec: AC1

from uuid import uuid4
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from placementops.core.database import Base


class Facility(Base):
    __tablename__ = "facilities"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )

    facility_name: Mapped[str] = mapped_column(String, nullable=False)
    facility_type: Mapped[str] = mapped_column(String, nullable=False)  # snf|irf|ltach

    address_line_1: Mapped[str | None] = mapped_column(String, nullable=True)
    city: Mapped[str | None] = mapped_column(String, nullable=True)
    county: Mapped[str | None] = mapped_column(String, nullable=True)
    state: Mapped[str | None] = mapped_column(String, nullable=True)
    zip: Mapped[str | None] = mapped_column(String, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)

    active_status: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )
