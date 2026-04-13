"""
Patient SMS conversation service.

Manages AI-driven SMS flows that present facility placement options to patients/families.
Structured flow (YES/STOP/1/2/3) handled in code; everything else routed to Claude.

Conversation states:
  consent_pending → active → completed | opted_out
"""

import logging
import os
from datetime import datetime, timezone
from uuid import UUID, uuid4

from anthropic import Anthropic
from fastapi import HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from placementops.core.events import CaseActivityEvent, publish_case_activity_event
from placementops.core.models.facility import Facility
from placementops.core.models.facility_match import FacilityMatch
from placementops.core.models.patient_case import PatientCase
from placementops.core.models.sms_conversation import SmsConversation

logger = logging.getLogger(__name__)

_ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
_TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
_TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
_TWILIO_FROM_PHONE = os.getenv("TWILIO_FROM_PHONE")
_DELIVERY_MODE = os.getenv("OUTREACH_DELIVERY_MODE", "live")


# ---------------------------------------------------------------------------
# Twilio send helper
# ---------------------------------------------------------------------------

def _send_sms(to_phone: str, body: str) -> None:
    """Send an SMS via Twilio (or log if in log mode)."""
    if _DELIVERY_MODE == "log":
        logger.info(
            "\n%s\n[SMS LOG] To: %s\n%s\n%s",
            "=" * 60, to_phone, body, "=" * 60,
        )
        return

    if not all([_TWILIO_ACCOUNT_SID, _TWILIO_AUTH_TOKEN, _TWILIO_FROM_PHONE]):
        logger.warning("Twilio not configured — SMS to %s skipped", to_phone)
        return

    from twilio.rest import Client
    client = Client(_TWILIO_ACCOUNT_SID, _TWILIO_AUTH_TOKEN)
    client.messages.create(body=body, from_=_TWILIO_FROM_PHONE, to=to_phone)


# ---------------------------------------------------------------------------
# Facility options builder
# ---------------------------------------------------------------------------

async def _get_facility_options(
    session: AsyncSession, case_id: str
) -> list[dict]:
    """Return selected facility matches for the case with facility details."""
    result = await session.execute(
        select(FacilityMatch, Facility)
        .join(Facility, Facility.id == FacilityMatch.facility_id)
        .where(
            and_(
                FacilityMatch.patient_case_id == case_id,
                FacilityMatch.selected_for_outreach.is_(True),
            )
        )
        .order_by(FacilityMatch.match_rank)
        .limit(5)
    )
    rows = result.all()

    options = []
    for match, facility in rows:
        distance = f"{match.distance_miles:.1f} mi" if match.distance_miles else ""
        options.append({
            "facility_id": facility.id,
            "name": facility.facility_name,
            "type": facility.facility_type.upper(),
            "distance": distance,
        })
    return options


def _format_options_message(options: list[dict]) -> str:
    lines = ["Here are some options we've arranged for you:"]
    for i, opt in enumerate(options, 1):
        dist = f" – {opt['distance']}" if opt["distance"] else ""
        lines.append(f"{i}. {opt['name']} ({opt['type']}){dist}")
    lines.append("\nReply with a number to select an option, or ask us anything.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Claude fallback
# ---------------------------------------------------------------------------

def _claude_reply(
    conversation_history: list[dict],
    org_name: str,
    hospital_name: str,
    patient_first_name: str,
    options: list[dict],
) -> str:
    """Ask Claude to generate the next reply in the conversation."""
    if not _ANTHROPIC_API_KEY:
        return (
            "I'm sorry, I didn't quite catch that. "
            "Please reply with a number (1, 2, 3…) to select an option, "
            "or reply STOP to opt out."
        )

    options_text = "\n".join(
        f"{i}. {o['name']} ({o['type']})"
        for i, o in enumerate(options, 1)
    )

    system_prompt = f"""You are a helpful care coordination assistant for {org_name} at {hospital_name}.
You are texting {patient_first_name} (or their family) via SMS to help them understand their post-discharge care options.

The available options are:
{options_text}

Your role:
- Answer questions about the options clearly and briefly (SMS-friendly, under 160 chars when possible)
- Be warm, simple, and jargon-free
- If they seem ready to choose, gently re-present the numbered list
- NEVER give medical advice or make clinical recommendations
- NEVER discuss costs, insurance details, or guarantees
- If asked something outside your scope, say: "For that, please speak directly with your care team."
- Always end with a clear prompt: ask them to reply with a number or STOP

Keep replies short — this is SMS."""

    messages = [
        {"role": m["role"], "content": m["content"]}
        for m in conversation_history
        if m["role"] in ("user", "assistant")
    ]

    client = Anthropic(api_key=_ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        system=system_prompt,
        messages=messages,
    )
    return response.content[0].text.strip()


# ---------------------------------------------------------------------------
# Conversation append helper
# ---------------------------------------------------------------------------

def _append_message(conversation: SmsConversation, role: str, content: str) -> None:
    history = list(conversation.conversation_json or [])
    history.append({
        "role": role,
        "content": content,
        "ts": datetime.now(timezone.utc).isoformat(),
    })
    conversation.conversation_json = history


# ---------------------------------------------------------------------------
# Public: initiate_conversation
# ---------------------------------------------------------------------------

async def initiate_conversation(
    session: AsyncSession,
    case_id: UUID,
    initiated_by_user_id: UUID,
    organization_id: UUID,
) -> SmsConversation:
    """
    Start a patient SMS conversation for a case.
    Sends the opt-in message and creates the SmsConversation record.
    Raises 400 if patient_phone is not set on the case.
    Raises 400 if case is not at facility_options_generated.
    """
    result = await session.execute(
        select(PatientCase).where(
            and_(
                PatientCase.id == str(case_id),
                PatientCase.organization_id == str(organization_id),
            )
        )
    )
    case = result.scalar_one_or_none()
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    if not case.patient_phone:
        raise HTTPException(
            status_code=400,
            detail="patient_phone is required to start an SMS conversation",
        )

    if case.current_status != "facility_options_generated":
        raise HTTPException(
            status_code=400,
            detail=(
                f"Case must be at facility_options_generated to start patient SMS "
                f"(current: {case.current_status})"
            ),
        )

    # Supersede any existing open conversation for this case
    existing = await session.execute(
        select(SmsConversation).where(
            and_(
                SmsConversation.patient_case_id == str(case_id),
                SmsConversation.state.in_(["consent_pending", "active"]),
            )
        )
    )
    for old in existing.scalars().all():
        old.state = "opted_out"

    # Get org/hospital name for the message
    # Use organization name; hospital name comes from the case's hospital_id
    from placementops.core.models.organization import Organization
    org_result = await session.execute(
        select(Organization).where(Organization.id == str(organization_id))
    )
    org = org_result.scalar_one_or_none()
    org_name = org.name if org else "your care team"

    patient_first = (case.patient_name or "").split()[0] if case.patient_name else "there"

    opt_in_message = (
        f"Hi {patient_first}, this is {org_name}. "
        "Should you need rehabilitation or care on discharge, we have some "
        "recommended options available to you. "
        "Reply YES to see them, or STOP at any time."
    )

    conversation = SmsConversation(
        id=str(uuid4()),
        patient_case_id=str(case_id),
        phone_number=case.patient_phone,
        state="consent_pending",
        conversation_json=[],
        initiated_by_user_id=str(initiated_by_user_id),
    )
    session.add(conversation)
    _append_message(conversation, "assistant", opt_in_message)

    await session.commit()
    await session.refresh(conversation)

    _send_sms(case.patient_phone, opt_in_message)
    return conversation


# ---------------------------------------------------------------------------
# Public: handle_inbound
# ---------------------------------------------------------------------------

async def handle_inbound(
    session: AsyncSession,
    from_phone: str,
    body: str,
) -> None:
    """
    Handle an inbound SMS reply from a patient/family.
    Looks up the open conversation by phone number and dispatches.
    Silently ignores if no open conversation found.
    """
    result = await session.execute(
        select(SmsConversation).where(
            and_(
                SmsConversation.phone_number == from_phone,
                SmsConversation.state.in_(["consent_pending", "active"]),
            )
        )
        .order_by(SmsConversation.created_at.desc())
        .limit(1)
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        logger.info("Inbound SMS from %s — no open conversation found, ignoring", from_phone)
        return

    text = body.strip().upper()
    _append_message(conversation, "user", body.strip())

    # STOP at any point
    if text in ("STOP", "UNSUBSCRIBE", "CANCEL", "END", "QUIT"):
        await _handle_opt_out(session, conversation)
        return

    if conversation.state == "consent_pending":
        await _handle_consent(session, conversation, text)
    elif conversation.state == "active":
        await _handle_active(session, conversation, body.strip())


async def _handle_consent(
    session: AsyncSession,
    conversation: SmsConversation,
    text: str,
) -> None:
    if text in ("YES", "Y", "YEP", "YEAH", "OK", "OKAY", "SURE"):
        conversation.state = "active"

        options = await _get_facility_options(session, conversation.patient_case_id)
        if not options:
            reply = (
                "Thank you! Our team will be in touch shortly with your options. "
                "If you have questions, please contact your care coordinator directly."
            )
            _append_message(conversation, "assistant", reply)
            await session.commit()
            _send_sms(conversation.phone_number, reply)
            return

        reply = _format_options_message(options)
        _append_message(conversation, "assistant", reply)
        await session.commit()
        _send_sms(conversation.phone_number, reply)
    else:
        # Re-prompt
        reply = (
            "Sorry, we didn't catch that. Reply YES to see your placement options, "
            "or STOP to opt out."
        )
        _append_message(conversation, "assistant", reply)
        await session.commit()
        _send_sms(conversation.phone_number, reply)


async def _handle_active(
    session: AsyncSession,
    conversation: SmsConversation,
    body: str,
) -> None:
    options = await _get_facility_options(session, conversation.patient_case_id)

    # Check for a numbered selection
    clean = body.strip()
    if clean.isdigit():
        idx = int(clean) - 1
        if 0 <= idx < len(options):
            await _record_choice(session, conversation, options[idx])
            return

    # Route to Claude for everything else
    case_result = await session.execute(
        select(PatientCase).where(PatientCase.id == conversation.patient_case_id)
    )
    case = case_result.scalar_one_or_none()

    from placementops.core.models.organization import Organization
    org_result = await session.execute(
        select(Organization).where(
            Organization.id == (case.organization_id if case else "")
        )
    )
    org = org_result.scalar_one_or_none()

    patient_first = (case.patient_name or "").split()[0] if case else "there"
    org_name = org.name if org else "your care team"

    # Build hospital name from case if available
    hospital_name = org_name  # fallback; can enhance with hospital_reference lookup

    reply = _claude_reply(
        conversation_history=conversation.conversation_json,
        org_name=org_name,
        hospital_name=hospital_name,
        patient_first_name=patient_first,
        options=options,
    )
    _append_message(conversation, "assistant", reply)
    await session.commit()
    _send_sms(conversation.phone_number, reply)


async def _record_choice(
    session: AsyncSession,
    conversation: SmsConversation,
    chosen: dict,
) -> None:
    conversation.chosen_facility_id = chosen["facility_id"]
    conversation.state = "completed"

    reply = (
        f"Great choice! We've noted your preference for {chosen['name']}. "
        "Your care coordinator will be in touch to confirm next steps. "
        "Thank you!"
    )
    _append_message(conversation, "assistant", reply)
    await session.commit()

    _send_sms(conversation.phone_number, reply)

    # Load case to notify coordinator
    case_result = await session.execute(
        select(PatientCase).where(PatientCase.id == conversation.patient_case_id)
    )
    case = case_result.scalar_one_or_none()

    # Notify coordinator via SMS if configured
    if case:
        coordinator_msg = (
            f"Patient {case.patient_name} selected {chosen['name']} "
            f"for case {str(case.id)[:8]}. Ready for next steps."
        )
        # Find the coordinator's phone — for now log it
        logger.info("[COORDINATOR NOTIFY] %s", coordinator_msg)

        # Log to case timeline
        await publish_case_activity_event(
            CaseActivityEvent(
                case_id=UUID(conversation.patient_case_id),
                actor_user_id=UUID(conversation.initiated_by_user_id),
                event_type="patient_sms_choice_made",
                old_status=case.current_status,
                new_status=case.current_status,
                occurred_at=datetime.now(timezone.utc),
                organization_id=UUID(case.organization_id),
                metadata={
                    "chosen_facility_id": chosen["facility_id"],
                    "chosen_facility_name": chosen["name"],
                    "conversation_id": conversation.id,
                },
            )
        )


async def _handle_opt_out(
    session: AsyncSession,
    conversation: SmsConversation,
) -> None:
    conversation.state = "opted_out"
    reply = "You've been unsubscribed. Contact your care team directly with any questions."
    _append_message(conversation, "assistant", reply)
    await session.commit()
    _send_sms(conversation.phone_number, reply)

    case_result = await session.execute(
        select(PatientCase).where(PatientCase.id == conversation.patient_case_id)
    )
    case = case_result.scalar_one_or_none()
    if case:
        logger.info(
            "[COORDINATOR NOTIFY] Patient %s opted out of SMS for case %s",
            case.patient_name,
            str(case.id)[:8],
        )


# ---------------------------------------------------------------------------
# Public: get_conversation
# ---------------------------------------------------------------------------

async def get_conversation(
    session: AsyncSession,
    case_id: UUID,
    organization_id: UUID,
) -> SmsConversation | None:
    """Return the most recent SMS conversation for a case."""
    # Verify case belongs to org
    case_result = await session.execute(
        select(PatientCase).where(
            and_(
                PatientCase.id == str(case_id),
                PatientCase.organization_id == str(organization_id),
            )
        )
    )
    if case_result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")

    result = await session.execute(
        select(SmsConversation)
        .where(SmsConversation.patient_case_id == str(case_id))
        .order_by(SmsConversation.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
