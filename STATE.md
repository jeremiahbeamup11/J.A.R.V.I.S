# Loop State

## Last Completed
Milestone 3: Mac control agent — Jarvis can open apps on the MacBook.
- mac_agent/mac_agent.py runs on the Mac, exposes /open_app and /health
- control_mac_app tool added to tools/__init__.py (function + schema in
  TOOL_SCHEMAS + registered in TOOL_FUNCTIONS)
- MAC_AGENT_URL set in .env
- Fixed a path bug: mac_agent folder had been created inside __pycache__;
  moved to jarvis/mac_agent/mac_agent.py (correct location).

## Verification Result
PASSED — 2026-06-21. Ran live:
  curl -X POST http://localhost:8000/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "Jarvis, open the Notes app"}'
The Notes app actually launched on the Mac. Real-world action confirmed,
not inspection. This is the first milestone where Jarvis controls a
physical machine.

## Current Task
Milestone 4: Expand Mac control tools. Add, one at a time, each as a new
endpoint in mac_agent.py + matching tool in tools/__init__.py:
  - set_volume(level 0-100)
  - media_control(action: play/pause/next/previous)
  - open_url(url)  [opens in default browser]
  - run_shortcut(name)  [runs a macOS Shortcut via the `shortcuts` CLI]

For EACH tool, follow the three-point wiring:
  1. function in tools/__init__.py
  2. schema added INTO the TOOL_SCHEMAS list
  3. registered in the TOOL_FUNCTIONS dict
Plus the matching endpoint in mac_agent.py.

Build and verify ONE tool per loop. Verify each by a real curl that
causes the actual effect (volume actually changes, music actually pauses),
not by inspecting code. Update STATE.md after each.

SAFETY: keep every endpoint narrow and enumerated. No raw shell. For
run_shortcut, only run named shortcuts the user has already created — do
not construct or execute arbitrary commands.

## Housekeeping (do first this loop)
- Confirm there is no leftover/duplicate mac_agent.py anywhere except
  jarvis/mac_agent/mac_agent.py. Delete any stray copy (e.g. one left
  inside a __pycache__ directory). One source of truth per file.
- Commit and push: Milestone 3 has not yet been pushed to GitHub.

## Blocked
(none)