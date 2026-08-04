"""
Jarvis brains + router.

Claude = primary brain (tool-calling loop).
Ollama = local first-responder for simple trusted commands.
Grok Build = engineering body: pure engineering intents go straight to
Grok (no Claude middleman); Claude can still call run_grok_build as a tool
for mixed requests.
"""

from __future__ import annotations

import logging
import os
import re

import requests as http_requests
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

from tools import TOOL_SCHEMAS, run_tool
from tools.grok_build import (
    default_cwd,
    extract_path_from_text,
    resolve_project_path,
    run_grok_build,
)
from memory import (
    anthropic_history_messages,
    build_system_appendix,
    load_long_term,
    ollama_history_messages,
    record_turn,
)

MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
MAX_TOOL_ROUNDS = 8

SYSTEM_PROMPT = (
    "You are Jarvis, a concise, capable engineering assistant on a Mac. "
    "You do not only answer — when the task benefits from it, you USE the "
    "Mac and produce tangible work products.\n\n"
    "Mac control: open apps, set volume, media, open URLs, run Shortcuts, "
    "open_file (workshop paths), reveal_in_finder.\n\n"
    "Workshop / design (important): When the user asks how a physical system "
    "works, how to design something, or wants a model they can see/touch "
    "(example: lunar hopper thermal system), do a multi-step workflow:\n"
    "  1) Reason briefly about the real engineering requirements.\n"
    "  2) build_3d_model — assemble a clear schematic 3D from primitives "
    "(box/cylinder/sphere/cone) that represents the system (not photoreal; "
    "readable labeled layout via distinct part sizes/positions).\n"
    "  3) write_design_brief into the same project_dir explaining the design.\n"
    "  4) open_file on the STL (prefer app_name eDrawings; fallback Preview) "
    "and/or reveal_in_finder so the model is on screen.\n"
    "  5) In your spoken/text reply, explain the system while referring to "
    "the model you just opened (e.g. the tall cylinder is the propellant "
    "tank, the flat plate is the radiator).\n"
    "Always do steps 2–4 for design/how-do-we-build/physical-system questions "
    "unless the user only wants a pure verbal answer.\n\n"
    "Software engineering: use run_grok_build for implement/fix/refactor/"
    "scaffold/tests on allowlisted code projects.\n\n"
    "Memory: You have short-term session history in the messages, and "
    "long-term memory tools (remember, recall, forget, set_active_project, "
    "set_preference). Persist lasting facts and preferences with remember. "
    "Never store secrets. Use prior conversation context naturally — do not "
    "pretend amnesia about what was just said.\n\n"
    "Always use tools when they apply — never claim you cannot do something "
    "a tool handles. Do not narrate that you are calling tools.\n\n"
    "Reply length: short for commands; full explanations for design/teach. "
    "After Grok or a workshop build, summarize in plain language — no raw logs."
)

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("jarvis.router")

client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


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

# Pure engineering → shoot straight to Grok Build (no Claude middleman).
# Require engineering verbs/phrases; path or default cwd resolved later.
_ENGINEERING_PATTERNS = [
    re.compile(
        r"\b(implement|refactor|scaffold|debug|migrate)\b",
        re.I,
    ),
    re.compile(
        r"\b(fix|repair)\b.+\b(bug|error|crash|test|build|type.?error|compile)\b",
        re.I,
    ),
    re.compile(
        r"\b(add|create|write|build)\b.+\b("
        r"endpoint|api|function|class|module|component|feature|"
        r"test|tests|unit test|integration test|pr|pull request|"
        r"fastapi|flask|django|react|next\.?js|express|typescript|"
        r"python (?:file|module|script)|dockerfile|ci|github action"
        r")\b",
        re.I,
    ),
    re.compile(
        r"\b(code review|review (?:this|the|my) (?:code|pr|pull request|diff))\b",
        re.I,
    ),
    re.compile(
        r"\b(run grok|use grok|grok build|have grok)\b",
        re.I,
    ),
    re.compile(
        r"\b(write|add|generate)\b.+\b(tests?|specs?)\b.+\b(for|to|in)\b",
        re.I,
    ),
]

# Device / assistant commands should never steal engineering routing.
_NOT_ENGINEERING = re.compile(
    r"\b(volume|spotify|weather|what time|open safari|open notes|"
    r"play music|pause|shortcut)\b",
    re.I,
)


def is_pure_engineering(message: str) -> bool:
    """True when the message is software-engineering work for Grok Build."""
    if _NOT_ENGINEERING.search(message) and not any(
        p.search(message) for p in _ENGINEERING_PATTERNS
    ):
        return False
    return any(p.search(message) for p in _ENGINEERING_PATTERNS)


def route(message: str) -> tuple[str, str]:
    """Decide LOCAL, GROK, or CLOUD for a message. Returns (target, reason).

    Priority:
      1. Pure engineering intent → GROK (straight to Grok Build)
      2. Simple single trusted local tool → LOCAL
      3. Everything else → CLOUD (Claude)
    """
    if is_pure_engineering(message):
        return "grok", "pure_engineering_intent"

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

def agent_loop(user_message: str, *, use_memory: bool = True) -> tuple[str, str]:
    """Run the Claude tool-calling loop. Returns (reply_text, stop_reason)."""
    system = SYSTEM_PROMPT + (build_system_appendix() if use_memory else "")
    messages: list[dict] = []
    if use_memory:
        messages.extend(anthropic_history_messages())
    messages.append({"role": "user", "content": user_message})

    for _ in range(MAX_TOOL_ROUNDS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=system,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        if response.stop_reason != "tool_use":
            text = "".join(
                block.text for block in response.content if block.type == "text"
            ).strip()
            if use_memory:
                record_turn(
                    user_message,
                    text,
                    {"routed_to": "cloud", "model": MODEL},
                )
            return text, response.stop_reason

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                try:
                    result = run_tool(block.name, block.input)
                except Exception as exc:
                    result = {"error": f"{type(exc).__name__}: {exc}"}
                # Keep active project in sync when Grok/workshop touch a path
                if use_memory and block.name in ("run_grok_build", "build_3d_model"):
                    _maybe_capture_project(block.name, block.input, result)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": str(result),
                    }
                )

        messages.append({"role": "user", "content": tool_results})

    text = "Stopped: hit the maximum number of tool rounds."
    if use_memory:
        record_turn(user_message, text, {"routed_to": "cloud", "model": MODEL})
    return text, "max_rounds"


def _maybe_capture_project(tool_name: str, tool_input: dict, result: dict) -> None:
    """Best-effort: set active project from successful tool outputs."""
    try:
        from memory import set_active_project

        if not isinstance(result, dict) or not result.get("ok"):
            return
        path = None
        if tool_name == "run_grok_build":
            path = result.get("project_path") or (tool_input or {}).get("project_path")
        elif tool_name == "build_3d_model":
            path = result.get("project_dir")
        if path:
            set_active_project(str(path))
    except Exception:
        pass


# --- Local brain (Ollama) -------------------------------------------------

def _anthropic_to_ollama_tools(schemas: list[dict]) -> list[dict]:
    """Convert Anthropic tool schemas to Ollama (OpenAI-style) format."""
    # Local brain: only simple trusted tools (no Grok, no workshop multi-step).
    _local_skip = {
        "run_grok_build",
        "build_3d_model",
        "write_design_brief",
        "open_file",
        "reveal_in_finder",
        # Memory tools stay on cloud (better judgment about what to store)
        "remember",
        "recall",
        "forget",
        "set_active_project",
        "set_preference",
    }
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
        if s["name"] not in _local_skip
    ]


_OLLAMA_TOOLS = _anthropic_to_ollama_tools(TOOL_SCHEMAS)


def _ollama_chat(messages: list[dict], tools: list[dict] | None = None) -> dict:
    """Send a chat request to the local Ollama endpoint."""
    body: dict = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"num_predict": 4096},
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


def agent_loop_local(user_message: str, *, use_memory: bool = True) -> str:
    """Run the local Ollama tool-calling loop until a final text answer."""
    system = SYSTEM_PROMPT
    if use_memory:
        # Compact: prefs + active project only (keep local prompts small)
        lt = load_long_term()
        bits = []
        if lt.get("active_project"):
            bits.append(f"Active project: {lt['active_project']}")
        prefs = lt.get("preferences") or {}
        if prefs:
            bits.append("Preferences: " + ", ".join(f"{k}={v}" for k, v in list(prefs.items())[:8]))
        if bits:
            system = system + "\n\n## Context\n" + "\n".join(bits)

    messages: list[dict] = [{"role": "system", "content": system}]
    if use_memory:
        messages.extend(ollama_history_messages(max_pairs=3))
    messages.append({"role": "user", "content": user_message})

    for _ in range(MAX_TOOL_ROUNDS):
        data = _ollama_chat(messages, tools=_OLLAMA_TOOLS)
        msg = data["message"]

        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            text = (msg.get("content") or "").strip()
            if use_memory:
                record_turn(
                    user_message,
                    text,
                    {"routed_to": "local", "model": OLLAMA_MODEL},
                )
            return text

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

    text = "Stopped: hit the maximum number of tool rounds."
    if use_memory:
        record_turn(user_message, text, {"routed_to": "local", "model": OLLAMA_MODEL})
    return text


# --- Grok Build direct path -----------------------------------------------

def _resolve_engineering_cwd(user_message: str) -> tuple[str | None, str | None]:
    """Pick project_path for a direct Grok route. Returns (path, error)."""
    extracted = extract_path_from_text(user_message)
    active = None
    try:
        ap = load_long_term().get("active_project")
        if ap and ("/" in str(ap) or str(ap).startswith("~")):
            active = str(ap)
    except Exception:
        pass
    candidate = extracted or active or (default_cwd() or None)
    path, err = resolve_project_path(candidate)
    if err:
        return None, err
    return str(path), None


def agent_loop_grok(user_message: str, mode: str = "build") -> tuple[str, dict]:
    """Run Grok Build headlessly. Returns (spoken_summary, raw_result)."""
    project_path, err = _resolve_engineering_cwd(user_message)
    if err:
        # No valid cwd — caller should fall back to Claude.
        return "", {"ok": False, "error": err, "needs_cloud": True}

    result = run_grok_build(
        task=user_message,
        project_path=project_path,
        mode=mode,
    )

    if not result.get("ok"):
        err_msg = result.get("error") or "Grok Build failed"
        text = result.get("text") or ""
        summary = f"Grok Build hit a problem: {err_msg}"
        if text:
            summary += f" Details: {text[:500]}"
        return summary, result

    body = (result.get("text") or "").strip()
    if body:
        # Prefer Grok's own summary; keep it voice-friendly length.
        summary = body if len(body) <= 1200 else body[:1200] + "…"
    else:
        summary = f"Grok Build finished on {result.get('project_path')}."
    return summary, result


# --- Routed entrypoint ----------------------------------------------------

def routed_chat(user_message: str) -> dict:
    """Route a message to the right brain/body, with fallback on failure."""
    target, reason = route(user_message)
    fallback_used = False
    reply = None
    stop_reason = None
    model_used = None
    grok_meta = None

    # --- Direct Grok Build for pure engineering ---
    if target == "grok":
        try:
            reply, grok_meta = agent_loop_grok(user_message, mode="build")
            if grok_meta.get("needs_cloud"):
                log.info(
                    "ROUTE grok → cloud (path resolve failed: %s) | msg=%r",
                    grok_meta.get("error"),
                    user_message[:80],
                )
                target = "cloud"
                reason = f"grok_path_unresolved:{grok_meta.get('error', '')[:80]}"
                reply = None
            else:
                stop_reason = "end_turn" if grok_meta.get("ok") else "error"
                model_used = "grok-build"
                log.info(
                    "ROUTE grok | reason=%s | ok=%s | cwd=%s | msg=%r",
                    reason,
                    grok_meta.get("ok"),
                    grok_meta.get("project_path"),
                    user_message[:80],
                )
        except Exception as exc:
            log.warning(
                "ROUTE grok FAILED (%s), falling back to cloud | msg=%r",
                exc,
                user_message[:80],
            )
            target = "cloud"
            fallback_used = True
            reason = f"grok_failed:{exc}"
            reply = None

    if target == "local" and reply is None:
        try:
            reply = agent_loop_local(user_message)
            stop_reason = "stop"
            model_used = OLLAMA_MODEL
            log.info(
                "ROUTE local | reason=%s | fallback=no | msg=%r",
                reason,
                user_message[:80],
            )
        except Exception as exc:
            log.warning(
                "ROUTE local FAILED (%s), falling back to cloud | msg=%r",
                exc,
                user_message[:80],
            )
            target = "cloud"
            fallback_used = True

    if reply is None:
        try:
            reply, stop_reason = agent_loop(user_message)
            model_used = MODEL
            if fallback_used:
                log.info(
                    "ROUTE cloud (fallback) | reason=%s | msg=%r",
                    reason,
                    user_message[:80],
                )
            else:
                log.info(
                    "ROUTE cloud | reason=%s | fallback=no | msg=%r",
                    reason,
                    user_message[:80],
                )
        except Exception as exc:
            if not fallback_used and target != "local":
                log.warning(
                    "ROUTE cloud FAILED (%s), falling back to local | msg=%r",
                    exc,
                    user_message[:80],
                )
                fallback_used = True
                try:
                    reply = agent_loop_local(user_message)
                    stop_reason = "stop"
                    model_used = OLLAMA_MODEL
                    log.info(
                        "ROUTE local (fallback) | reason=%s | msg=%r",
                        reason,
                        user_message[:80],
                    )
                except Exception as exc2:
                    reply = f"Both brains failed. Cloud: {exc} | Local: {exc2}"
                    log.error("ROUTE both FAILED | msg=%r", user_message[:80])
            else:
                reply = f"Brain failed: {exc}"
                log.error("ROUTE FAILED | msg=%r", user_message[:80])

    routed_to = target
    if fallback_used:
        # actual brain that answered
        if model_used == MODEL:
            routed_to = "cloud"
        elif model_used == OLLAMA_MODEL:
            routed_to = "local"
        elif model_used == "grok-build":
            routed_to = "grok"

    # Grok path does not go through agent_loop — record session turn here.
    # Cloud/local already record inside their loops.
    if reply is not None and routed_to == "grok":
        record_turn(
            user_message,
            reply,
            {"routed_to": "grok", "model": model_used, "reason": reason},
        )
        if grok_meta and grok_meta.get("ok") and grok_meta.get("project_path"):
            try:
                from memory import set_active_project

                set_active_project(str(grok_meta["project_path"]))
            except Exception:
                pass

    out = {
        "reply": reply,
        "routed_to": routed_to,
        "reason": reason,
        "fallback": fallback_used,
        "model": model_used,
        "stop_reason": stop_reason,
    }
    if grok_meta and not grok_meta.get("needs_cloud"):
        out["grok"] = {
            "ok": grok_meta.get("ok"),
            "project_path": grok_meta.get("project_path"),
            "mode": grok_meta.get("mode"),
            "session_id": grok_meta.get("session_id"),
            "num_turns": grok_meta.get("num_turns"),
        }
    try:
        from memory import status as memory_status

        ms = memory_status()
        out["memory"] = {
            "session_id": ms.get("session_id"),
            "session_turns": ms.get("session_turns"),
            "long_term_notes": ms.get("long_term_notes"),
            "active_project": ms.get("active_project"),
        }
    except Exception:
        pass
    return out
