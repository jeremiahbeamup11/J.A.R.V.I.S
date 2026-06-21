"""
Tool registry for Jarvis.

Each tool is a plain Python function plus a JSON schema describing it to
Claude. To add a tool: write the function, add its schema to TOOL_SCHEMAS,
and register it in TOOL_FUNCTIONS. Nothing else changes.
"""

import os
from datetime import datetime

import requests

MAC_AGENT_URL = os.environ.get("MAC_AGENT_URL", "http://localhost:8765")


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
}


def run_tool(name: str, tool_input: dict) -> dict:
    """Execute a tool by name with the given input dict."""
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return {"error": f"unknown tool: {name}"}
    return fn(**tool_input)