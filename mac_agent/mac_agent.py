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