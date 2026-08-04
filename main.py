"""
Jarvis — FastAPI orchestrator.

Brains + routing live in agent.py. This module exposes HTTP endpoints,
including the iPhone remote UI at /phone.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

# Load .env before agent/tools read config.
load_dotenv()

import requests as http_requests
from fastapi import Depends, FastAPI, File, Form, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from agent import MODEL, OLLAMA_MODEL, agent_loop, agent_loop_local, routed_chat
from phone_api import (
    audio_to_wav,
    auth_required,
    is_hotspot_like,
    lan_ips,
    preferred_lan_hint,
    require_phone_auth,
    save_upload,
)
from tts import speak
from voice import record_audio, transcribe

app = FastAPI(title="Jarvis")

STATIC_DIR = Path(__file__).resolve().parent / "static"
PHONE_PORT = int(os.environ.get("JARVIS_PORT", "8010"))


class ChatRequest(BaseModel):
    message: str


class PhoneChatRequest(BaseModel):
    message: str
    speak: bool = True


def _maybe_speak(text: str, do_speak: bool) -> bool:
    if not do_speak or not (text or "").strip():
        return False
    try:
        speak(text)
        return True
    except Exception:
        return False


@app.get("/")
def health():
    return {
        "status": "jarvis online",
        "phone": "/phone",
        "hotspot_like": is_hotspot_like(),
        "ips": lan_ips(),
        "hint": preferred_lan_hint(PHONE_PORT),
    }


@app.post("/chat")
def chat(req: ChatRequest):
    return routed_chat(req.message)


@app.post("/chat_cloud")
def chat_cloud(req: ChatRequest):
    """Direct cloud path — bypasses the router."""
    reply, stop_reason = agent_loop(req.message)
    return {"reply": reply, "model": MODEL, "stop_reason": stop_reason}


@app.post("/chat_local")
def chat_local(req: ChatRequest):
    """Direct local path — bypasses the router."""
    try:
        reply = agent_loop_local(req.message)
    except http_requests.exceptions.ConnectionError:
        reply = "Local brain offline — is Ollama running?"
    except Exception as exc:
        reply = f"Local brain error: {type(exc).__name__}: {exc}"
    return {"reply": reply, "model": OLLAMA_MODEL}


@app.post("/voice")
def voice():
    """Record from the Mac mic, transcribe, route, and speak the reply."""
    audio = record_audio()
    text = transcribe(audio)
    if not text:
        speak("I didn't catch that.")
        return {"transcript": "", "reply": "I didn't catch that."}
    result = routed_chat(text)
    speak(result["reply"])
    result["transcript"] = text
    return result


# --- Phone remote (iPhone Safari / PWA) ------------------------------------

@app.get("/phone")
def phone_ui():
    """Mobile control surface — open this URL on the iPhone."""
    page = STATIC_DIR / "phone.html"
    if not page.exists():
        return {"error": "static/phone.html missing"}
    return FileResponse(page, media_type="text/html")


@app.get("/phone/api/status")
def phone_status(_: None = Depends(require_phone_auth)):
    return {
        "status": "online",
        "auth_required": auth_required(),
        "hotspot_like": is_hotspot_like(),
        "ips": lan_ips(),
        "lan_hint": preferred_lan_hint(PHONE_PORT),
    }


@app.post("/phone/api/chat")
def phone_chat(req: PhoneChatRequest, _: None = Depends(require_phone_auth)):
    result = routed_chat(req.message)
    spoken = _maybe_speak(result.get("reply") or "", req.speak)
    result["spoken"] = spoken
    return result


@app.post("/phone/api/chat_cloud")
def phone_chat_cloud(req: PhoneChatRequest, _: None = Depends(require_phone_auth)):
    reply, stop_reason = agent_loop(req.message)
    spoken = _maybe_speak(reply, req.speak)
    return {
        "reply": reply,
        "model": MODEL,
        "stop_reason": stop_reason,
        "routed_to": "cloud",
        "spoken": spoken,
    }


@app.post("/phone/api/voice")
async def phone_voice(
    audio: UploadFile = File(...),
    speak: str = Form("1"),
    cloud_only: str = Form("0"),
    _: None = Depends(require_phone_auth),
):
    """Accept a phone mic clip, transcribe on the Mac, route, optional TTS."""
    do_speak = speak.strip() not in ("0", "false", "False", "")
    force_cloud = cloud_only.strip() in ("1", "true", "True")

    suffix = Path(audio.filename or "clip.webm").suffix or ".webm"
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / f"clip{suffix}"
        await save_upload(audio, raw)
        try:
            wav_path = audio_to_wav(raw)
        except Exception as exc:
            return {
                "ok": False,
                "error": f"Could not convert audio: {exc}",
                "transcript": "",
                "reply": "",
            }

        # faster-whisper accepts a file path (wav after ffmpeg convert)
        from voice import _get_model

        model = _get_model()
        segments, _ = model.transcribe(str(wav_path), beam_size=3, language="en")
        text = " ".join(seg.text.strip() for seg in segments).strip()

    if not text:
        reply = "I didn't catch that."
        spoken = _maybe_speak(reply, do_speak)
        return {
            "ok": True,
            "transcript": "",
            "reply": reply,
            "spoken": spoken,
        }

    if force_cloud:
        reply, stop_reason = agent_loop(text)
        result = {
            "reply": reply,
            "model": MODEL,
            "stop_reason": stop_reason,
            "routed_to": "cloud",
            "reason": "phone_cloud_only",
            "fallback": False,
        }
    else:
        result = routed_chat(text)

    spoken = _maybe_speak(result.get("reply") or "", do_speak)
    result["transcript"] = text
    result["spoken"] = spoken
    result["ok"] = True
    return result
