"""
Tool registry for Jarvis.

Each tool is a plain Python function plus a JSON schema describing it to
Claude. To add a tool: write the function, add its schema to TOOL_SCHEMAS,
and register it in TOOL_FUNCTIONS. Nothing else changes.
"""

import os
from datetime import datetime

import requests

from tools.grok_build import (  # noqa: F401 — re-export
    clear_grok_session,
    list_grok_sessions,
    run_grok_build,
)
from tools.workshop import (  # noqa: F401 — re-export
    build_3d_model,
    open_file,
    reveal_in_finder,
    workshop_engines,
    write_design_brief,
)
from tools.workshop_templates import list_templates  # noqa: F401
from tools.workshop_grok import design_3d_with_grok  # noqa: F401
from memory import (  # noqa: F401 — re-export
    forget,
    recall,
    remember,
    set_active_project,
    set_preference,
)

MAC_AGENT_URL = os.environ.get("MAC_AGENT_URL", "http://localhost:8765")


def _normalize_tags(tags) -> list[str] | None:
    if tags is None:
        return None
    if isinstance(tags, str):
        return [t.strip() for t in tags.split(",") if t.strip()]
    if isinstance(tags, list):
        return [str(t).strip() for t in tags if str(t).strip()]
    return None


def remember_fact(content: str, tags=None, category: str = "note") -> dict:
    """Tool wrapper for durable memory notes."""
    return remember(content=content, tags=_normalize_tags(tags), category=category or "note")


def get_time() -> dict:
    """Return the current local date and time."""
    now = datetime.now()
    return {
        "time": now.strftime("%I:%M %p"),
        "date": now.strftime("%A, %B %d, %Y"),
        "iso": now.isoformat(),
    }


def get_weather(city: str) -> dict:
    """Fetch current weather for a city using wttr.in (no API key needed)."""
    resp = requests.get(
        f"https://wttr.in/{city}",
        params={"format": "j1"},
        headers={"User-Agent": "Jarvis/1.0"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    current = data["current_condition"][0]
    return {
        "city": city,
        "temp_f": current["temp_F"],
        "temp_c": current["temp_C"],
        "feels_like_f": current["FeelsLikeF"],
        "humidity": current["humidity"],
        "description": current["weatherDesc"][0]["value"],
        "wind_mph": current["windspeedMiles"],
    }


def control_mac_app(app_name: str) -> dict:
    """Open an application on the MacBook via the Mac control agent."""
    try:
        resp = requests.post(
            f"{MAC_AGENT_URL}/open_app",
            json={"app_name": app_name},
            timeout=12,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": "Mac agent offline — is the Mac awake and the agent running?"}
    except requests.exceptions.RequestException as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def set_volume(level: int) -> dict:
    """Set the Mac's output volume (0-100) via the Mac control agent."""
    level = max(0, min(100, level))
    try:
        resp = requests.post(
            f"{MAC_AGENT_URL}/set_volume",
            json={"level": level},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": "Mac agent offline — is the Mac awake and the agent running?"}
    except requests.exceptions.RequestException as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def media_control(action: str) -> dict:
    """Send a media key event (play/pause/next/previous) via the Mac agent."""
    try:
        resp = requests.post(
            f"{MAC_AGENT_URL}/media_control",
            json={"action": action},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": "Mac agent offline — is the Mac awake and the agent running?"}
    except requests.exceptions.RequestException as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def open_url(url: str) -> dict:
    """Open a URL in the default browser via the Mac control agent."""
    try:
        resp = requests.post(
            f"{MAC_AGENT_URL}/open_url",
            json={"url": url},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": "Mac agent offline — is the Mac awake and the agent running?"}
    except requests.exceptions.RequestException as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def run_shortcut(name: str) -> dict:
    """Run a named macOS Shortcut via the Mac control agent."""
    try:
        resp = requests.post(
            f"{MAC_AGENT_URL}/run_shortcut",
            json={"name": name},
            timeout=35,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": "Mac agent offline — is the Mac awake and the agent running?"}
    except requests.exceptions.RequestException as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


# --- Claude-facing schemas -------------------------------------------------

TOOL_SCHEMAS = [
    {
        "name": "get_time",
        "description": "Return the current local date and time.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_weather",
        "description": (
            "Get the current weather for a city. Use the user's city if they "
            "don't specify one."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City name, e.g. 'New York' or 'London'.",
                },
            },
            "required": ["city"],
        },
    },
    {
        "name": "control_mac_app",
        "description": "Open an application on the user's MacBook by name, e.g. 'Spotify', 'Safari', 'Notes'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "app_name": {
                    "type": "string",
                    "description": "The exact name of the macOS app to open.",
                },
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "set_volume",
        "description": "Set the Mac's output volume to a level between 0 (mute) and 100 (max).",
        "input_schema": {
            "type": "object",
            "properties": {
                "level": {
                    "type": "integer",
                    "description": "Volume level from 0 (silent) to 100 (maximum).",
                    "minimum": 0,
                    "maximum": 100,
                },
            },
            "required": ["level"],
        },
    },
    {
        "name": "media_control",
        "description": "Control media playback on the Mac: play, pause, skip to next track, or go to previous track.",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["play", "pause", "next", "previous"],
                    "description": "The media action to perform.",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "open_url",
        "description": "Open a URL in the default browser on the Mac.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The full URL to open, e.g. 'https://google.com'.",
                },
            },
            "required": ["url"],
        },
    },
    {
        "name": "run_shortcut",
        "description": "Run a macOS Shortcut by name. Only shortcuts the user has already created in the Shortcuts app can be run.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The exact name of the macOS Shortcut to run.",
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "run_grok_build",
        "description": (
            "Run Grok Build (open-source coding agent) on a local project to "
            "implement, fix, refactor, scaffold, or explain code. Use this for "
            "software engineering work. project_path must be under the user's "
            "GROK_BUILD_ALLOWLIST. mode=build edits files immediately on "
            "allowlisted paths; mode=ask is read-only analysis. "
            "MULTI-TURN: continue_session=true (default) resumes the last Grok "
            "session for that project so follow-ups keep full context. Set "
            "new_session=true only when starting a fresh unrelated task on "
            "the same repo. Prefer build when the user wants changes made."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": (
                        "Clear engineering instruction for Grok Build, e.g. "
                        "'Add a /health endpoint and tests'."
                    ),
                },
                "project_path": {
                    "type": "string",
                    "description": (
                        "Absolute or ~ path to the project directory. "
                        "Must be under GROK_BUILD_ALLOWLIST."
                    ),
                },
                "mode": {
                    "type": "string",
                    "enum": ["build", "ask"],
                    "description": (
                        "build = implement changes (default, allowlisted paths). "
                        "ask = read-only analysis / Q&A about the codebase."
                    ),
                },
                "max_turns": {
                    "type": "integer",
                    "description": "Optional cap on agent turns (default from env).",
                    "minimum": 1,
                    "maximum": 128,
                },
                "continue_session": {
                    "type": "boolean",
                    "description": (
                        "Resume the stored Grok session for this project "
                        "(default true). Keeps multi-step product build context."
                    ),
                },
                "new_session": {
                    "type": "boolean",
                    "description": (
                        "Force a brand-new Grok session (ignores prior context). "
                        "Use when switching to an unrelated task on the same path."
                    ),
                },
                "session_id": {
                    "type": "string",
                    "description": (
                        "Optional explicit Grok session UUID to resume. "
                        "Usually omit — registry handles this."
                    ),
                },
            },
            "required": ["task", "project_path"],
        },
    },
    {
        "name": "list_grok_sessions",
        "description": (
            "List active Grok Build multi-turn sessions (project path → session id). "
            "Use when the user asks which engineering sessions are open."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "clear_grok_session",
        "description": (
            "Clear stored Grok multi-turn session for a project path, or all "
            "sessions if path is empty. Next run_grok_build starts fresh."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "project_path": {
                    "type": "string",
                    "description": "Project path to clear; omit/empty for all.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "design_3d_with_grok",
        "description": (
            "HIGH-FIDELITY 3D design: Grok Build authors a full Blender (bpy) scene, "
            "then Jarvis runs it headlessly and opens the .blend. Use this when the "
            "user wants a serious engineering concept model (lunar hopper thermal, "
            "lander, propulsion, mechanisms) that should look like a system — NOT "
            "a few random primitives. Prefer this over build_3d_model for quality. "
            "Multi-turn: continue_session=true to refine the same design. "
            "Takes longer (Grok agent run)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": (
                        "Full design request: what system, key subsystems, constraints, "
                        "what must be visible in the model."
                    ),
                },
                "name": {
                    "type": "string",
                    "description": "Short project slug, e.g. 'lunar_hopper_thermal'.",
                },
                "title": {
                    "type": "string",
                    "description": "Human title for the design.",
                },
                "open_after": {
                    "type": "boolean",
                    "description": "Open model.blend in Blender when done (default true).",
                },
                "continue_session": {
                    "type": "boolean",
                    "description": "Resume Grok design session for this project (default true).",
                },
                "new_session": {
                    "type": "boolean",
                    "description": "Force a fresh Grok design session.",
                },
                "max_turns": {
                    "type": "integer",
                    "description": "Optional Grok turn cap (default higher for design).",
                    "minimum": 5,
                    "maximum": 128,
                },
            },
            "required": ["description", "name"],
        },
    },
    {
        "name": "build_3d_model",
        "description": (
            "QUICK schematic 3D model via templates/primitives (fast). "
            "Use for rough whiteboard-style assemblies. For serious / realistic "
            "concept models, prefer design_3d_with_grok instead. "
            "Templates: lunar_thermal, hopper_lander, propulsion, electronics_bay. "
            "engine=auto uses Blender for colorized .blend when installed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Short project slug, e.g. 'lunar_hopper_thermal'.",
                },
                "title": {
                    "type": "string",
                    "description": "Human title for the model.",
                },
                "template": {
                    "type": "string",
                    "description": (
                        "System template id: lunar_thermal | hopper_lander | "
                        "propulsion | electronics_bay. Preferred over free-form parts."
                    ),
                },
                "scale": {
                    "type": "number",
                    "description": "Uniform scale for templates (default 1.0).",
                },
                "units": {
                    "type": "string",
                    "description": "Unit label for the brief, e.g. 'cm' or 'mm'.",
                },
                "notes": {
                    "type": "string",
                    "description": "Optional short design notes saved with the model.",
                },
                "engine": {
                    "type": "string",
                    "enum": ["auto", "blender", "primitives"],
                    "description": (
                        "auto (default)=Blender if installed else primitives; "
                        "blender=require Blender; primitives=STL only."
                    ),
                },
                "render": {
                    "type": "boolean",
                    "description": "If true (Blender), also export a PNG still render.",
                },
                "open_after": {
                    "type": "boolean",
                    "description": "If true and Blender built a .blend, open it in Blender.",
                },
                "parts": {
                    "type": "array",
                    "description": (
                        "Optional free-form parts if not using template. Types: "
                        "box|cylinder|sphere|cone|pipe|torus|panel|leg. "
                        "Prefer template for thermal/vehicle systems."
                    ),
                    "items": {"type": "object"},
                },
            },
            "required": ["name"],
        },
    },
    {
        "name": "workshop_engines",
        "description": (
            "Report whether Blender / primitives engines are available for "
            "build_3d_model. Call if unsure whether Blender is installed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "list_workshop_templates",
        "description": (
            "List system templates for build_3d_model (lunar_thermal, hopper_lander, etc.)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "write_design_brief",
        "description": (
            "Write a markdown design brief (explanation, requirements, how the "
            "system works) into the workshop. Pass project_dir from build_3d_model "
            "to keep brief + STL together."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Title / slug for the brief.",
                },
                "content": {
                    "type": "string",
                    "description": "Markdown body explaining the design.",
                },
                "project_dir": {
                    "type": "string",
                    "description": "Optional existing workshop project directory.",
                },
            },
            "required": ["name", "content"],
        },
    },
    {
        "name": "open_file",
        "description": (
            "Open a file on the Mac (STL, markdown, etc.) with the default app "
            "or a named app. Path must be under the workshop allowlist. For STL "
            "models try app_name 'eDrawings' first (installed on this Mac), else "
            "omit app_name for Preview/default."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to the file to open.",
                },
                "app_name": {
                    "type": "string",
                    "description": "Optional macOS app name, e.g. 'eDrawings', 'Preview'.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "reveal_in_finder",
        "description": (
            "Reveal a workshop file or folder in Finder so the user can grab it, "
            "AirDrop it, or open it manually."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to reveal.",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "remember",
        "description": (
            "Save a durable fact to long-term memory (survives restarts). "
            "Use for lasting preferences, project names/paths, decisions, "
            "people, or facts the user wants you to keep. Do NOT store "
            "passwords or API keys. category: note|preference|project|person."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "What to remember, in a clear short sentence.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional tags, e.g. ['lunar', 'thermal'].",
                },
                "category": {
                    "type": "string",
                    "enum": ["note", "preference", "project", "person"],
                    "description": "note (default), preference, project, or person.",
                },
            },
            "required": ["content"],
        },
    },
    {
        "name": "recall",
        "description": (
            "Search long-term memory. Empty query returns recent notes plus "
            "active project and preferences. Use when the user asks what you "
            "remember or refers to past work."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search text; omit for recent memories.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max notes to return (default 10).",
                    "minimum": 1,
                    "maximum": 50,
                },
            },
            "required": [],
        },
    },
    {
        "name": "forget",
        "description": "Delete a long-term memory note by its id (from recall).",
        "input_schema": {
            "type": "object",
            "properties": {
                "note_id": {
                    "type": "string",
                    "description": "The note id to remove.",
                },
            },
            "required": ["note_id"],
        },
    },
    {
        "name": "set_active_project",
        "description": (
            "Set or clear the active project path/name used as default context "
            "for engineering and design work. Pass empty string to clear."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path_or_name": {
                    "type": "string",
                    "description": "Project path or name; empty to clear.",
                },
            },
            "required": ["path_or_name"],
        },
    },
    {
        "name": "set_preference",
        "description": "Store a key/value preference (e.g. city=Austin, voice=short).",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Preference name."},
                "value": {"type": "string", "description": "Preference value."},
            },
            "required": ["key", "value"],
        },
    },
]

# --- Dispatch table --------------------------------------------------------

TOOL_FUNCTIONS = {
    "get_time": get_time,
    "get_weather": get_weather,
    "control_mac_app": control_mac_app,
    "set_volume": set_volume,
    "media_control": media_control,
    "open_url": open_url,
    "run_shortcut": run_shortcut,
    "run_grok_build": run_grok_build,
    "list_grok_sessions": list_grok_sessions,
    "clear_grok_session": clear_grok_session,
    "design_3d_with_grok": design_3d_with_grok,
    "build_3d_model": build_3d_model,
    "workshop_engines": workshop_engines,
    "list_workshop_templates": list_templates,
    "write_design_brief": write_design_brief,
    "open_file": open_file,
    "reveal_in_finder": reveal_in_finder,
    "remember": remember_fact,
    "recall": recall,
    "forget": forget,
    "set_active_project": set_active_project,
    "set_preference": set_preference,
}


def run_tool(name: str, tool_input: dict) -> dict:
    """Execute a tool by name with the given input dict."""
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return {"error": f"unknown tool: {name}"}
    args = dict(tool_input or {})
    try:
        return fn(**args)
    except TypeError as exc:
        return {"error": f"bad tool args for {name}: {exc}"}