# Loop State

## Last Completed
Milestone 9d: Local trust list + per-request routing. VERIFIED.
- Hard-edge tested (found + fixed a real miss: "what is it like outside"
  regex gap, now passing).
- llama3.1:8b baseline: 42/42 tool calls passed across hard edges:
    argument math (halfway->50, mute->0, max->100, "crank to 80")  6/6
    ambiguous targets (open the browser, pull up notes)            4/4
    unusual phrasings (barely hear it, what's it like outside)     5/5
    multi-tool (volume down and open Spotify) -> tools fire, but
      these correctly route CLOUD                                  5/5
- Router decision logic 23/23, with reasons logged:
    simple single-tool trusted        -> LOCAL  simple_intent:<tool>
    multi-tool / and|then|also         -> CLOUD  multi_tool_or_complex
    no intent matched                  -> CLOUD  no_simple_intent_matched
    tool not trusted locally           -> CLOUD  tool_not_trusted_locally
- Trust is PER-REQUEST: trusted tools go local only on simple single-tool
  requests; complex/multi-tool/ambiguous go cloud.
- LOCAL_TRUSTED_TOOLS editable in one place; remove a tool to demote it.

## Known edges (logged, not blocking)
- Multi-tool detection keys on conjunctions (and/then/also). A comma-only
  or oddly-phrased multi-step request could leak to local. Fails safe
  (does one action). Tighten later if real usage shows leakage.
- run_shortcut is in the trusted set and is the most powerful tool (can
  trigger any macOS Shortcut). CONFIRM it was exercised in the hard-edge
  tests. If it was not, treat it as "trusted pending its own test" and
  consider routing it cloud until verified.

## Verification Result
PASSED. Robust two-brain Jarvis with a tested, data-backed local trust
list and per-request routing.

## Current Task
Milestone 9e: Qwen A/B test (model comparison).
1. Record current state as the llama3.1:8b baseline (42/42 hard-edge,
   23/23 routing) — already in this file.
2. `ollama pull` a current Qwen tool-capable model. Before trusting it,
   run `ollama show <model>` and confirm "tools" is in Capabilities.
3. Swap OLLAMA_MODEL to the Qwen model (one-line change — no other code).
4. Re-run the SAME hard-edge + routing test suite unchanged.
5. Compare tool-call reliability head to head vs the 42/42 baseline.
6. Keep whichever model is more reliable. If they tie, prefer the one with
   lower latency / smaller footprint on this Mac.

VERIFY: show the Qwen tally next to the llama3.1:8b baseline on the SAME
tests, and state which model is selected and why. I will confirm.

NOTE: this is optional polish on an already-working system. Jarvis is fully
functional on llama3.1:8b right now.

## Blocked
(none)