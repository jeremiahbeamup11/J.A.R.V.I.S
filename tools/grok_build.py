"""
Grok Build body tool for Jarvis.

Runs the open-source Grok Build CLI headlessly against an allowlisted
project directory. Safety model:

  - CWD must resolve under GROK_BUILD_ALLOWLIST (comma-separated roots).
  - No raw shell: only the fixed `grok -p` invocation with enumerated flags.
  - mode=build is allowed immediately on allowlisted paths (user policy).
  - mode=ask restricts Grok to read-only tools.

Milestone 10d — multi-turn sessions:
  - Per-project Grok session_id stored under data/grok_sessions.json
  - continue_session=True (default) resumes with `grok -r <session_id>`
  - new_session=True starts fresh; clear_grok_session drops the registry entry
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import uuid
from datetime import datetime, timezone
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

_registry_lock = threading.RLock()

# UUID shape for grok -r / -s (scripts should prefer IDs)
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _env(name: str, default: str = "") -> str:
    """Read env at call time so values set by load_dotenv() are visible."""
    return os.environ.get(name, default)


def default_cwd() -> str:
    """Optional default project path from env (call-time read)."""
    return _env("GROK_BUILD_DEFAULT_CWD").strip()


def _data_dir() -> Path:
    raw = _env("MEMORY_DIR").strip()
    if raw:
        # MEMORY_DIR is .../data/memory → parent is data/
        p = Path(os.path.expanduser(raw)).resolve()
        if p.name == "memory":
            return p.parent
        return p
    return (Path.home() / "Desktop" / "JARVIS" / "data").resolve()


def _sessions_path() -> Path:
    return _data_dir() / "grok_sessions.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


# --- Session registry (per project path) -----------------------------------

def _load_registry() -> dict:
    path = _sessions_path()
    if not path.exists():
        return {"version": 1, "projects": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("version", 1)
            data.setdefault("projects", {})
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"version": 1, "projects": {}}


def _save_registry(data: dict) -> None:
    path = _sessions_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def get_project_session(project_path: str | Path) -> dict | None:
    """Return registry entry for a project, or None."""
    key = str(Path(project_path).resolve())
    with _registry_lock:
        reg = _load_registry()
        entry = (reg.get("projects") or {}).get(key)
        return dict(entry) if entry else None


def set_project_session(
    project_path: str | Path,
    session_id: str,
    *,
    last_task: str | None = None,
    mode: str | None = None,
) -> dict:
    """Persist Grok session id for a project path."""
    key = str(Path(project_path).resolve())
    session_id = (session_id or "").strip()
    if not session_id:
        return {"ok": False, "error": "session_id empty"}

    with _registry_lock:
        reg = _load_registry()
        projects = reg.setdefault("projects", {})
        prev = projects.get(key) or {}
        entry = {
            "session_id": session_id,
            "updated": _now(),
            "last_task": (last_task or prev.get("last_task") or "")[:500],
            "mode": mode or prev.get("mode") or "build",
            "project_path": key,
        }
        projects[key] = entry
        _save_registry(reg)
        return {"ok": True, **entry}


def clear_grok_session(project_path: str | None = None) -> dict:
    """Clear Grok session for one project, or all if path omitted."""
    with _registry_lock:
        reg = _load_registry()
        projects = reg.setdefault("projects", {})
        if not project_path or not str(project_path).strip():
            n = len(projects)
            reg["projects"] = {}
            _save_registry(reg)
            return {"ok": True, "cleared": n, "result": f"Cleared all Grok sessions ({n})"}

        path, err = resolve_project_path(project_path)
        if err:
            # allow clearing by exact registry key even if path deleted
            key = str(Path(os.path.expanduser(project_path)).resolve()) if project_path else ""
            if key in projects:
                del projects[key]
                _save_registry(reg)
                return {"ok": True, "project_path": key, "result": f"Cleared Grok session for {key}"}
            return {"ok": False, "error": err}

        key = str(path)
        if key not in projects:
            return {
                "ok": True,
                "project_path": key,
                "result": f"No Grok session stored for {key}",
            }
        del projects[key]
        _save_registry(reg)
        return {"ok": True, "project_path": key, "result": f"Cleared Grok session for {key}"}


def list_grok_sessions() -> dict:
    """List all stored Grok project sessions."""
    with _registry_lock:
        reg = _load_registry()
        projects = reg.get("projects") or {}
        items = sorted(projects.values(), key=lambda e: e.get("updated") or "", reverse=True)
        return {
            "ok": True,
            "count": len(items),
            "sessions": items,
            "registry_path": str(_sessions_path()),
        }


def _is_uuid(value: str) -> bool:
    return bool(_UUID_RE.match((value or "").strip()))


def run_grok_build(
    task: str,
    project_path: str | None = None,
    mode: str = "build",
    max_turns: int | None = None,
    continue_session: bool = True,
    session_id: str | None = None,
    new_session: bool = False,
) -> dict:
    """Run Grok Build headlessly on an allowlisted project.

    Args:
        task: Engineering instruction for Grok.
        project_path: Directory to work in (must be under allowlist).
        mode: "build" (edit + run tools, auto-approved on allowlist) or
              "ask" (read-only tools only).
        max_turns: Cap on agentic turns (default from env).
        continue_session: If True (default), resume the last Grok session for
            this project when known (`grok -r <id>`), else start new.
        session_id: Explicit Grok session UUID to resume (overrides registry).
        new_session: If True, force a fresh session (ignore registry / id).
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
    assert path is not None

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

    # Resolve which session to resume
    resume_id: str | None = None
    session_mode = "new"
    if new_session:
        session_mode = "new"
    elif session_id and str(session_id).strip():
        sid = str(session_id).strip()
        if not _is_uuid(sid):
            return {
                "ok": False,
                "error": (
                    f"session_id must be a UUID (got {sid!r}). "
                    "Use continue_session=true without an id to resume the project session."
                ),
            }
        resume_id = sid
        session_mode = "resume_explicit"
    elif continue_session:
        entry = get_project_session(path)
        if entry and entry.get("session_id"):
            sid = str(entry["session_id"]).strip()
            if _is_uuid(sid):
                resume_id = sid
                session_mode = "resume_registry"
            else:
                # Non-UUID stored id — fall back to -c for that cwd
                session_mode = "continue_cwd"
        else:
            # No registry entry: still try -c (most recent in this cwd)
            # only if env allows; default: start new for clean first run
            if _env("GROK_BUILD_CONTINUE_WITHOUT_ID", "").strip().lower() in (
                "1",
                "true",
                "yes",
            ):
                session_mode = "continue_cwd"
            else:
                session_mode = "new"

    def _build_cmd(resume: str | None, use_continue: bool) -> list[str]:
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
        if resume:
            cmd.extend(["-r", resume])
        elif use_continue:
            cmd.append("-c")
        if mode == "build":
            cmd.extend(["--always-approve", "--permission-mode", "bypassPermissions"])
        else:
            cmd.extend(["--tools", _ASK_TOOLS])
        return cmd

    use_continue = session_mode == "continue_cwd"
    cmd = _build_cmd(resume_id, use_continue)

    def _run(cmd_list: list[str]) -> subprocess.CompletedProcess:
        return subprocess.run(
            cmd_list,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env={**os.environ, "NO_COLOR": "1"},
        )

    try:
        result = _run(cmd)
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": f"Grok Build timed out after {timeout_sec}s",
            "project_path": str(path),
            "mode": mode,
            "session_mode": session_mode,
            "resumed_session_id": resume_id,
        }
    except FileNotFoundError:
        return {"ok": False, "error": f"failed to execute grok at {grok}"}

    # If resume failed (stale/missing session), retry once as a fresh session
    retried_fresh = False
    if result.returncode != 0 and resume_id:
        err_blob = ((result.stderr or "") + "\n" + (result.stdout or "")).lower()
        resume_fail = any(
            tok in err_blob
            for tok in (
                "session",
                "not found",
                "resume",
                "unknown",
                "invalid",
                "no such",
            )
        )
        if resume_fail or result.returncode != 0:
            retried_fresh = True
            session_mode = "new_after_resume_fail"
            try:
                result = _run(_build_cmd(None, False))
            except subprocess.TimeoutExpired:
                return {
                    "ok": False,
                    "error": f"Grok Build timed out after {timeout_sec}s (retry)",
                    "project_path": str(path),
                    "mode": mode,
                    "session_mode": session_mode,
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
        "session_mode": session_mode,
        "continued": session_mode.startswith("resume") or session_mode == "continue_cwd",
        "retried_fresh": retried_fresh,
    }
    if resume_id and not retried_fresh:
        payload["resumed_session_id"] = resume_id

    if stdout:
        try:
            data = json.loads(stdout)
            payload["text"] = data.get("text") or data.get("result") or ""
            payload["stop_reason"] = data.get("stopReason") or data.get("stop_reason")
            sid = data.get("sessionId") or data.get("session_id")
            if sid:
                payload["session_id"] = sid
            payload["num_turns"] = data.get("num_turns")
            if data.get("total_cost_usd") is not None:
                payload["total_cost_usd"] = data["total_cost_usd"]
        except json.JSONDecodeError:
            payload["text"] = stdout[:8000]
    else:
        payload["text"] = ""

    if result.returncode != 0:
        payload["error"] = stderr[:2000] if stderr else f"grok exited {result.returncode}"
        if not payload["text"] and stderr:
            payload["text"] = stderr[:4000]

    # Persist session id for multi-turn follow-ups on this project
    sid = payload.get("session_id")
    if sid and _is_uuid(str(sid)):
        set_project_session(path, str(sid), last_task=task, mode=mode)
        payload["session_saved"] = True
    elif payload.get("ok") and session_mode in ("continue_cwd",):
        # -c may not always echo session id in older builds; keep prior registry
        entry = get_project_session(path)
        if entry and entry.get("session_id"):
            payload["session_id"] = entry["session_id"]
            payload["session_saved"] = False

    if isinstance(payload.get("text"), str) and len(payload["text"]) > 6000:
        payload["text"] = payload["text"][:6000] + "\n…[truncated]"

    return payload
