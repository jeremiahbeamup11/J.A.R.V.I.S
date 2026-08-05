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
Workshop quality paths:
1. Templates (11b2) — fast schematic systems
2. **design_3d_with_grok** — Grok Build authors full Blender bpy scenes
   (stronger fidelity). Claude orchestrates/explains; Grok models.

- `tools/workshop_grok.py` — seed project → Grok → Blender headless → open
- Agent prompt: prefer design_3d_with_grok for real engineering concepts

## Current Task
(none — restart stack; ask for thermal model to use Grok path)

## Next
1. Live test design_3d_with_grok (longer run; needs Grok + Blender)
2. Private host / phone when ready
3. Keynote (11c) optional

## How to test
```bash
cd ~/Desktop/JARVIS
./stop_jarvis.sh 2>/dev/null; ./start_jarvis.sh
# or: python3 wakeword.py
# "Hey Jarvis, how does a lunar hopper thermal system work — build the model"
```

## Blocked
(none)
