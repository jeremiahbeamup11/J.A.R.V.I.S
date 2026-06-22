"""
Jarvis — Milestone 9c
Claude + Ollama dual-brain orchestrator with intent-based routing.

Flow:
  POST /chat {"message": "..."}
    -> router decides LOCAL or CLOUD based on intent keywords
    -> chosen brain processes the request
    -> if chosen brain fails, falls back to the other
    -> returns reply + routing metadata
"""

import logging
import os
import re

import requests as http_requests

from anthropic import Anthropic
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

from tools import TOOL_SCHEMAS, run_tool
from tts import speak
from voice import record_audio, transcribe

load_dotenv()

MODEL = "claude-opus-4-8"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
MAX_TOOL_ROUNDS = 8

SYSTEM_PROMPT = (
    "You are Jarvis, a concise, capable voice assistant running on a Mac. "
    "You have direct control over the Mac through your tools: you can open "
    "apps, set the system volume, control media playback (play, pause, "
    "next, previous), open URLs in the browser, and run macOS Shortcuts. "
    "Always use your tools when the user asks you to do "
    "something you have a tool for — never say you can't do something that "
    "a tool handles. Keep spoken replies short and natural — you will be "
    "read aloud. Do not narrate that you are calling tools."
)

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("jarvis.router")

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
app = FastAPI(title="Jarvis")


class ChatRequest(BaseModel):
    message: str


# --- Router ----------------------------------------------------------------

# TRUST LIST: tools the local brain handles reliably for simple, single-tool
# requests. Demote a tool by removing it from this set — it will route to
# cloud with a logged reason. Baseline: llama3.1:8b 42/42 varied tests.
LOCAL_TRUSTED_TOOLS = {
    "get_time",
    "get_weather",
    "set_volume",
    "media_control",
    "open_url",
    "control_mac_app",
    "run_shortcut",
}

_INTENT_PATTERNS = [
    (re.compile(r"\b(open|launch|start)\b.+\b(app|application|spotify|safari|notes|chrome|finder|music|messages|slack|discord|terminal|calculator)\b", re.I), "control_mac_app"),
    (re.compile(r"\b(volume|sound)\b.*\b(\d+|up|down|mute|max|loud|quiet|halfway)\b", re.I), "set_volume"),
    (re.compile(r"\b(set|turn|change|make|crank).*(volume|sound|loud|quiet)\b", re.I), "set_volume"),
    (re.compile(r"\bcan.t hear\b|\bbarely hear\b|\btoo quiet\b|\btoo loud\b", re.I), "set_volume"),
    (re.compile(r"\b(play|pause|resume|stop|next|skip|previous|prev)\b.*\b(music|song|track|media|playback)?\b", re.I), "media_control"),
    (re.compile(r"\b(open|go to|visit|navigate|pull up)\b.*\b(\.com|\.org|\.net|\.io|\.ai|http|www|url|website|site)\b", re.I), "open_url"),
    (re.compile(r"\bwhat time\b|\bcheck the time\b|\bcurrent time\b|\btell me the time\b", re.I), "get_time"),
    (re.compile(r"\bwhat('s| is) the (date|day)\b|\bwhat day\b", re.I), "get_time"),
    (re.compile(r"\b(weather|temperature|forecast|how hot|how cold)\b", re.I), "get_weather"),
    (re.compile(r"\bwhat.{0,3} it like (outside|out)\b|\bhow.{0,3} it (outside|looking)\b|\blike outside\b", re.I), "get_weather"),
    (re.compile(r"\b(run|execute)\b.*\bshortcut\b", re.I), "run_shortcut"),
]

_MULTI_SIGNAL = re.compile(r"\b(and|then|also|plus)\b", re.I)


def route(message: str) -> tuple[str, str]:
    """Decide LOCAL or CLOUD for a message. Returns (target, reason).

    Trust is per-REQUEST, not blanket per-tool:
    - Simple single-tool requests for trusted tools → LOCAL
    - Multi-tool, complex, or ambiguous requests → CLOUD
    - Untrusted tools → CLOUD
    """
    matched_tools = []
    matched_reason = None
    for pattern, tool_name in _INTENT_PATTERNS:
        if pattern.search(message):
            if tool_name not in matched_tools:
                matched_tools.append(tool_name)
            if matched_reason is None:
                matched_reason = tool_name

    if not matched_tools:
        return "cloud", "no_simple_intent_matched"

    if len(matched_tools) > 1 or _MULTI_SIGNAL.search(message):
        return "cloud", f"multi_tool_or_complex:{'+'.join(matched_tools)}"

    tool = matched_tools[0]
    if tool not in LOCAL_TRUSTED_TOOLS:
        return "cloud", f"tool_not_trusted_locally:{tool}"

    return "local", f"simple_intent:{tool}"


# --- Cloud brain (Claude) -------------------------------------------------

def agent_loop(user_message: str) -> str:
    """Run the Claude tool-calling loop until a final text answer."""
    messages = [{"role": "user", "content": user_message}]

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        if response.stop_reason != "tool_use":
            return "".join(
                block.text for block in response.content if block.type == "text"
            ).strip()

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                try:
                    result = run_tool(block.name, block.input)
                except Exception as exc:
                    result = {"error": f"{type(exc).__name__}: {exc}"}
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(result),
                    }
                )

        messages.append({"role": "user", "content": tool_results})

    return "Stopped: hit the maximum number of tool rounds."


# --- Local brain (Ollama) -------------------------------------------------

def _anthropic_to_ollama_tools(schemas: list[dict]) -> list[dict]:
    """Convert Anthropic tool schemas to Ollama (OpenAI-style) format."""
    return [
        {
            "type": "function",
            "function": {
                "name": s["name"],
                "description": s.get("description", ""),
                "parameters": s["input_schema"],
            },
        }
        for s in schemas
    ]


_OLLAMA_TOOLS = _anthropic_to_ollama_tools(TOOL_SCHEMAS)


def _ollama_chat(messages: list[dict], tools: list[dict] | None = None) -> dict:
    """Send a chat request to the local Ollama endpoint."""
    body: dict = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
    }
    if tools:
        body["tools"] = tools
    resp = http_requests.post(
        f"{OLLAMA_URL}/api/chat",
        json=body,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def agent_loop_local(user_message: str) -> str:
    """Run the local Ollama tool-calling loop until a final text answer."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]

    for _ in range(MAX_TOOL_ROUNDS):
        data = _ollama_chat(messages, tools=_OLLAMA_TOOLS)
        msg = data["message"]

        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            return (msg.get("content") or "").strip()

        messages.append(msg)

        for tc in tool_calls:
            fn = tc["function"]
            tool_name = fn["name"]
            tool_args = fn.get("arguments", {})
            try:
                result = run_tool(tool_name, tool_args)
            except Exception as exc:
                result = {"error": f"{type(exc).__name__}: {exc}"}
            messages.append({"role": "tool", "content": str(result)})

    return "Stopped: hit the maximum number of tool rounds."


# --- Routed entrypoint ----------------------------------------------------

def routed_chat(user_message: str) -> dict:
    """Route a message to the right brain, with fallback on failure."""
    target, reason = route(user_message)
    fallback_used = False
    reply = None

    if target == "local":
        try:
            reply = agent_loop_local(user_message)
            log.info("ROUTE local | reason=%s | fallback=no | msg=%r", reason, user_message[:80])
        except Exception as exc:
            log.warning("ROUTE local FAILED (%s), falling back to cloud | msg=%r", exc, user_message[:80])
            target = "cloud"
            fallback_used = True

    if reply is None:
        try:
            reply = agent_loop(user_message)
            if fallback_used:
                log.info("ROUTE cloud (fallback) | reason=%s | msg=%r", reason, user_message[:80])
            else:
                log.info("ROUTE cloud | reason=%s | fallback=no | msg=%r", reason, user_message[:80])
        except Exception as exc:
            if not fallback_used:
                log.warning("ROUTE cloud FAILED (%s), falling back to local | msg=%r", exc, user_message[:80])
                fallback_used = True
                try:
                    reply = agent_loop_local(user_message)
                    log.info("ROUTE local (fallback) | reason=%s | msg=%r", reason, user_message[:80])
                except Exception as exc2:
                    reply = f"Both brains failed. Cloud: {exc} | Local: {exc2}"
                    log.error("ROUTE both FAILED | msg=%r", user_message[:80])
            else:
                reply = f"Both brains failed: {exc}"
                log.error("ROUTE both FAILED | msg=%r", user_message[:80])

    model_used = OLLAMA_MODEL if (target == "local" and not fallback_used) or (target == "cloud" and fallback_used) else MODEL
    return {
        "reply": reply,
        "routed_to": target if not fallback_used else ("cloud" if target == "local" else "local"),
        "reason": reason,
        "fallback": fallback_used,
        "model": model_used,
    }


# --- Endpoints -------------------------------------------------------------

@app.get("/")
def health():
    return {"status": "jarvis online"}


@app.post("/chat")
def chat(req: ChatRequest):
    return routed_chat(req.message)


@app.post("/chat_cloud")
def chat_cloud(req: ChatRequest):
    """Direct cloud path — bypasses the router."""
    reply = agent_loop(req.message)
    return {"reply": reply, "model": MODEL}


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
    """Record from the mic, transcribe, route, and speak the reply."""
    audio = record_audio()
    text = transcribe(audio)
    if not text:
        speak("I didn't catch that.")
        return {"transcript": "", "reply": "I didn't catch that."}
    result = routed_chat(text)
    speak(result["reply"])
    result["transcript"] = text
    return result