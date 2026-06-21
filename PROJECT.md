# Jarvis — Project Spec

## Goal
A voice-controlled AI assistant. Talk to it; it responds in voice and can
control devices via tool calling.

## Tech Stack
- Backend: Python + FastAPI (orchestrator)
- Brain: Claude API with tool calling
- STT: faster-whisper (local)
- TTS: ElevenLabs
- Wake word: Porcupine
- Device control: Home Assistant REST API + local Python tools

## Milestones (in order — do not skip ahead)
1. Text-only Claude tool-calling loop with 2 stub tools (print only)
2. One real tool: get_time() + get_weather()
3. One Home Assistant tool: turn a light on/off
4. Voice input: faster-whisper transcribes mic → text
5. Voice output: ElevenLabs speaks Claude's reply
6. Wake word: "Jarvis" triggers the listen loop

## Definition of Done (per milestone)
A milestone is done only when it runs end-to-end and is verified by an
actual command/test, not by inspection.