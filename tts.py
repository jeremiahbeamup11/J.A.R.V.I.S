"""
Voice output for Jarvis — ElevenLabs text-to-speech.

Converts text to speech and plays it through the Mac speakers using afplay.
"""

import os
import subprocess
import tempfile

from elevenlabs import ElevenLabs

VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "onwK4e9ZLuTAKqWW03F9")
MODEL_ID = "eleven_turbo_v2_5"

_client = None


def _get_client() -> ElevenLabs:
    global _client
    if _client is None:
        _client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
    return _client


def speak(text: str) -> None:
    """Convert text to speech and play it through the speakers."""
    if not text.strip():
        return

    client = _get_client()
    audio = client.text_to_speech.convert(
        text=text,
        voice_id=VOICE_ID,
        model_id=MODEL_ID,
    )
    data = b"".join(audio)

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        f.write(data)
        path = f.name

    try:
        subprocess.run(["afplay", path], timeout=30)
    except subprocess.TimeoutExpired:
        pass
    finally:
        os.unlink(path)
