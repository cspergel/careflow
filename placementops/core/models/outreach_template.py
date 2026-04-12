# @forgeplan-node: core-infrastructure
"""OutreachTemplate ORM model — reusable outreach message templates."""
# @forgeplan-spec: AC1

from uuid import uuid4
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column

from placementops.core.database import Base


class OutreachTemplate(Base):
    __tablename__ = "outreach_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    organization_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("organizations.id"), nullable=False, index=True
    )
    template_name: Mapped[str] = mapped_column(String, nullable=False)
    template_type: Mapped[str] = mapped_column(
        String, nullable=False
    )  # email|phone_manual|task|voice_ai_script
    subject_template: Mapped[str | None] = mapped_column(String, nullable=True)
    body_template: Mapped[str] = mapped_column(String, nullable=False)
    allowed_variables: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )
