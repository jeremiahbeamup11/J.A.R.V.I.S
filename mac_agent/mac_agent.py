"""
Jarvis — Mac Control Agent
Runs ON the MacBook. Exposes safe, enumerated endpoints that the Jarvis
orchestrator calls over the local network. This is Jarvis's first "body."

SAFETY: Only the capabilities defined here exist. There is no general
shell endpoint. open_app is allow-listed implicitly by macOS (it can only
open apps that exist) and uses `open -a`, which does not execute arbitrary
code.

Run on the Mac with:
    pip install fastapi uvicorn
    uvicorn mac_agent:app --host 0.0.0.0 --port 8765

Find the Mac's LAN IP with:  ipconfig getifaddr en0
Put that IP + port in the orchestrator's .env as MAC_AGENT_URL.
"""

import shutil
import subprocess

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Jarvis Mac Agent")


class OpenAppRequest(BaseModel):
    app_name: str


class SetVolumeRequest(BaseModel):
    level: int


class MediaControlRequest(BaseModel):
    action: str


class OpenUrlRequest(BaseModel):
    url: str


class RunShortcutRequest(BaseModel):
    name: str


@app.get("/health")
def health():
    return {"status": "mac agent online"}


@app.post("/open_app")
def open_app(req: OpenAppRequest):
    """Open a macOS application by name using `open -a`.

    `open -a` only launches existing applications; it cannot run arbitrary
    commands, which keeps this endpoint safe. Returns success or a clear
    error string the orchestrator can relay to Claude.
    """
    if shutil.which("open") is None:
        return {"ok": False, "error": "`open` not found — not macOS?"}

    # Guard against obvious injection in the app name. App names are simple.
    name = req.app_name.strip()
    if not name or any(c in name for c in [";", "|", "&", "`", "$", "\n"]):
        return {"ok": False, "error": f"invalid app name: {name!r}"}

    try:
        result = subprocess.run(
            ["open", "-a", name],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "open timed out"}

    if result.returncode == 0:
        return {"ok": True, "app": name, "result": f"opened {name}"}
    return {
        "ok": False,
        "app": name,
        "error": result.stderr.strip() or f"could not open {name}",
    }


@app.post("/set_volume")
def set_volume(req: SetVolumeRequest):
    """Set macOS output volume (0-100) via osascript."""
    level = max(0, min(100, req.level))
    try:
        subprocess.run(
            ["osascript", "-e", f"set volume output volume {level}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "osascript timed out"}
    return {"ok": True, "level": level, "result": f"volume set to {level}"}


_MEDIA_KEY_CODES = {
    "play": 16,
    "pause": 16,
    "next": 17,
    "previous": 18,
}


@app.post("/media_control")
def media_control(req: MediaControlRequest):
    """Send a media key event (play/pause/next/previous) via osascript.

    Uses CGEvent key codes for the media keys — no shell involved, just
    a fixed AppleScript snippet per allowed action.
    """
    action = req.action.strip().lower()
    key_code = _MEDIA_KEY_CODES.get(action)
    if key_code is None:
        return {
            "ok": False,
            "error": f"unknown action {action!r} — use play, pause, next, or previous",
        }

    script = (
        "on run\n"
        f"  set keyCode to {key_code}\n"
        "  tell application \"System Events\" to key code keyCode\n"
        "end run"
    )
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "osascript timed out"}

    if result.returncode != 0:
        return {"ok": False, "action": action, "error": result.stderr.strip()}
    return {"ok": True, "action": action, "result": f"media {action} sent"}


@app.post("/open_url")
def open_url_endpoint(req: OpenUrlRequest):
    """Open a URL in the default browser using `open`.

    Only allows http:// and https:// schemes to prevent file:// or
    custom-scheme abuse.
    """
    url = req.url.strip()
    if not url.startswith(("http://", "https://")):
        return {"ok": False, "error": "only http:// and https:// URLs are allowed"}

    try:
        result = subprocess.run(
            ["open", url],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "open timed out"}

    if result.returncode == 0:
        return {"ok": True, "url": url, "result": f"opened {url}"}
    return {"ok": False, "url": url, "error": result.stderr.strip() or f"could not open {url}"}


def _list_shortcuts() -> set[str]:
    """Return the set of shortcut names the user has created."""
    try:
        result = subprocess.run(
            ["shortcuts", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return set()
        return {line.strip() for line in result.stdout.splitlines() if line.strip()}
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return set()


@app.get("/list_shortcuts")
def list_shortcuts():
    """Return the names of all macOS Shortcuts the user has created."""
    return {"ok": True, "shortcuts": sorted(_list_shortcuts())}


@app.post("/run_shortcut")
def run_shortcut(req: RunShortcutRequest):
    """Run a named macOS Shortcut via the `shortcuts` CLI.

    SAFETY: validates the name against `shortcuts list` first — only
    shortcuts the user has already created can be run. No arbitrary
    command execution.
    """
    name = req.name.strip()
    if not name:
        return {"ok": False, "error": "shortcut name is empty"}

    available = _list_shortcuts()
    if not available:
        return {"ok": False, "error": "no shortcuts found — create one in the Shortcuts app first"}
    if name not in available:
        return {
            "ok": False,
            "error": f"shortcut {name!r} not found. Available: {sorted(available)}",
        }

    try:
        result = subprocess.run(
            ["shortcuts", "run", name],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"shortcut {name!r} timed out (30s)"}

    if result.returncode == 0:
        return {"ok": True, "shortcut": name, "result": f"ran shortcut {name!r}"}
    return {
        "ok": False,
        "shortcut": name,
        "error": result.stderr.strip() or f"shortcut {name!r} failed",
    }