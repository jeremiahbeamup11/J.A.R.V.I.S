"""
Jarvis memory — short-term session continuity + durable long-term notes.

Layers:
  1. Session turns — rolling conversation for multi-turn chat (disk-backed).
  2. Long-term notes — explicit facts Jarvis (or you) save across days.
  3. Preferences + active project — light structured context.

Storage (default): ~/Desktop/JARVIS/data/memory/
  long_term.json   notes, preferences, active_project
  session.json     current rolling dialogue

Safety: only writes under MEMORY_DIR. No secrets are auto-captured; Claude
must call remember() deliberately (or you use the HTTP API).
"""

from __future__ import annotations

import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

_lock = threading.RLock()

_DEFAULT_DIR = Path.home() / "Desktop" / "JARVIS" / "data" / "memory"


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def memory_dir() -> Path:
    raw = os.environ.get("MEMORY_DIR", "").strip()
    if raw:
        return Path(os.path.expanduser(raw)).resolve()
    return _DEFAULT_DIR.resolve()


def session_max_turns() -> int:
    return max(2, min(_env_int("MEMORY_SESSION_MAX_TURNS", 24), 100))


def session_idle_minutes() -> int:
    return max(5, min(_env_int("MEMORY_SESSION_IDLE_MINUTES", 180), 24 * 60))


def long_term_max() -> int:
    return max(10, min(_env_int("MEMORY_LONG_TERM_MAX", 200), 1000))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _long_path() -> Path:
    return memory_dir() / "long_term.json"


def _session_path() -> Path:
    return memory_dir() / "session.json"


def _ensure_dir() -> None:
    memory_dir().mkdir(parents=True, exist_ok=True)


def _read_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return json.loads(json.dumps(default))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return json.loads(json.dumps(default))


def _write_json(path: Path, data: dict) -> None:
    _ensure_dir()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


_EMPTY_LONG = {
    "version": 1,
    "preferences": {},
    "active_project": None,
    "notes": [],
}

_EMPTY_SESSION = {
    "version": 1,
    "session_id": None,
    "updated": None,
    "turns": [],
}


# --- Long-term -------------------------------------------------------------

def load_long_term() -> dict:
    with _lock:
        data = _read_json(_long_path(), _EMPTY_LONG)
        data.setdefault("preferences", {})
        data.setdefault("active_project", None)
        data.setdefault("notes", [])
        return data


def save_long_term(data: dict) -> None:
    with _lock:
        _write_json(_long_path(), data)


def remember(
    content: str,
    tags: list[str] | None = None,
    category: str = "note",
) -> dict:
    """Save a durable note. category: note | preference | project | person."""
    content = (content or "").strip()
    if not content:
        return {"ok": False, "error": "content is empty"}
    if len(content) > 2000:
        content = content[:2000] + "…"

    category = (category or "note").strip().lower()
    if category not in ("note", "preference", "project", "person"):
        category = "note"

    clean_tags: list[str] = []
    for t in tags or []:
        t = re.sub(r"[^\w\- ]+", "", str(t).strip())[:40]
        if t and t not in clean_tags:
            clean_tags.append(t)

    note = {
        "id": uuid.uuid4().hex[:12],
        "content": content,
        "tags": clean_tags,
        "category": category,
        "created": _now(),
    }

    with _lock:
        data = load_long_term()
        notes = list(data.get("notes") or [])
        notes.append(note)
        # Cap size — drop oldest
        max_n = long_term_max()
        if len(notes) > max_n:
            notes = notes[-max_n:]
        data["notes"] = notes

        if category == "preference":
            # Also mirror into preferences map when content looks like key=value
            m = re.match(r"^([A-Za-z0-9_\- ]{1,40})\s*[:=]\s*(.+)$", content)
            if m:
                key = m.group(1).strip().lower().replace(" ", "_")
                data.setdefault("preferences", {})[key] = m.group(2).strip()

        if category == "project":
            data["active_project"] = content

        save_long_term(data)

    return {
        "ok": True,
        "id": note["id"],
        "category": category,
        "result": f"Remembered ({category}): {content[:120]}",
    }


def recall(query: str | None = None, limit: int = 10) -> dict:
    """Search long-term notes. Empty query returns most recent."""
    limit = max(1, min(int(limit or 10), 50))
    data = load_long_term()
    notes = list(data.get("notes") or [])
    q = (query or "").strip().lower()

    if q:
        scored = []
        for n in notes:
            hay = " ".join(
                [
                    n.get("content") or "",
                    " ".join(n.get("tags") or []),
                    n.get("category") or "",
                ]
            ).lower()
            if q in hay or any(part in hay for part in q.split() if len(part) > 2):
                scored.append(n)
        hits = scored[-limit:]
    else:
        hits = notes[-limit:]

    return {
        "ok": True,
        "count": len(hits),
        "active_project": data.get("active_project"),
        "preferences": data.get("preferences") or {},
        "notes": hits,
        "result": f"Found {len(hits)} memories" + (f" matching {query!r}" if q else " (recent)"),
    }


def forget(note_id: str) -> dict:
    """Delete a long-term note by id."""
    note_id = (note_id or "").strip()
    if not note_id:
        return {"ok": False, "error": "note_id is empty"}

    with _lock:
        data = load_long_term()
        notes = data.get("notes") or []
        kept = [n for n in notes if n.get("id") != note_id]
        if len(kept) == len(notes):
            return {"ok": False, "error": f"no note with id {note_id!r}"}
        data["notes"] = kept
        save_long_term(data)
    return {"ok": True, "id": note_id, "result": f"Forgot note {note_id}"}


def set_active_project(path_or_name: str | None) -> dict:
    """Set or clear the active project string used as default context."""
    with _lock:
        data = load_long_term()
        if path_or_name is None or not str(path_or_name).strip():
            data["active_project"] = None
            save_long_term(data)
            return {"ok": True, "active_project": None, "result": "Cleared active project"}
        val = str(path_or_name).strip()[:500]
        data["active_project"] = val
        save_long_term(data)
        return {"ok": True, "active_project": val, "result": f"Active project set to {val}"}


def set_preference(key: str, value: str) -> dict:
    key = re.sub(r"[^\w\-]", "_", (key or "").strip().lower())[:40]
    value = (value or "").strip()[:500]
    if not key:
        return {"ok": False, "error": "key is empty"}
    with _lock:
        data = load_long_term()
        data.setdefault("preferences", {})[key] = value
        save_long_term(data)
    return {"ok": True, "key": key, "value": value, "result": f"Preference {key}={value}"}


# --- Session ---------------------------------------------------------------

def load_session() -> dict:
    with _lock:
        data = _read_json(_session_path(), _EMPTY_SESSION)
        data.setdefault("turns", [])
        data.setdefault("session_id", None)
        return data


def save_session(data: dict) -> None:
    with _lock:
        _write_json(_session_path(), data)


def _parse_ts(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None


def ensure_session() -> dict:
    """Return current session, rotating if idle too long."""
    with _lock:
        data = load_session()
        updated = _parse_ts(data.get("updated"))
        now = datetime.now(timezone.utc)
        idle_min = session_idle_minutes()
        stale = False
        if updated is not None:
            age = (now - updated).total_seconds() / 60.0
            if age > idle_min:
                stale = True
        if not data.get("session_id") or stale:
            data = {
                "version": 1,
                "session_id": uuid.uuid4().hex[:12],
                "updated": _now(),
                "turns": [],
            }
            save_session(data)
        return data


def clear_session() -> dict:
    with _lock:
        data = {
            "version": 1,
            "session_id": uuid.uuid4().hex[:12],
            "updated": _now(),
            "turns": [],
        }
        save_session(data)
        return {"ok": True, "session_id": data["session_id"], "result": "Session cleared"}


def record_turn(user_text: str, assistant_text: str, meta: dict | None = None) -> None:
    """Append a user/assistant pair to the rolling session."""
    user_text = (user_text or "").strip()
    assistant_text = (assistant_text or "").strip()
    if not user_text and not assistant_text:
        return

    # Cap individual turn size for context budgets
    if len(user_text) > 4000:
        user_text = user_text[:4000] + "…"
    if len(assistant_text) > 4000:
        assistant_text = assistant_text[:4000] + "…"

    with _lock:
        data = ensure_session()
        turns = list(data.get("turns") or [])
        ts = _now()
        if user_text:
            turns.append({"role": "user", "content": user_text, "ts": ts})
        if assistant_text:
            entry = {"role": "assistant", "content": assistant_text, "ts": ts}
            if meta:
                entry["meta"] = {
                    k: meta[k]
                    for k in ("routed_to", "model", "reason")
                    if k in meta and meta[k] is not None
                }
            turns.append(entry)

        max_t = session_max_turns()
        # turns are pairs roughly; keep last max_t messages
        if len(turns) > max_t:
            turns = turns[-max_t:]
        data["turns"] = turns
        data["updated"] = ts
        save_session(data)


def recent_turns(n: int | None = None) -> list[dict]:
    data = ensure_session()
    turns = data.get("turns") or []
    if n is None:
        return list(turns)
    return list(turns[-max(1, n) :])


def anthropic_history_messages(max_messages: int | None = None) -> list[dict]:
    """Prior session turns as Anthropic messages (user/assistant text only).

    Ensures the history starts with a user turn (API requirement) by dropping
    a leading assistant turn if present.
    """
    cap = max_messages if max_messages is not None else session_max_turns()
    turns = recent_turns(cap)
    msgs: list[dict] = []
    for t in turns:
        role = t.get("role")
        content = (t.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        # Merge consecutive same-role turns (shouldn't happen often)
        if msgs and msgs[-1]["role"] == role:
            msgs[-1]["content"] = msgs[-1]["content"] + "\n" + content
        else:
            msgs.append({"role": role, "content": content})
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    # Don't end with user — current message is appended by caller
    while msgs and msgs[-1]["role"] == "user":
        msgs.pop()
    return msgs


def ollama_history_messages(max_pairs: int = 4) -> list[dict]:
    """Small recent history for local model (user/assistant only)."""
    # 2 messages per pair
    return anthropic_history_messages(max_messages=max_pairs * 2)


# --- Prompt injection ------------------------------------------------------

def build_system_appendix(include_session_hint: bool = True) -> str:
    """Text block appended to the system prompt for the cloud brain."""
    data = load_long_term()
    session = ensure_session()
    lines = ["\n\n## Memory (use when relevant)"]
    lines.append(
        "You have long-term memory tools: remember, recall, forget, "
        "set_active_project, set_preference. "
        "When the user states a lasting preference, project, or fact worth "
        "keeping across days, call remember. When they ask what you know or "
        "refer to past work, call recall. Do not store secrets (passwords, API keys)."
    )

    prefs = data.get("preferences") or {}
    if prefs:
        lines.append("### Preferences")
        for k, v in list(prefs.items())[:30]:
            lines.append(f"- {k}: {v}")

    ap = data.get("active_project")
    if ap:
        lines.append(f"### Active project\n- {ap}")

    notes = list(data.get("notes") or [])[-12:]
    if notes:
        lines.append("### Recent long-term notes")
        for n in notes:
            tags = ",".join(n.get("tags") or []) or "—"
            lines.append(
                f"- [{n.get('id')}] ({n.get('category')}/{tags}) {n.get('content')}"
            )

    if include_session_hint:
        n_turns = len(session.get("turns") or [])
        lines.append(
            f"### Session\n- id={session.get('session_id')} turns={n_turns} "
            f"(earlier turns are in the message history)"
        )

    return "\n".join(lines)


def status() -> dict:
    session = ensure_session()
    long_t = load_long_term()
    return {
        "ok": True,
        "memory_dir": str(memory_dir()),
        "session_id": session.get("session_id"),
        "session_turns": len(session.get("turns") or []),
        "session_updated": session.get("updated"),
        "session_max_turns": session_max_turns(),
        "session_idle_minutes": session_idle_minutes(),
        "long_term_notes": len(long_t.get("notes") or []),
        "preferences": long_t.get("preferences") or {},
        "active_project": long_t.get("active_project"),
    }
