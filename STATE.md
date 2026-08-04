# Loop State

## Context
Base stack is in good shape for product work: dual brain (Ollama + Claude),
Grok Build for code, Workshop for design STLs, phone remote for iPhone
control. Cosmetics (persona / calling polish) still deferred by user.

## Last Completed (this push)
Capability wave since Milestone 9d:

### Milestone 10 — Grok Build body (10a–10c)
- `tools/grok_build.py` + `run_grok_build` tool
- Allowlist (`GROK_BUILD_ALLOWLIST`), build auto-approved on allowlist
- Router target `grok` for pure engineering intents
- Shared `agent.py` (cloud / local / grok); wakeword uses same router

### Milestone 11a — Workshop body
- `tools/workshop.py`: `build_3d_model` (STL), `write_design_brief`,
  `open_file`, `reveal_in_finder`
- `mac_agent` `/open_path` + `/reveal_in_finder` (allowlisted)
- Design multi-step system prompt (reason → model → brief → open → explain)

### Milestone 12a — Phone remote
- `static/phone.html` + `phone_api.py` + `/phone` routes on orchestrator
- Text chat from iPhone over home LAN verified
- Mic button requires **HTTPS** (iOS secure context); HTTP works with
  keyboard dictation; ngrok HTTPS for real site mic
- Optional `JARVIS_PHONE_TOKEN`

### Ops this session
- Stopped test processes: uvicorn `:8010`, localtunnel
- Left user ngrok on `:5001` alone (`dense-racing-spectator.ngrok-free.dev`)
- Docs + .gitignore updated; push to origin/main

## Current Task
(none — pick next milestone)

## Recommended next (pick one)
1. **Memory / continuity** — highest daily-use value (STATE backlog #3).
   Short-term session memory + optional long-term notes so Jarvis remembers
   projects, preferences, and multi-turn design work.
2. **Phone mic HTTPS path** — dedicated `ngrok http 8010` (or mkcert LAN
   HTTPS) + start script so 🎙 works without keyboard workaround.
3. **10d Grok sessions** — multi-turn Grok Build (`--continue` / session id).
4. **11b richer CAD** — Blender/OpenSCAD when installed.
5. **Full base-test pass** — checklist: wakeword, mac_agent, workshop live,
   phone text, one Grok task (optional before more features).

## Blocked
(none)

## How to run (quick)
```bash
# Mac body
uvicorn mac_agent.mac_agent:app --host 127.0.0.1 --port 8765

# Brain + phone UI (LAN)
uvicorn main:app --host 0.0.0.0 --port 8010
# iPhone (same Wi‑Fi): http://<Mac-IP>:8010/phone

# Room voice
python wakeword.py

# Phone mic over HTTPS (repoint ngrok from 5001 if free):
# ngrok http 8010  →  https://…/phone
```

## Note
User deferred language/calling polish. Prefer capability + reliability next.
