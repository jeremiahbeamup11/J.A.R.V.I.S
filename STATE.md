# Loop State

## Last Completed
Milestone 9c: Router + local tool-calling. VERIFIED.
- Intent-based router decides LOCAL vs CLOUD before calling any model
- Local brain (Ollama llama3.1:8b) now has full tool-calling: schemas
  converted to OpenAI format, tool results fed back via run_tool()
- Resilience fallback: cloud failure → local, local failure → cloud
- Logging on every request: routed_to, reason, fallback status
- /chat uses router, /chat_cloud and /chat_local bypass for debugging
- /voice endpoint also uses the router

## Verification Result
PASSED — 2026-06-22. All three local tool-calling tests confirmed
real-world effects:
1. "What time is it?" → local → get_time() → returned actual current time
2. "Set volume to 30" → local → set_volume(30) → Mac volume actually changed
3. "Open Notes" → local → control_mac_app("Notes") → Notes app actually opened
All three routed to local brain, all three executed tools correctly.

## Current Task
Milestone 9c complete. Commit and push, then await user direction for
next milestone.

## Notes / Decisions
- llama3.1:8b confirmed working for tool-calling via Ollama
- Model swap (Qwen A/B test) deferred; one-line change via OLLAMA_MODEL
- Local tier requires Mac awake + Ollama running; cloud is always-on backstop

## Blocked
(none)
