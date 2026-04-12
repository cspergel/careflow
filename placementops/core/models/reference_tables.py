# @forgeplan-node: core-infrastructure
"""
Reference / lookup table ORM models.

Includes: Organization, UserRole, DeclineReasonReference, PayerReference, HospitalReference.
These tables are seeded once and rarely change.
"""
# @forgeplan-spec: AC1
# @forgeplan-spec: AC10

from uuid import uuid4
from datetime import datetime

from sqlalchemy import ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from placementops.core.database import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())


class UserRole(Base):
    __tablename__ = "user_roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    role_key: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)


class DeclineReasonReference(Base):
    __tablename__ = "decline_reason_reference"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String, nullable=False)
    display_order: Mapped[int] = mapped_column(nullable=False, default=0)


class PayerReference(Base):
    __tablename__ = "payer_reference"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    payer_name: Mapped[str] = mapped_column(String, nullable=False)
    payer_type: Mapped[str | None] = mapped_column(String, nullable=True)


class HospitalReference(Base):
    __tablename__ = "hospital_reference"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False
    )
    hospital_name: Mapped[str] = mapped_column(String, nullable=False)
    address: Mapped[str | None] = mapped_column(String, nullable=True)
