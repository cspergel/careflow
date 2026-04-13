"""
SMS module router.

Endpoints:
  POST /api/v1/cases/{case_id}/sms-conversation  — coordinator initiates patient SMS
  GET  /api/v1/cases/{case_id}/sms-conversation  — get conversation status
  POST /api/v1/webhooks/twilio/sms               — Twilio inbound SMS webhook
"""

import hashlib
import hmac
import logging
import os
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.auth import AuthContext, get_auth_context
from placementops.core.database import get_db
from placementops.modules.sms import service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["sms"])

_TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")


# ---------------------------------------------------------------------------
# Twilio signature validation
# ---------------------------------------------------------------------------

def _validate_twilio_signature(request_url: str, params: dict, signature: str) -> bool:
    """Validate that the request genuinely came from Twilio."""
    if not _TWILIO_AUTH_TOKEN:
        # No token configured — skip validation in dev (log warning)
        logger.warning("TWILIO_AUTH_TOKEN not set — skipping Twilio signature validation")
        return True

    sorted_params = "".join(f"{k}{v}" for k, v in sorted(params.items()))
    expected = hmac.new(
        _TWILIO_AUTH_TOKEN.encode("utf-8"),
        (request_url + sorted_params).encode("utf-8"),
        hashlib.sha1,
    ).digest()
    import base64
    expected_b64 = base64.b64encode(expected).decode("utf-8")
    return hmac.compare_digest(expected_b64, signature)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SmsConversationResponse(BaseModel):
    id: str
    patient_case_id: str
    phone_number: str
    state: str
    chosen_facility_id: str | None
    conversation_json: list
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# POST /cases/{case_id}/sms-conversation — initiate
# ---------------------------------------------------------------------------

@router.post(
    "/cases/{case_id}/sms-conversation",
    response_model=SmsConversationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def initiate_patient_sms(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> SmsConversationResponse:
    """Start an AI-driven patient SMS placement options conversation."""
    if auth.role_key not in ("placement_coordinator", "manager", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only placement coordinators and managers can initiate patient SMS",
        )

    conversation = await service.initiate_conversation(
        session=db,
        case_id=case_id,
        initiated_by_user_id=auth.user_id,
        organization_id=auth.organization_id,
    )

    return SmsConversationResponse(
        id=conversation.id,
        patient_case_id=conversation.patient_case_id,
        phone_number=conversation.phone_number,
        state=conversation.state,
        chosen_facility_id=conversation.chosen_facility_id,
        conversation_json=conversation.conversation_json,
        created_at=conversation.created_at.isoformat(),
        updated_at=conversation.updated_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# GET /cases/{case_id}/sms-conversation — status
# ---------------------------------------------------------------------------

@router.get(
    "/cases/{case_id}/sms-conversation",
    response_model=SmsConversationResponse | None,
)
async def get_patient_sms(
    case_id: UUID,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> SmsConversationResponse | None:
    """Return the most recent SMS conversation for a case, or null if none."""
    conversation = await service.get_conversation(
        session=db,
        case_id=case_id,
        organization_id=auth.organization_id,
    )
    if conversation is None:
        return None

    return SmsConversationResponse(
        id=conversation.id,
        patient_case_id=conversation.patient_case_id,
        phone_number=conversation.phone_number,
        state=conversation.state,
        chosen_facility_id=conversation.chosen_facility_id,
        conversation_json=conversation.conversation_json,
        created_at=conversation.created_at.isoformat(),
        updated_at=conversation.updated_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# POST /webhooks/twilio/sms — inbound from Twilio
# ---------------------------------------------------------------------------

@router.post("/webhooks/twilio/sms", include_in_schema=False)
async def twilio_sms_webhook(
    request: Request,
    From: str = Form(...),
    Body: str = Form(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Twilio inbound SMS webhook.
    Validates Twilio signature then routes to the conversation state machine.
    Returns empty TwiML — replies are sent proactively via Twilio REST API.
    """
    signature = request.headers.get("X-Twilio-Signature", "")
    form_data = dict(await request.form())

    if not _validate_twilio_signature(str(request.url), form_data, signature):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Twilio signature",
        )

    logger.info("Inbound SMS from %s: %r", From, Body[:80])

    await service.handle_inbound(
        session=db,
        from_phone=From,
        body=Body,
    )

    # Return empty TwiML — we reply via REST, not via TwiML response
    return {}
