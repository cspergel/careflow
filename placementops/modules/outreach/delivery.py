"""
Outreach delivery layer — Resend (email) and Twilio (SMS/voicemail_drop).

Called by mark_sent() after the OutreachAction has been committed to the DB.
Delivery is best-effort: failures update delivery_status to "failed" but do not
roll back the sent record — it is a permanent communication record.

Env vars required:
  RESEND_API_KEY          — Resend API key
  OUTREACH_FROM_EMAIL     — sender address (e.g. "PlacementOps <no-reply@yourorg.com>")
  TWILIO_ACCOUNT_SID      — Twilio Account SID
  TWILIO_AUTH_TOKEN       — Twilio Auth Token
  TWILIO_FROM_PHONE       — Twilio sender phone number in E.164 format (e.g. +15551234567)

delivery_status values returned:
  "delivered"               — provider accepted the message
  "failed"                  — provider returned an error
  "skipped_no_config"       — required env vars missing; delivery not attempted
  "skipped_no_facility"     — action has no facility_id; cannot look up contact
  "skipped_no_contact_email"— facility has no email on primary/fallback contact
  "skipped_no_contact_phone"— facility has no phone on primary/fallback contact
  "not_applicable"          — channel doesn't require automated delivery
                              (phone_manual, task, voice_ai)
"""

import logging
import os

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.models.facility_contact import FacilityContact
from placementops.core.models.outreach_action import OutreachAction

logger = logging.getLogger(__name__)

_RESEND_API_KEY = os.getenv("RESEND_API_KEY")
_FROM_EMAIL = os.getenv("OUTREACH_FROM_EMAIL", "PlacementOps <outreach@placementops.com>")
_TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
_TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
_TWILIO_FROM_PHONE = os.getenv("TWILIO_FROM_PHONE")

_EMAIL_CHANNELS = frozenset({"email"})
_SMS_CHANNELS = frozenset({"sms", "voicemail_drop"})
_BYPASS_CHANNELS = frozenset({"phone_manual", "task"})


async def _get_primary_contact(
    session: AsyncSession, facility_id: str
) -> FacilityContact | None:
    """Return the primary contact for a facility, falling back to the first contact."""
    result = await session.execute(
        select(FacilityContact).where(
            and_(
                FacilityContact.facility_id == facility_id,
                FacilityContact.is_primary.is_(True),
            )
        )
    )
    contact = result.scalar_one_or_none()
    if contact is None:
        result = await session.execute(
            select(FacilityContact)
            .where(FacilityContact.facility_id == facility_id)
            .limit(1)
        )
        contact = result.scalar_one_or_none()
    return contact


async def _send_email(action: OutreachAction, to_email: str) -> str:
    """Send email via Resend. Returns delivery_status."""
    if not _RESEND_API_KEY:
        logger.warning(
            "RESEND_API_KEY not configured — email delivery skipped for action %s",
            action.id,
        )
        return "skipped_no_config"

    try:
        import resend  # type: ignore[import-untyped]

        resend.api_key = _RESEND_API_KEY
        params: resend.Emails.SendParams = {
            "from": _FROM_EMAIL,
            "to": [to_email],
            "subject": action.draft_subject or "Placement Inquiry",
            "html": f"<div style='font-family:sans-serif;white-space:pre-wrap'>{action.draft_body}</div>",
            "text": action.draft_body or "",
        }
        response = resend.Emails.send(params)
        logger.info(
            "Email delivered via Resend: resend_id=%s action=%s to=%s",
            response.get("id"),
            action.id,
            to_email,
        )
        return "delivered"
    except Exception as exc:
        logger.error(
            "Resend email delivery failed for action %s to %s: %s",
            action.id,
            to_email,
            exc,
        )
        return "failed"


async def _send_sms(action: OutreachAction, to_phone: str) -> str:
    """Send SMS via Twilio. Returns delivery_status."""
    if not all([_TWILIO_ACCOUNT_SID, _TWILIO_AUTH_TOKEN, _TWILIO_FROM_PHONE]):
        logger.warning(
            "Twilio env vars not fully configured — SMS delivery skipped for action %s",
            action.id,
        )
        return "skipped_no_config"

    try:
        from twilio.rest import Client  # type: ignore[import-untyped]

        client = Client(_TWILIO_ACCOUNT_SID, _TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            body=action.draft_body or "",
            from_=_TWILIO_FROM_PHONE,
            to=to_phone,
        )
        logger.info(
            "SMS delivered via Twilio: sid=%s action=%s to=%s",
            message.sid,
            action.id,
            to_phone,
        )
        return "delivered"
    except Exception as exc:
        logger.error(
            "Twilio SMS delivery failed for action %s to %s: %s",
            action.id,
            to_phone,
            exc,
        )
        return "failed"


async def deliver_action(session: AsyncSession, action: OutreachAction) -> str:
    """
    Attempt delivery of an outreach action.

    Dispatches to Resend (email) or Twilio (sms/voicemail_drop) based on channel.
    phone_manual and task are manual — no automated delivery needed.
    voice_ai is Phase 2 — returns "not_applicable".

    Returns a delivery_status string to be persisted on the action.
    Never raises — all exceptions are caught and logged.
    """
    if action.channel in _BYPASS_CHANNELS:
        return "not_applicable"

    if action.channel == "voice_ai":
        logger.info("voice_ai delivery is Phase 2 — skipped for action %s", action.id)
        return "not_applicable"

    if not action.facility_id:
        logger.warning(
            "action %s has no facility_id — cannot resolve contact for delivery",
            action.id,
        )
        return "skipped_no_facility"

    contact = await _get_primary_contact(session, action.facility_id)

    if action.channel in _EMAIL_CHANNELS:
        if not contact or not contact.email:
            logger.warning(
                "No email address on facility contact for action %s (facility %s)",
                action.id,
                action.facility_id,
            )
            return "skipped_no_contact_email"
        return await _send_email(action, contact.email)

    if action.channel in _SMS_CHANNELS:
        if not contact or not contact.phone:
            logger.warning(
                "No phone number on facility contact for action %s (facility %s)",
                action.id,
                action.facility_id,
            )
            return "skipped_no_contact_phone"
        return await _send_sms(action, contact.phone)

    logger.warning("Unknown channel '%s' for action %s", action.channel, action.id)
    return "not_applicable"
