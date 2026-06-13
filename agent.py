import os
import logging
import re
from dataclasses import dataclass, field

import anthropic

from knowledge_base import get_faq_context, get_available_slots

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You are Sarah, a friendly dental receptionist at Smile Care Dental. You help patients book appointments, answer questions about services, and provide office information. Keep responses under 40 words. Never give medical advice. If a patient has a dental emergency, immediately offer to transfer to a dentist.

OFFICE KNOWLEDGE BASE:
{faq_context}

AVAILABLE APPOINTMENT SLOTS THIS WEEK:
{slots}

RULES:
- Always be warm, professional, and empathetic
- Keep every response under 40 words
- Never diagnose or give medical advice
- For dental emergencies (severe pain, broken tooth, swelling), offer immediate transfer
- When booking: collect patient name, preferred slot from available times, and appointment type
- Confirm bookings by reading back all details
- If caller asks for a human/representative/manager, say you'll transfer them right away
- Do not mention you are an AI unless directly asked
"""

TRANSFER_TRIGGERS = [
    "speak to human",
    "speak to a human",
    "talk to human",
    "talk to a human",
    "real person",
    "representative",
    "speak to someone",
    "talk to someone",
    "operator",
    "manager",
    "transfer me",
    "connect me",
    "i need help",
    "human please",
]

EMERGENCY_KEYWORDS = [
    "emergency",
    "severe pain",
    "unbearable pain",
    "broken tooth",
    "knocked out",
    "knocked-out",
    "swelling",
    "abscess",
    "bleeding",
    "can't eat",
    "cannot eat",
]


@dataclass
class ConversationState:
    call_sid: str
    history: list[dict] = field(default_factory=list)
    intent: str = "unknown"
    patient_name: str = ""
    requested_slot: str = ""
    appointment_type: str = ""
    booking_confirmed: bool = False
    transfer_requested: bool = False
    turn_count: int = 0


# In-memory session store keyed by call_sid
_sessions: dict[str, ConversationState] = {}


def get_or_create_session(call_sid: str) -> ConversationState:
    if call_sid not in _sessions:
        _sessions[call_sid] = ConversationState(call_sid=call_sid)
    return _sessions[call_sid]


def clear_session(call_sid: str) -> None:
    _sessions.pop(call_sid, None)


def _detect_transfer_request(text: str) -> bool:
    lower = text.lower()
    return any(trigger in lower for trigger in TRANSFER_TRIGGERS)


def _detect_emergency(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in EMERGENCY_KEYWORDS)


def _detect_intent(text: str) -> str:
    lower = text.lower()
    if any(w in lower for w in ["book", "schedule", "appointment", "make an appointment", "come in"]):
        return "booking"
    if any(w in lower for w in ["cancel", "cancellation"]):
        return "cancellation"
    if any(w in lower for w in ["reschedule", "change my appointment", "move my appointment"]):
        return "reschedule"
    if any(w in lower for w in ["hours", "open", "close", "when", "location", "address", "where"]):
        return "faq"
    if any(w in lower for w in ["insurance", "accept", "coverage", "plan"]):
        return "insurance"
    if any(w in lower for w in ["price", "cost", "how much", "fee"]):
        return "pricing"
    return "general"


def _extract_patient_name(text: str, existing_name: str) -> str:
    if existing_name:
        return existing_name
    patterns = [
        r"(?:my name is|i'm|i am|this is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        r"^([A-Z][a-z]+\s+[A-Z][a-z]+)$",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return existing_name


def get_greeting() -> str:
    return "Thank you for calling Smile Care Dental. This is Sarah. How can I help you today?"


async def process_speech(call_sid: str, speech_input: str) -> tuple[str, bool, bool]:
    """
    Process caller speech and return (response_text, should_transfer, is_booking_confirmed).
    """
    session = get_or_create_session(call_sid)
    session.turn_count += 1

    if _detect_transfer_request(speech_input):
        session.transfer_requested = True
        return "I'll connect you with our team right away. Please hold.", True, False

    is_emergency = _detect_emergency(speech_input)

    if session.intent == "unknown":
        session.intent = _detect_intent(speech_input)

    session.patient_name = _extract_patient_name(speech_input, session.patient_name)

    session.history.append({"role": "user", "content": speech_input})

    system = SYSTEM_PROMPT.format(
        faq_context=get_faq_context(),
        slots="\n".join(f"- {s}" for s in get_available_slots()),
    )

    if is_emergency:
        system += "\n\nIMPORTANT: The patient may be describing a dental emergency. Immediately express concern and offer to transfer to a dentist."

    if not ANTHROPIC_API_KEY:
        response_text = _fallback_response(session, speech_input)
    else:
        try:
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            message = client.messages.create(
                model=MODEL,
                max_tokens=150,
                system=system,
                messages=session.history,
            )
            response_text = message.content[0].text.strip()
        except Exception as exc:
            logger.error("Claude API error: %s", exc)
            response_text = _fallback_response(session, speech_input)

    session.history.append({"role": "assistant", "content": response_text})

    should_transfer = _detect_transfer_request(response_text) or (
        is_emergency and "transfer" in response_text.lower()
    )

    booking_confirmed = (
        "confirmed" in response_text.lower() or "booked" in response_text.lower()
    ) and session.intent == "booking"

    if booking_confirmed:
        session.booking_confirmed = True

    return response_text, should_transfer, booking_confirmed


def _fallback_response(session: ConversationState, user_input: str) -> str:
    """Rule-based fallback when Claude API is unavailable."""
    lower = user_input.lower()
    slots = get_available_slots()

    if session.intent == "booking":
        if not session.patient_name:
            return "I'd be happy to help schedule that. May I have your name please?"
        if not session.requested_slot:
            available = ", ".join(slots[:3])
            return f"Great! We have openings on {available}. Which works for you?"
        return f"Perfect! I've booked {session.requested_slot} for {session.patient_name}. You'll receive a confirmation text. Is there anything else?"

    if "hours" in lower or "open" in lower:
        return "We're open Monday through Friday 8am to 6pm, and Saturday 9am to 2pm. Closed Sundays."
    if "insurance" in lower:
        return "We accept Delta Dental, Cigna, Aetna, and BlueCross BlueShield. We also offer self-pay options."
    if "location" in lower or "address" in lower or "where" in lower:
        return "We're located at 123 Main Street, Annapolis MD 21401. Easy parking right out front."
    if "price" in lower or "cost" in lower or "how much" in lower:
        return "A new patient exam and cleaning is around $150 to $200 without insurance. We can discuss exact pricing when you come in."

    return "I'm happy to help! I can schedule an appointment, answer questions about our services, or provide office information. What do you need?"


def get_session_summary(call_sid: str) -> dict:
    session = _sessions.get(call_sid)
    if not session:
        return {}
    return {
        "intent": session.intent,
        "patient_name": session.patient_name,
        "appointment_type": session.appointment_type,
        "requested_slot": session.requested_slot,
        "booking_confirmed": session.booking_confirmed,
        "transfer_requested": session.transfer_requested,
        "turn_count": session.turn_count,
    }
