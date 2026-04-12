# @forgeplan-node: core-infrastructure
"""User ORM model — authenticated platform user with org-scoped role."""
# @forgeplan-spec: AC1

from uuid import uuid4
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from placementops.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String, nullable=False)
    role_key: Mapped[str] = mapped_column(
        String, nullable=False
    )  # admin|intake_staff|clinical_reviewer|placement_coordinator|manager|read_only
    status: Mapped[str] = mapped_column(String, nullable=False, default="active")  # active|inactive
    timezone: Mapped[str | None] = mapped_column(String, nullable=True)
    default_hospital_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("hospital_reference.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )
