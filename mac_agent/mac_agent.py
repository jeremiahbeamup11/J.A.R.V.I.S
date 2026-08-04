"""
Jarvis — Mac Control Agent
Runs ON the MacBook. Exposes safe, enumerated endpoints that the Jarvis
orchestrator calls over the local network. This is Jarvis's first "body."

SAFETY: Only the capabilities defined here exist. There is no general
shell endpoint. open_app is allow-listed implicitly by macOS (it can only
open apps that exist) and uses `open -a`, which does not execute arbitrary
code. open_path / reveal_in_finder only work under WORKSHOP_DIR + optional
extra roots in OPEN_PATH_ALLOWLIST.

Run on the Mac with:
    pip install fastapi uvicorn python-dotenv
    uvicorn mac_agent:app --host 0.0.0.0 --port 8765
  (from the mac_agent/ dir) or:
    uvicorn mac_agent.mac_agent:app --host 0.0.0.0 --port 8765
  (from the JARVIS repo root)

Find the Mac's LAN IP with:  ipconfig getifaddr en0
Put that IP + port in the orchestrator's .env as MAC_AGENT_URL.
"""

import os
import shutil
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

# Load repo .env when run from JARVIS root or mac_agent/
load_dotenv()
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

app = FastAPI(title="Jarvis Mac Agent")

_DEFAULT_WORKSHOP = Path.home() / "Desktop" / "JARVIS" / "workshop"


def _workshop_root() -> Path:
    raw = os.environ.get("WORKSHOP_DIR", "").strip()
    if raw:
        return Path(os.path.expanduser(raw)).resolve()
    return _DEFAULT_WORKSHOP.resolve()


def _open_path_roots() -> list[Path]:
    """Roots under which open_path / reveal_in_finder are allowed."""
    roots = [_workshop_root()]
    extra = os.environ.get("OPEN_PATH_ALLOWLIST", "").strip()
    for part in extra.split(","):
        part = part.strip()
        if not part:
            continue
        roots.append(Path(os.path.expanduser(part)).resolve())
    # Always allow Desktop/JARVIS as a whole so briefs next to code are OK
    jarvis = Path.home() / "Desktop" / "JARVIS"
    if jarvis.exists():
        roots.append(jarvis.resolve())
    # de-dupe
    seen: set[str] = set()
    out: list[Path] = []
    for r in roots:
        key = str(r)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def _validate_open_path(raw: str) -> tuple[Path | None, str | None]:
    if not raw or not raw.strip():
        return None, "path is empty"
    # Block obvious injection / odd schemes
    p = raw.strip()
    if any(c in p for c in [";", "|", "&", "`", "\n", "\r"]):
        return None, f"invalid path: {p!r}"
    try:
        path = Path(os.path.expanduser(p)).resolve()
    except (OSError, RuntimeError) as exc:
        return None, f"invalid path: {exc}"
    if not path.exists():
        return None, f"path does not exist: {path}"
    for root in _open_path_roots():
        try:
            path.relative_to(root)
            return path, None
        except ValueError:
            continue
    return None, (
        f"path {path} is outside open allowlist. "
        f"Roots: {[str(r) for r in _open_path_roots()]}"
    )


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


class OpenPathRequest(BaseModel):
    path: str
    app_name: str | None = None


class RevealRequest(BaseModel):
    path: str


@app.get("/health")
def health():
    return {
        "status": "mac agent online",
        "workshop": str(_workshop_root()),
        "open_roots": [str(r) for r in _open_path_roots()],
    }


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


@app.post("/open_path")
def open_path(req: OpenPathRequest):
    """Open a file/folder with the default app, or a named app.

    SAFETY: path must resolve under WORKSHOP_DIR / OPEN_PATH_ALLOWLIST /
    ~/Desktop/JARVIS. Optional app_name uses `open -a` (same as open_app).
    """
    path, err = _validate_open_path(req.path)
    if err:
        return {"ok": False, "error": err}
    assert path is not None

    if shutil.which("open") is None:
        return {"ok": False, "error": "`open` not found — not macOS?"}

    cmd = ["open"]
    app = (req.app_name or "").strip()
    if app:
        if any(c in app for c in [";", "|", "&", "`", "$", "\n"]):
            return {"ok": False, "error": f"invalid app name: {app!r}"}
        cmd.extend(["-a", app])
    cmd.append(str(path))

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "open timed out"}

    if result.returncode == 0:
        return {
            "ok": True,
            "path": str(path),
            "app": app or "default",
            "result": f"opened {path}" + (f" with {app}" if app else ""),
        }
    return {
        "ok": False,
        "path": str(path),
        "error": result.stderr.strip() or f"could not open {path}",
    }


@app.post("/reveal_in_finder")
def reveal_in_finder(req: RevealRequest):
    """Reveal a file/folder in Finder (`open -R`). Allowlisted paths only."""
    path, err = _validate_open_path(req.path)
    if err:
        return {"ok": False, "error": err}
    assert path is not None

    if shutil.which("open") is None:
        return {"ok": False, "error": "`open` not found — not macOS?"}

    try:
        result = subprocess.run(
            ["open", "-R", str(path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "open timed out"}

    if result.returncode == 0:
        return {"ok": True, "path": str(path), "result": f"revealed {path} in Finder"}
    return {
        "ok": False,
        "path": str(path),
        "error": result.stderr.strip() or f"could not reveal {path}",
    }