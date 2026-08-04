"""
Grok Build body tool for Jarvis.

Runs the open-source Grok Build CLI headlessly against an allowlisted
project directory. Safety model:

  - CWD must resolve under GROK_BUILD_ALLOWLIST (comma-separated roots).
  - No raw shell: only the fixed `grok -p` invocation with enumerated flags.
  - mode=build is allowed immediately on allowlisted paths (user policy).
  - mode=ask restricts Grok to read-only tools.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

# Read-only tool set for mode=ask (headless --tools allowlist).
_ASK_TOOLS = "read_file,grep,list_dir,web_search,web_fetch,open_page"

# Absolute path patterns that may appear in natural language.
_PATH_RE = re.compile(
    r"(?:"
    r"~(?:/[\w.\-]+)+"  # ~/foo/bar
    r"|/(?:Users|home|tmp|var|opt)(?:/[\w.\-]+)+"
    r"|(?:/[\w.\-]+){2,}"  # other absolute-ish paths
    r")"
)


def _env(name: str, default: str = "") -> str:
    """Read env at call time so values set by load_dotenv() are visible."""
    return os.environ.get(name, default)


def default_cwd() -> str:
    """Optional default project path from env (call-time read)."""
    return _env("GROK_BUILD_DEFAULT_CWD").strip()


def _parse_allowlist() -> list[Path]:
    roots: list[Path] = []
    for part in _env("GROK_BUILD_ALLOWLIST").split(","):
        part = part.strip()
        if not part:
            continue
        p = Path(os.path.expanduser(part)).resolve()
        roots.append(p)
    return roots


def allowlist_roots() -> list[str]:
    """Public helper: resolved allowlist roots as strings."""
    return [str(p) for p in _parse_allowlist()]


def resolve_project_path(project_path: str | None) -> tuple[Path | None, str | None]:
    """Resolve and validate a project path against the allowlist.

    Returns (path, None) on success, or (None, error_message) on failure.
    """
    roots = _parse_allowlist()
    if not roots:
        return None, (
            "GROK_BUILD_ALLOWLIST is empty. Set it in .env to a comma-separated "
            "list of allowed project roots, e.g. ~/Desktop,~/Projects"
        )

    raw = (project_path or "").strip() or default_cwd()
    if not raw:
        return None, (
            "No project_path provided and GROK_BUILD_DEFAULT_CWD is unset. "
            f"Allowed roots: {[str(r) for r in roots]}"
        )

    try:
        path = Path(os.path.expanduser(raw)).resolve()
    except (OSError, RuntimeError) as exc:
        return None, f"invalid project_path: {exc}"

    if not path.exists():
        return None, f"project path does not exist: {path}"
    if not path.is_dir():
        return None, f"project path is not a directory: {path}"

    # path must be equal to or under an allowlisted root
    for root in roots:
        try:
            path.relative_to(root)
            return path, None
        except ValueError:
            continue

    return None, (
        f"project path {path} is outside the allowlist. "
        f"Allowed roots: {[str(r) for r in roots]}"
    )


def extract_path_from_text(text: str) -> str | None:
    """Best-effort extract of a filesystem path from a user message."""
    # Prefer quoted paths
    for q in re.findall(r'["\']([^"\']+)["\']', text):
        if "/" in q or q.startswith("~"):
            expanded = os.path.expanduser(q)
            if os.path.isdir(expanded):
                return q
    matches = _PATH_RE.findall(text)
    for m in matches:
        expanded = os.path.expanduser(m)
        if os.path.isdir(expanded):
            return m
    return None


def _find_grok_bin() -> str | None:
    grok_bin = _env("GROK_BIN", os.path.expanduser("~/.grok/bin/grok"))
    if grok_bin and os.path.isfile(grok_bin) and os.access(grok_bin, os.X_OK):
        return grok_bin
    return shutil.which("grok")


def run_grok_build(
    task: str,
    project_path: str | None = None,
    mode: str = "build",
    max_turns: int | None = None,
) -> dict:
    """Run Grok Build headlessly on an allowlisted project.

    Args:
        task: Engineering instruction for Grok.
        project_path: Directory to work in (must be under allowlist).
        mode: "build" (edit + run tools, auto-approved on allowlist) or
              "ask" (read-only tools only).
        max_turns: Cap on agentic turns (default from env).
    """
    task = (task or "").strip()
    if not task:
        return {"ok": False, "error": "task is empty"}

    mode = (mode or "build").strip().lower()
    if mode not in ("build", "ask"):
        return {"ok": False, "error": f"mode must be 'build' or 'ask', got {mode!r}"}

    path, err = resolve_project_path(project_path)
    if err:
        return {"ok": False, "error": err}

    grok = _find_grok_bin()
    if not grok:
        return {
            "ok": False,
            "error": (
                "grok binary not found. Install Grok Build or set GROK_BIN "
                "to the full path (default ~/.grok/bin/grok)."
            ),
        }

    turns_default = int(_env("GROK_BUILD_MAX_TURNS", "40") or "40")
    timeout_sec = int(_env("GROK_BUILD_TIMEOUT_SEC", "900") or "900")
    turns = max_turns if max_turns is not None else turns_default
    turns = max(1, min(int(turns), 128))

    cmd = [
        grok,
        "-p",
        task,
        "--cwd",
        str(path),
        "--output-format",
        "json",
        "--max-turns",
        str(turns),
        "--no-auto-update",
    ]

    if mode == "build":
        # User policy: build is allowed immediately on allowlisted paths.
        cmd.extend(["--always-approve", "--permission-mode", "bypassPermissions"])
    else:
        cmd.extend(["--tools", _ASK_TOOLS])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env={**os.environ, "NO_COLOR": "1"},
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": f"Grok Build timed out after {timeout_sec}s",
            "project_path": str(path),
            "mode": mode,
        }
    except FileNotFoundError:
        return {"ok": False, "error": f"failed to execute grok at {grok}"}

    stdout = (result.stdout or "").strip()
    stderr = (result.stderr or "").strip()

    payload: dict = {
        "ok": result.returncode == 0,
        "project_path": str(path),
        "mode": mode,
        "max_turns": turns,
        "exit_code": result.returncode,
    }

    if stdout:
        try:
            data = json.loads(stdout)
            payload["text"] = data.get("text") or data.get("result") or ""
            payload["stop_reason"] = data.get("stopReason") or data.get("stop_reason")
            payload["session_id"] = data.get("sessionId") or data.get("session_id")
            payload["num_turns"] = data.get("num_turns")
            if data.get("total_cost_usd") is not None:
                payload["total_cost_usd"] = data["total_cost_usd"]
        except json.JSONDecodeError:
            # Plain text fallback if json parse fails
            payload["text"] = stdout[:8000]
    else:
        payload["text"] = ""

    if result.returncode != 0:
        payload["error"] = stderr[:2000] if stderr else f"grok exited {result.returncode}"
        if not payload["text"] and stderr:
            payload["text"] = stderr[:4000]

    # Cap reply size so Claude / TTS don't choke on huge dumps
    if isinstance(payload.get("text"), str) and len(payload["text"]) > 6000:
        payload["text"] = payload["text"][:6000] + "\n…[truncated]"

    return payload
