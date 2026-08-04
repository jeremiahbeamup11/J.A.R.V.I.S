# Loop State

## Context
Jarvis is operational for daily use: dual brain, Grok Build, workshop STLs,
phone remote (text), wake-word voice, and memory (session + long-term).

## Last Completed
Milestone 13a — Memory (implemented + live stack confirmed working).

Verified live by user:
- Wake word voice loop works end-to-end (Hey Jarvis → reply + TTS)
- Memory layer in place (session + long-term notes/tools)
- mac_agent + orchestrator + wakeword used together successfully

Code landed this milestone:
- `memory.py` — session + long-term disk store
- Tools: remember, recall, forget, set_active_project, set_preference
- `agent.py` — history injection, system memory appendix, turn recording
- `main.py` — `/memory` APIs
- Docs + gitignore for `data/`

## Current Task
(none — pick next)

## Next (capability order)
1. **12b Phone mic HTTPS** — start script + ngrok/HTTPS so 🎙 works on iPhone
2. **10d Grok multi-turn** — continue/session id for real product builds
3. **13b Per-client sessions** — separate phone vs wakeword memory streams
4. **11b Richer CAD** — when Blender/OpenSCAD installed
5. **ESP32 body** — hardware week

## Blocked
(none)

## How to run (full stack)
```bash
# 1 Mac body
uvicorn mac_agent.mac_agent:app --host 127.0.0.1 --port 8765

# 2 Brain + phone UI
uvicorn main:app --host 0.0.0.0 --port 8010

# 3 Room voice
python3 wakeword.py
# Say: "Hey Jarvis …"
```

## Note
Cosmetics (persona/calling polish) still deferred. Prefer capability next.
