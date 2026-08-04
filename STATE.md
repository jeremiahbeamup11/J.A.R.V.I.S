# Loop State

## Context
Milestone 11b — richer workshop via Blender when installed. User is about
to download Blender (recommended primary tool for design visualization).

## Recommendation given to user
- **Download Blender** (blender.org → drag to /Applications) — best for
  “open the app, spin color-coded system, explain parts by name.”
- Optional later: CadQuery (STEP solids) or OpenSCAD (code-CAD). Not required now.
- Do not need Fusion as primary for Jarvis automation.

## Last Completed
Milestone 11b code (works with or without Blender):

- `tools/blender_engine.py` — detect Blender, headless build script,
  export .blend + .stl + .glb, named materials/colors
- `tools/workshop.py` — `engine=auto|blender|primitives`, `open_after`,
  `workshop_engines()`
- Tool schemas + agent prompt (open Blender when blend_path exists)
- `GET /workshop/engines`
- PROJECT.md / .env.example (BLENDER_BIN)

Without Blender: auto falls back to primitives (existing behavior).
With Blender: colorized assemblies open in Blender.app.

## Current Task
User installs Blender → live verify `GET /workshop/engines` shows available,
then design question builds a .blend and opens it.

## Next after Blender verify
1. Phone mic HTTPS (12b)
2. CadQuery/STEP (11e) only if needed
3. ESP32 / Keynote drivers later

## Blocked
Waiting on Blender install for live Blender path verify (primitives path OK).
