# @forgeplan-node: core-infrastructure
"""OutreachAction ORM model — a single outreach communication to a facility for a case."""
# @forgeplan-spec: AC1

from uuid import uuid4
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from placementops.core.database import Base


class OutreachAction(Base):
    __tablename__ = "outreach_actions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    patient_case_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("patient_cases.id"), nullable=False, index=True
    )
    facility_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("facilities.id"), nullable=True
    )
    template_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("outreach_templates.id"), nullable=True
    )

    action_type: Mapped[str] = mapped_column(
        String, nullable=False
    )  # facility_outreach|internal_alert|cm_update|follow_up_reminder
    channel: Mapped[str] = mapped_column(
        String, nullable=False
    )  # email|phone_manual|task|sms|voicemail_drop|voice_ai

    draft_subject: Mapped[str | None] = mapped_column(String, nullable=True)
    draft_body: Mapped[str] = mapped_column(String, nullable=False)

    approval_status: Mapped[str] = mapped_column(
        String, nullable=False, default="draft"
    )  # draft|pending_approval|approved|sent|canceled|failed

    approved_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    sent_by_user_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(nullable=True)
    delivery_status: Mapped[str | None] = mapped_column(String, nullable=True)

    # Phase 2 voice fields
    call_transcript_url: Mapped[str | None] = mapped_column(String, nullable=True)
    call_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    call_outcome_summary: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )
