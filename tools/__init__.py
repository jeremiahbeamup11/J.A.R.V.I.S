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
]

# --- Dispatch table --------------------------------------------------------

TOOL_FUNCTIONS = {
    "get_time": get_time,
    "get_weather": get_weather,
    "control_mac_app": control_mac_app,
}


def run_tool(name: str, tool_input: dict) -> dict:
    """Execute a tool by name with the given input dict."""
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return {"error": f"unknown tool: {name}"}
    return fn(**tool_input)