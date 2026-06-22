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
3. Mac control agent: a safe listener on the Mac exposing open_app, plus
   the matching Jarvis tool. Verify Jarvis actually opens a Mac app.
4. Expand Mac tools: set_volume, run_shortcut, media controls.
5. Voice input: faster-whisper transcribes mic -> text.
6. Voice output: ElevenLabs speaks Jarvis's reply.
7. Wake word: "Jarvis" triggers the listen loop.
8. (LATER) ESP32 device bridge for custom hardware.
9. (PHASE 2) Optional local-brain tier on the Mac.

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
