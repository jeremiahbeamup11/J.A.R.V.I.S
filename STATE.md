# Loop State

## Context
Ops + phone HTTPS path landed. Next major depth item is workshop model
quality (templates / richer thermal assemblies), per user plan.

## Last Completed
1. **Full-stack start/stop scripts (ops)**
   - `./start_jarvis.sh` — mac_agent (:8765) + orchestrator (:8010) + wakeword
   - `./stop_jarvis.sh` — stops pid-file managed processes
   - Flags: `--phone-https`, `--no-voice`, `--no-mac`
   - Logs: `data/logs/`  Pids: `data/run/`

2. **Phone mic HTTPS (12b)**
   - `./start_jarvis.sh --phone-https` starts ngrok (web-addr :4042)
   - Prints `https://…/phone` for Safari mic (secure context)
   - Phone UI banner + status hints updated to use the start script
   - LAN `http://…/phone` still fine for **text** + keyboard dictation

## Current Task
(none)

## Next (user-agreed order)
1. ~~Start script + full stack~~ DONE
2. ~~Phone mic HTTPS (12b)~~ DONE
3. **Upgrade workshop models** — templates, richer parts, layout rules,
   optional still-render (so thermal systems look like systems)

## How to run daily
```bash
cd ~/Desktop/JARVIS
./start_jarvis.sh
# Room: "Hey Jarvis …"

# iPhone mic:
./stop_jarvis.sh   # if already up without tunnel
./start_jarvis.sh --phone-https
# open the printed https://…/phone URL on the phone
```

## Note
If ngrok ERR_NGROK_334: another ngrok is using the free reserved domain
(often `ngrok http 5001`). Stop that process, then retry --phone-https.

## Blocked
(none)
