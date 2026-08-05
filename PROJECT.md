# Jarvis — Project Spec

## Goal
An always-on AI assistant that lives in my room, that I talk to, and that
can operate my MacBook and any tech I build. Named after Tony Stark's
JARVIS. The point is NOT smart-home lights — it's a personal assistant in
full control of my own devices.

## Core Mental Model (JARVIS pattern)
Jarvis is NOT a box. Jarvis is the always-on orchestrator loop + its tool
layer. The intelligence (brain) is non-localized; the hardware it controls
are interchangeable "bodies" that each expose safe endpoints the brain
calls. Keep the brain portable and the bodies swappable. Never hardcode
Jarvis to one machine.

## Architecture
- Brain (reasoning): Claude API — cloud. Phase 1 = cloud only.
- Orchestrator: Python + FastAPI tool-calling loop (the "self").
- Host (where the loop runs):
    - NOW (dev): the MacBook itself.
    - LATER (always-on): a dedicated box. Pi 5 DEFERRED — DRAM shortage
      pushed 8GB Pi 5 to ~$194 (Jun 2026). Reevaluate vs mini-PC / used
      Pi 4 / Pi Zero 2W once Jarvis works and prices settle.
- Bodies (things Jarvis controls), each = a box on the network exposing
  safe, enumerated endpoints that become tools in the loop:
    - MacBook control agent (PRIMARY — Milestone 3).
    - ESP32 device bridge (for hardware I build — LATER). Already owned:
      ESP32-WROOM-32 (FCC ID 2BB77-ESP32-32X). No purchase needed.

## Hardware Owned / Needed
- OWNED: ESP32-WROOM-32, Arduino Uno (backup), MacBook (Apple Silicon).
- BUY NOW: nothing.
- BUY SOON (only at voice milestone): USB mic (~$15-35). Mac built-in mic
  works for prototyping first.
- DEFERRED: always-on host box.

## Safety Model (non-negotiable)
Every Mac/device capability is an explicit, enumerated tool. Jarvis can do
ONLY what a tool exists for. Never give Jarvis a raw shell. Never add a
tool more dangerous than what I've explicitly approved. Destructive or
irreversible actions (delete, overwrite, send) require an explicit
approval step before execution.

## Phase 2 (recorded so we don't relitigate)
M-series MacBook becomes an OPTIONAL local-brain tier via Ollama, for
fast/private/offline simple commands, with cloud fallback when the Mac is
away. NOT Phase 1. Do not build the local brain until Jarvis works
end-to-end on the cloud brain.

## Milestones (in order — do not skip ahead)
1. [DONE] Text-only Claude tool-calling loop with 2 stub tools.
2. [DONE] Real tools: get_time() + get_weather(), with error handling.
3. [DONE] Mac control agent: open_app + matching Jarvis tool.
4. [DONE] Expand Mac tools: set_volume, run_shortcut, media, open_url.
5. [DONE] Voice input: faster-whisper transcribes mic -> text.
6. [DONE] Voice output: ElevenLabs speaks Jarvis's reply.
7. [DONE] Wake word: "Hey Jarvis" (OpenWakeWord).
8. (LATER) ESP32 device bridge for custom hardware.
9. [DONE / ACTIVE] Optional local-brain tier on the Mac (Ollama router).
10. [DONE] Grok Build engineering body (see Milestone 10 below).
11. [DONE 11a–11b] Workshop body — STL + Blender engine when installed.
12. [DONE 12a] Phone remote — iPhone text control over LAN (/phone).
13. [DONE 13a] Memory — session continuity + long-term notes.

## Definition of Done (per milestone)
Done only when it runs end-to-end and is verified by an actual command,
not by inspection. Milestone 3: saying "open Spotify" (or similar) to
Jarvis actually launches that app on the Mac, verified live.

## Phase 2 — Local Brain Tier (Milestones 9a–9e) [ACTIVE]
Goal: add a second brain running locally on the Mac via Ollama. Simple,
frequent commands route to the local model (fast/free/private/offline);
hard reasoning escalates to Claude. The ROUTING LAYER is the real project,
not the model itself.

Starting model: llama3.1:8b — chosen for easiest integration + most
documentation while building the routing layer for the first time.
Planned upgrade: A/B test a current Qwen (most reliable local tool-caller)
once the pipeline works; Ollama makes the swap a one-line change. Keep
whichever drops fewer tool calls on our actual tools.

CRITICAL: not every model build supports tool calling. Before relying on
any model, run `ollama show <model>` and confirm "tools" appears under
Capabilities. A model without it will reply with text instead of calling
tools and silently break routing.

Reality check: small local models are markedly worse at tool-calling than
Claude. Treat the local model as a fast FIRST RESPONDER for a small set of
well-defined commands, with Claude as the backstop — NOT a replacement.

Milestones:
- 9a: Install Ollama, pull llama3.1:8b, confirm it answers a plain prompt
      locally, AND confirm `ollama show llama3.1:8b` lists "tools".
- 9b: Add a second client in the orchestrator that sends a prompt to the
      local Ollama endpoint and returns the response. No routing yet —
      just prove the code can talk to both brains.
- 9c: Build the router: a simple, hardcoded list of "simple" intents that
      go local; everything else goes to Claude. Resist cleverness.
- 9d: Test tool-calling on the local model against our actual tools. Find
      which tools it calls reliably; route ONLY those to it.
- 9e: Graceful fallback: if the local model returns a malformed or
      low-confidence response, automatically retry on Claude.

Hardware note: runs on the MacBook, uses real RAM, warms it up. Local tier
only available when the Mac is awake + Ollama running. Mac away => cloud
only. Existing error-handling makes this graceful.

## Milestone 10 — Grok Build engineering body [DONE 10a–10c]
Goal: Jarvis can help build real software products by dispatching work to
open-source Grok Build, without giving Jarvis a raw shell.

Architecture fit:
- Claude remains the primary brain for mixed / ambiguous requests.
- Pure engineering intents route STRAIGHT to Grok Build (no Claude hop).
- Claude can still call `run_grok_build` as a tool when engineering is
  mixed with other assistant work.
- Ollama never receives `run_grok_build` (too long / high-stakes).

Safety:
- CWD must resolve under `GROK_BUILD_ALLOWLIST` (custom comma-separated
  list in `.env`). Outside the list → refuse.
- `mode=build` is allowed immediately on allowlisted paths (user policy).
- `mode=ask` is read-only (`--tools` allowlist of read/search tools).
- Invocation is a fixed `grok -p ...` command with enumerated flags only.

Config (see `.env.example`):
- `GROK_BUILD_ALLOWLIST` — required for any Grok work
- `GROK_BUILD_DEFAULT_CWD` — optional default project when path omitted
- `GROK_BIN`, `GROK_BUILD_MAX_TURNS`, `GROK_BUILD_TIMEOUT_SEC` — optional

Router targets: `local` | `grok` | `cloud`

Milestones:
- 10a: [DONE] Tool `run_grok_build(task, project_path, mode)` + JSON headless
- 10b: [DONE] Custom allowlist path validation
- 10c: [DONE] build vs ask modes; build auto-approved on allowlist
- 10d: [DONE] multi-turn sessions — per-project session registry +
      `continue_session` (default true) resumes via `grok -r <sessionId>`;
      `new_session` / `clear_grok_session` for fresh starts; HTTP
      `GET /grok/sessions`, `POST /grok/sessions/clear`
- 10e: (LATER) tighter engineering classifier / path disambiguation UI

## Milestone 11 — Workshop body (design + tangible models) [ACTIVE]
Goal: when you ask Jarvis *how to make X work* or to design a system, it
does not only talk — it opens Mac tools and produces work products you
can see (and later 3D-print / hand to CAD).

Pattern (multi-tool Claude orchestration, always cloud):
  reason → build_3d_model (STL) → write_design_brief → open_file / Finder
  → explain while pointing at the model

Geometry engines:
- **primitives** (always): pure-Python binary STL (box/cylinder/sphere/cone)
- **blender** (11b): when Blender.app installed — named + colorized parts,
  exports `.blend` + `.stl` + `.glb`, open in Blender for the “spin while
  explaining” loop. Headless only via fixed generated script (no raw shell).
- **auto** (default): blender if present, else primitives

Recommended install for this project: **Blender** (free, blender.org →
/Applications). Optional later (not required for 11b):
- CadQuery/build123d — true solid CAD + STEP (pip; no nice GUI alone)
- OpenSCAD — code-CAD parametric parts
Not recommended as primary for Jarvis automation: Fusion 360 / SolidWorks
(poor headless control for our loop).

Files land under WORKSHOP_DIR (default ~/Desktop/JARVIS/workshop).
HTTP: `GET /workshop/engines`

Safety:
- Artifacts only under workshop / OPEN_PATH_ALLOWLIST / Desktop/JARVIS
- mac_agent open_path + reveal_in_finder are enumerated endpoints
- No raw shell; Blender runs only our generated script + JSON spec

Milestones:
- 11a: [DONE] build_3d_model + brief + open_file/reveal + system-prompt workflow
- 11b: [DONE] Blender engine (auto detect), colorized named parts, .blend/.glb
- 11b2: [DONE] System templates (lunar_thermal, hopper_lander, propulsion,
      electronics_bay) + pipe/torus/panel/leg types + optional PNG render;
      agent must prefer templates over random free-form shapes
- 11c: (LATER) app-specific drivers (Keynote slides, Rotato, etc.)
- 11d: (LATER) voice-safe confirm before long workshop builds
- 11e: (LATER) CadQuery/STEP path if solid-model export is needed

## Milestone 12 — Phone remote (iPhone client) [DONE 12a]
Goal: control Jarvis from the iPhone while the Mac runs the brain + bodies.

- UI: `GET /phone` → `static/phone.html` (mobile Safari / Add to Home Screen)
- API: `/phone/api/status`, `/chat`, `/chat_cloud`, `/voice` (audio upload)
- Optional auth: `JARVIS_PHONE_TOKEN` (Bearer)
- **Home Wi‑Fi:** `http://<Mac-LAN-IP>:8010/phone` (text works)
- **Mic button:** requires HTTPS (iOS secure context). Use ngrok
  `ngrok http 8010` → `https://…/phone`, or keyboard dictation on HTTP.
- **Hotspot/car:** LAN IP often fails; use ngrok HTTPS.
- Speak-on-Mac toggle: phone can trigger ElevenLabs on the laptop speakers.

Milestones:
- 12a: [DONE] Phone UI + chat APIs + LAN verify + HTTPS mic guidance
- 12b: [DONE] `./start_jarvis.sh` full stack + `--phone-https` (ngrok)
      for iPhone site mic; `./stop_jarvis.sh` to tear down
- 12c: (LATER) push notifications / always-on host when Mac is elsewhere

## Ops — start / stop (12b)
```bash
cd ~/Desktop/JARVIS
./start_jarvis.sh                 # mac_agent + API + wakeword
./start_jarvis.sh --phone-https   # + ngrok HTTPS URL for iPhone 🎙
./stop_jarvis.sh
```
Logs/pids: `data/logs/`, `data/run/`.  
If ngrok fails with ERR_NGROK_334, stop the other tunnel (e.g. port 5001)
so the free account can bind a URL to Jarvis.

## Milestone 13 — Memory / continuity [DONE 13a]
Goal: Jarvis remembers the conversation and lasting facts so multi-turn
work (phone, wake word, API) does not reset every message.

Layers:
1. **Session** — rolling user/assistant turns on disk (`session.json`).
   Injected into Claude history; compact recent pairs for Ollama.
   Rotates after MEMORY_SESSION_IDLE_MINUTES idle.
2. **Long-term** — notes / preferences / active project (`long_term.json`).
   Tools: remember, recall, forget, set_active_project, set_preference.
3. **Auto context** — successful Grok/workshop paths set active_project;
   Grok routing falls back to active project path when none is spoken.

Storage: `MEMORY_DIR` (default `~/Desktop/JARVIS/data/memory/`). Not in git.

HTTP: `GET /memory`, `POST /memory/clear_session`,
`POST /memory/remember`, `POST /memory/recall`.

Milestones:
- 13a: [DONE] session + long-term + tools + agent injection + APIs
- 13b: (LATER) per-client session ids (phone vs wakeword vs API)
- 13c: (LATER) smarter auto-summaries of long sessions

## Roadmap priority (capability first)
1. [NEXT] Workshop model quality (templates + richer parts + layout rules)
2. ESP32 body (milestone 8) when hardware week returns
3. Per-client memory sessions (13b)
4. Grok session classifier polish (10e)
5. Persona / calling cosmetics (deferred)
