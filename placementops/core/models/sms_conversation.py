"""SmsConversation ORM model — tracks AI-driven patient SMS placement flows."""

from uuid import uuid4
from datetime import datetime

from sqlalchemy import ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from placementops.core.database import Base


class SmsConversation(Base):
    __tablename__ = "sms_conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    patient_case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("patient_cases.id"), nullable=False, index=True
    )
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    # consent_pending | active | completed | opted_out
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="consent_pending")
    # [{role: "system"|"assistant"|"user", content: str, ts: iso}]
    conversation_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    chosen_facility_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("facilities.id"), nullable=True
    )
    initiated_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )
