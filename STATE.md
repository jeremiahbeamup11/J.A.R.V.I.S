# Loop State

## Context
Phone/local HTTPS deferred — user will solve remote access via private
cloud / always-on host later (not pure Vercel for whole stack). Focus moved
to workshop model quality.

## Architecture note (phone / cloud)
- Public HTTPS origin helps the *phone UI + mic*.
- Full Jarvis still needs a machine that can run Blender, mac_agent, wake
  word, Grok CLI — a home always-on box or hybrid (web UI in cloud, bodies
  on Mac/host), not serverless Vercel alone for the whole brain.

## Last Completed
Workshop model upgrade (11b2):
- `tools/workshop_templates.py` — lunar_thermal, hopper_lander, propulsion,
  electronics_bay with real subsystem part counts + color legend
- Blender types: pipe, torus, panel, leg + auto-framed camera
- Optional PNG still (`render=true`)
- `build_3d_model(template=...)` preferred path
- Agent prompt: forbid 3–4 random shapes; use templates
- `GET /workshop/templates`

## Current Task
(none — user should restart stack and re-ask thermal/hopper design)

## Next
1. Live voice: "lunar hopper thermal system" → should open dense template
2. Optional further geometry polish / Keynote (11c)
3. Private host / remote access when ready

## How to test
```bash
cd ~/Desktop/JARVIS
./stop_jarvis.sh 2>/dev/null; ./start_jarvis.sh
# or: python3 wakeword.py
# "Hey Jarvis, how does a lunar hopper thermal system work — build the model"
```

## Blocked
(none)
