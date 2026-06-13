import os
import uuid
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

import agent
import call_log
import tts
from knowledge_base import get_available_slots

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
OFFICE_PHONE = os.getenv("OFFICE_PHONE", "+14105550100")
GATHER_TIMEOUT = 5
SPEECH_TIMEOUT = "auto"
AUDIO_CACHE_DIR = Path("audio_cache")

GREETING_TEXT = agent.get_greeting()


@asynccontextmanager
async def lifespan(app: FastAPI):
    call_log.init_db()
    logger.info("Database initialized")
    AUDIO_CACHE_DIR.mkdir(exist_ok=True)
    # Pre-warm greeting audio if ElevenLabs is configured
    if os.getenv("ELEVENLABS_API_KEY"):
        try:
            import httpx
            audio_url = await tts.generate_elevenlabs_audio(GREETING_TEXT, BASE_URL)
            if audio_url:
                logger.info("Greeting audio pre-generated: %s", audio_url)
        except Exception as e:
            logger.warning("Could not pre-generate greeting audio: %s", e)
    yield


app = FastAPI(
    title="DentalVoice AI",
    description="AI Voice Agent for Smile Care Dental",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="static"), name="static")


# ---------------------------------------------------------------------------
# TwiML helpers
# ---------------------------------------------------------------------------

def _xml_response(content: str) -> HTMLResponse:
    return HTMLResponse(content=content, media_type="application/xml")


def _build_gather_twiml(say_or_play: str, action: str, hints: str = "") -> str:
    hints_attr = f' hints="{hints}"' if hints else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Gather input="speech dtmf" timeout="{GATHER_TIMEOUT}" speechTimeout="{SPEECH_TIMEOUT}" action="{action}" method="POST" partialResultCallback="{action}/partial"{hints_attr}>
    {say_or_play}
  </Gather>
  <Redirect method="POST">{action}</Redirect>
</Response>"""


def _build_transfer_twiml(message: str, audio_url: str | None) -> str:
    say_or_play = tts.build_twiml_say(message, audio_url)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  {say_or_play}
  <Say voice="{tts.TWILIO_TTS_VOICE}">Please hold while I connect you.</Say>
  <Dial timeout="30" callerId="{OFFICE_PHONE}">
    <Number>{OFFICE_PHONE}</Number>
  </Dial>
  <Say voice="{tts.TWILIO_TTS_VOICE}">I'm sorry, our team is unavailable right now. Please call us back during office hours. Goodbye!</Say>
</Response>"""


def _build_hangup_twiml(message: str, audio_url: str | None) -> str:
    say_or_play = tts.build_twiml_say(message, audio_url)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  {say_or_play}
  <Hangup/>
</Response>"""


# ---------------------------------------------------------------------------
# Twilio webhook routes
# ---------------------------------------------------------------------------

@app.post("/webhook/voice")
async def handle_inbound_call(
    CallSid: str = Form(...),
    From: str = Form(default="unknown"),
    To: str = Form(default=""),
):
    """Entry point for all inbound Twilio calls."""
    logger.info("Inbound call: CallSid=%s From=%s", CallSid, From)

    call_log.create_call_record(call_sid=CallSid, caller_number=From)

    audio_url = await tts.generate_elevenlabs_audio(GREETING_TEXT, BASE_URL)
    say_or_play = tts.build_twiml_say(GREETING_TEXT, audio_url)

    hints = "book appointment, office hours, insurance, location, speak to someone, emergency"
    twiml = _build_gather_twiml(
        say_or_play=say_or_play,
        action=f"{BASE_URL}/webhook/gather",
        hints=hints,
    )

    call_log.log_turn(call_sid=CallSid, role="assistant", content=GREETING_TEXT)
    return _xml_response(twiml)


@app.post("/webhook/gather")
async def handle_gather(
    CallSid: str = Form(...),
    From: str = Form(default="unknown"),
    SpeechResult: str = Form(default=""),
    Digits: str = Form(default=""),
    CallStatus: str = Form(default="in-progress"),
):
    """Handles gathered speech or DTMF from the caller."""
    speech_input = SpeechResult.strip() or Digits.strip()

    logger.info("Gather: CallSid=%s Input=%r Status=%s", CallSid, speech_input, CallStatus)

    # Call ended mid-gather
    if CallStatus in ("completed", "busy", "failed", "no-answer", "canceled"):
        _finalize_call(CallSid, outcome="abandoned")
        return _xml_response("<?xml version='1.0'?><Response/>")

    # No input — re-prompt once
    if not speech_input:
        no_input_text = "I didn't catch that. Could you please repeat that?"
        audio_url = await tts.generate_elevenlabs_audio(no_input_text, BASE_URL)
        say_or_play = tts.build_twiml_say(no_input_text, audio_url)
        twiml = _build_gather_twiml(
            say_or_play=say_or_play,
            action=f"{BASE_URL}/webhook/gather",
        )
        return _xml_response(twiml)

    call_log.log_turn(call_sid=CallSid, role="user", content=speech_input)

    response_text, should_transfer, booking_confirmed = await agent.process_speech(
        call_sid=CallSid,
        speech_input=speech_input,
    )

    logger.info("Agent response: %r transfer=%s booking=%s", response_text, should_transfer, booking_confirmed)

    summary = agent.get_session_summary(CallSid)
    call_log.update_call_record(
        call_sid=CallSid,
        intent=summary.get("intent"),
        appointment_booked=summary.get("requested_slot") if booking_confirmed else None,
        transferred_to_human=should_transfer,
    )

    call_log.log_turn(call_sid=CallSid, role="assistant", content=response_text)

    audio_url = await tts.generate_elevenlabs_audio(response_text, BASE_URL)

    if should_transfer:
        _finalize_call(CallSid, outcome="transferred")
        twiml = _build_transfer_twiml(response_text, audio_url)
        return _xml_response(twiml)

    if booking_confirmed:
        farewell = f"{response_text} We look forward to seeing you. Goodbye!"
        farewell_audio = await tts.generate_elevenlabs_audio(farewell, BASE_URL)
        _finalize_call(CallSid, outcome="booking_confirmed")
        twiml = _build_hangup_twiml(farewell, farewell_audio)
        return _xml_response(twiml)

    say_or_play = tts.build_twiml_say(response_text, audio_url)
    hints = "book appointment, office hours, insurance, location, speak to someone, emergency, yes, no"
    twiml = _build_gather_twiml(
        say_or_play=say_or_play,
        action=f"{BASE_URL}/webhook/gather",
        hints=hints,
    )
    return _xml_response(twiml)


@app.post("/webhook/gather/partial")
async def handle_partial_result(
    CallSid: str = Form(...),
    UnstableSpeechResult: str = Form(default=""),
):
    """Receive partial speech results (logging only, no response needed)."""
    if UnstableSpeechResult:
        logger.debug("Partial speech [%s]: %r", CallSid, UnstableSpeechResult)
    return _xml_response("<?xml version='1.0'?><Response/>")


@app.post("/webhook/status")
async def call_status_callback(
    CallSid: str = Form(...),
    CallStatus: str = Form(default=""),
    CallDuration: str = Form(default="0"),
):
    """Twilio status callback — fired when call ends."""
    logger.info("Call status: CallSid=%s Status=%s Duration=%ss", CallSid, CallStatus, CallDuration)
    if CallStatus in ("completed", "busy", "failed", "no-answer", "canceled"):
        summary = agent.get_session_summary(CallSid)
        outcome = summary.get("outcome") or CallStatus
        call_log.update_call_record(
            call_sid=CallSid,
            outcome=outcome,
            conversation_summary=str(summary),
        )
        agent.clear_session(CallSid)
    return JSONResponse({"received": True})


# ---------------------------------------------------------------------------
# Audio file serving (ElevenLabs cache)
# ---------------------------------------------------------------------------

@app.get("/audio/{filename}")
async def serve_audio(filename: str):
    """Serve cached ElevenLabs audio files."""
    # Prevent path traversal
    safe_name = Path(filename).name
    audio_path = Path("audio_cache") / safe_name
    if not audio_path.exists() or audio_path.suffix != ".mp3":
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(audio_path, media_type="audio/mpeg")


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.get("/logs")
async def get_logs():
    """Return all call log records."""
    logs = call_log.get_all_logs()
    return JSONResponse({"total": len(logs), "calls": logs})


@app.get("/logs/{call_sid}")
async def get_call_transcript(call_sid: str):
    """Return full conversation transcript for a specific call."""
    turns = call_log.get_conversation(call_sid)
    if not turns:
        return JSONResponse({"error": "call not found"}, status_code=404)
    return JSONResponse({"call_sid": call_sid, "turns": turns, "total_turns": len(turns)})


@app.get("/health")
async def health_check():
    return JSONResponse({
        "status": "ok",
        "service": "DentalVoice AI",
        "practice": "Smile Care Dental",
        "available_slots": get_available_slots(),
        "integrations": {
            "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
            "elevenlabs": bool(os.getenv("ELEVENLABS_API_KEY")),
            "twilio": bool(os.getenv("TWILIO_ACCOUNT_SID")),
        },
    })


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


@app.post("/api/chat")
async def web_chat(body: ChatRequest):
    """Web demo chat — lets visitors test Alex AI without a phone call."""
    session_id = body.session_id or f"web-{uuid.uuid4().hex[:8]}"
    call_log.create_call_record(call_sid=session_id, caller_number="web-demo")
    call_log.log_turn(call_sid=session_id, role="user", content=body.message)

    response_text, should_transfer, booking_confirmed = await agent.process_speech(
        call_sid=session_id,
        speech_input=body.message,
    )

    call_log.log_turn(call_sid=session_id, role="assistant", content=response_text)
    summary = agent.get_session_summary(session_id)

    return JSONResponse({
        "session_id": session_id,
        "response": response_text,
        "booking_confirmed": booking_confirmed,
        "should_transfer": should_transfer,
        "intent": summary.get("intent"),
    })


@app.get("/")
async def root():
    return FileResponse("static/index.html")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
