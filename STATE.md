# Loop State

## Last Completed
Milestone 6: Voice output — ElevenLabs TTS speaks Claude's replies aloud.
- tts.py: ElevenLabs SDK generates speech, afplay plays it through speakers
- /voice endpoint now records → transcribes → agent_loop → speaks reply
- Uses eleven_turbo_v2_5 model, "Daniel" voice (configurable via env var)
- ELEVENLABS_API_KEY added to .env
- requirements.txt updated with elevenlabs>=1.0

## Verification Result
PASSED — 2026-06-21. User spoke "What's the weather in Houston?" and
Jarvis replied aloud: "It's 88 degrees and partly cloudy in Houston,
though with the humidity it feels more like 98. Pretty muggy out there."
Full pipeline: mic → faster-whisper → agent_loop → get_weather() →
ElevenLabs TTS → speakers.

## Current Task
Milestone 7 (from PROJECT.md): Wake word — "Jarvis" triggers the listen
loop via Porcupine. The assistant should idle until it hears "Jarvis",
then record/transcribe/respond/speak, then go back to listening for the
wake word.

## Blocked
(none)
