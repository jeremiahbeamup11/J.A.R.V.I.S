"""
Tool registry for Jarvis.

Each tool is a plain Python function plus a JSON schema describing it to
Claude. To add a tool: write the function, add its schema to TOOL_SCHEMAS,
and register it in TOOL_FUNCTIONS. Nothing else changes.

For Milestone 1 these are STUBS that only print(), so we can verify the
tool-calling loop end-to-end before wiring real integrations.
"""


def control_light(room: str, state: str) -> dict:
    """STUB: pretend to control a light in a room."""
    print(f"[TOOL] control_light(room={room!r}, state={state!r})")
    return {"room": room, "state": state, "result": "ok (stub)"}


def system_status() -> dict:
    """STUB: pretend to report system status."""
    print("[TOOL] system_status()")
    return {
        "cpu": "12%",
        "memory": "4.2GB / 16GB",
        "status": "all systems nominal (stub)",
    }


# --- Claude-facing schemas -------------------------------------------------

TOOL_SCHEMAS = [
    {
        "name": "control_light",
        "description": "Turn a light on or off in a given room.",
        "input_schema": {
            "type": "object",
            "properties": {
                "room": {
                    "type": "string",
                    "description": "The room whose light to control, e.g. 'lab'.",
                },
                "state": {
                    "type": "string",
                    "enum": ["on", "off"],
                    "description": "Whether to turn the light on or off.",
                },
            },
            "required": ["room", "state"],
        },
    },
    {
        "name": "system_status",
        "description": "Report current system status (CPU, memory, overall health).",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]

# --- Dispatch table --------------------------------------------------------

TOOL_FUNCTIONS = {
    "control_light": control_light,
    "system_status": system_status,
}


def run_tool(name: str, tool_input: dict) -> dict:
    """Execute a tool by name with the given input dict."""
    fn = TOOL_FUNCTIONS.get(name)
    if fn is None:
        return {"error": f"unknown tool: {name}"}
    return fn(**tool_input)