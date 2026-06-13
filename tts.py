import os
import hashlib
import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "ZoiZ8fuDWInAcwPXaVeq")  # Josh — warm, smooth and steady
AUDIO_CACHE_DIR = Path("audio_cache")

TWILIO_TTS_VOICE = "Polly.Joanna"  # AWS Polly via Twilio — warm, professional


def _cache_path(text: str) -> Path:
    digest = hashlib.md5(text.encode()).hexdigest()
    return AUDIO_CACHE_DIR / f"{digest}.mp3"


async def generate_elevenlabs_audio(text: str, base_url: str) -> str | None:
    """Generate audio via ElevenLabs and return a public URL to the cached file."""
    if not ELEVENLABS_API_KEY:
        return None

    AUDIO_CACHE_DIR.mkdir(exist_ok=True)
    cache_file = _cache_path(text)

    if not cache_file.exists():
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
                    headers={
                        "xi-api-key": ELEVENLABS_API_KEY,
                        "Content-Type": "application/json",
                    },
                    json={
                        "text": text,
                        "model_id": "eleven_turbo_v2",
                        "voice_settings": {
                            "stability": 0.5,
                            "similarity_boost": 0.75,
                            "style": 0.3,
                            "use_speaker_boost": True,
                        },
                    },
                )
                if response.status_code != 200:
                    logger.warning("ElevenLabs error %s: %s", response.status_code, response.text)
                    return None
                cache_file.write_bytes(response.content)
        except Exception as exc:
            logger.warning("ElevenLabs request failed: %s", exc)
            return None

    return f"{base_url}/audio/{cache_file.name}"


def build_twiml_say(text: str, audio_url: str | None = None) -> str:
    """Return either a <Play> tag (ElevenLabs) or <Say> tag (Twilio TTS)."""
    if audio_url:
        return f'<Play>{audio_url}</Play>'
    return f'<Say voice="{TWILIO_TTS_VOICE}">{_escape_xml(text)}</Say>'


def _escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
    )
