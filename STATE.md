# Loop State

## Last Completed
Milestone 7: Wake word — "Hey Jarvis" triggers the voice loop.
- wakeword.py: standalone loop using OpenWakeWord (hey_jarvis model)
- Listens continuously → detects wake word → records → transcribes →
  agent_loop → speaks reply → back to listening
- Uses claude-sonnet-4-6 for fast responses in voice mode
- requirements.txt updated with openwakeword>=0.6
- No API key needed (OpenWakeWord is fully open source)

## Verification Result
PASSED — 2026-06-21. User ran `python3 wakeword.py`, said "Hey Jarvis",
spoke a command, and Jarvis responded aloud. Full hands-free loop
confirmed working.

## All Milestones Complete
1. Text-only tool-calling loop — DONE
2. Real tools (time + weather) — DONE
3. Mac control (open apps) — DONE
4. Expanded Mac tools (volume, media, URLs, shortcuts) — DONE
5. Voice input (faster-whisper) — DONE
6. Voice output (ElevenLabs TTS) — DONE
7. Wake word (OpenWakeWord "Hey Jarvis") — DONE

## Current Task
All PROJECT.md milestones are complete. Jarvis is a working voice-controlled
AI assistant with Mac control capabilities.

## Blocked
(none)
