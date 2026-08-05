#!/usr/bin/env bash
# Start the full Jarvis stack: mac_agent + orchestrator + wake word.
# Optional: --phone-https  (ngrok tunnel for iPhone mic over HTTPS)
#
# Usage:
#   ./start_jarvis.sh
#   ./start_jarvis.sh --phone-https
#   ./start_jarvis.sh --no-voice
#   ./start_jarvis.sh --no-mac
#   JARVIS_PORT=8010 ./start_jarvis.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PORT="${JARVIS_PORT:-8010}"
MAC_PORT="${MAC_AGENT_PORT:-8765}"
PYTHON="${PYTHON:-python3}"
RUN_DIR="$ROOT/data/run"
LOG_DIR="$ROOT/data/logs"
mkdir -p "$RUN_DIR" "$LOG_DIR"

WITH_VOICE=1
WITH_MAC=1
PHONE_HTTPS=0

for arg in "$@"; do
  case "$arg" in
    --phone-https|--ngrok) PHONE_HTTPS=1 ;;
    --no-voice) WITH_VOICE=0 ;;
    --no-mac) WITH_MAC=0 ;;
    --help|-h)
      cat <<EOF
Jarvis full-stack starter

  ./start_jarvis.sh              mac_agent + API :$PORT + wakeword
  ./start_jarvis.sh --phone-https  same + ngrok HTTPS for iPhone mic
  ./start_jarvis.sh --no-voice   skip wakeword
  ./start_jarvis.sh --no-mac     skip mac_agent

Env:
  JARVIS_PORT=8010
  MAC_AGENT_PORT=8765
  PYTHON=python3
EOF
      exit 0
      ;;
    *)
      echo "Unknown option: $arg (try --help)" >&2
      exit 1
      ;;
  esac
done

# Load .env if present (export keys for child processes)
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

is_listening() {
  local port="$1"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

pid_alive() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

start_bg() {
  local name="$1"
  local pidfile="$RUN_DIR/${name}.pid"
  local logfile="$LOG_DIR/${name}.log"
  shift

  if [[ -f "$pidfile" ]]; then
    local old
    old="$(cat "$pidfile" 2>/dev/null || true)"
    if pid_alive "$old"; then
      echo "[skip] $name already running (pid $old)"
      return 0
    fi
    rm -f "$pidfile"
  fi

  echo "[start] $name → log $logfile"
  nohup "$@" >>"$logfile" 2>&1 &
  local pid=$!
  echo "$pid" >"$pidfile"
  sleep 0.4
  if pid_alive "$pid"; then
    echo "[ok]   $name pid $pid"
  else
    echo "[fail] $name died — see $logfile" >&2
    return 1
  fi
}

echo "=== Jarvis start ==="
echo "root: $ROOT"
echo "port: $PORT  mac: $MAC_PORT"

# --- Mac agent ---
if [[ "$WITH_MAC" -eq 1 ]]; then
  if is_listening "$MAC_PORT"; then
    echo "[skip] mac_agent already listening on :$MAC_PORT"
  else
    start_bg mac_agent \
      "$PYTHON" -m uvicorn mac_agent.mac_agent:app \
      --host 127.0.0.1 --port "$MAC_PORT"
  fi
else
  echo "[skip] mac_agent (--no-mac)"
fi

# --- Orchestrator (brain + phone UI) ---
if is_listening "$PORT"; then
  echo "[skip] orchestrator already listening on :$PORT"
else
  start_bg orchestrator \
    "$PYTHON" -m uvicorn main:app \
    --host 0.0.0.0 --port "$PORT"
fi

# Wait briefly for health
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if curl -sf "http://127.0.0.1:${PORT}/" >/dev/null 2>&1; then
    break
  fi
  sleep 0.3
done

if curl -sf "http://127.0.0.1:${PORT}/" >/dev/null 2>&1; then
  echo "[ok]   orchestrator health OK"
else
  echo "[warn] orchestrator not healthy yet — check $LOG_DIR/orchestrator.log"
fi

# --- Wake word ---
if [[ "$WITH_VOICE" -eq 1 ]]; then
  start_bg wakeword "$PYTHON" wakeword.py
else
  echo "[skip] wakeword (--no-voice)"
fi

# --- LAN URL ---
LAN_IP=""
if command -v ipconfig >/dev/null 2>&1; then
  LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || true)"
fi
if [[ -z "$LAN_IP" ]]; then
  LAN_IP="$(python3 - <<'PY'
import socket
try:
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    s.connect(("8.8.8.8",80))
    print(s.getsockname()[0])
    s.close()
except Exception:
    print("")
PY
)"
fi

PHONE_HTTP="http://${LAN_IP:-<Mac-LAN-IP>}:${PORT}/phone"

# --- Optional ngrok for phone HTTPS mic ---
PHONE_HTTPS_URL=""
if [[ "$PHONE_HTTPS" -eq 1 ]]; then
  if ! command -v ngrok >/dev/null 2>&1; then
    echo "[warn] ngrok not found — install ngrok or skip --phone-https"
  else
    # Free account often has one reserved domain already online on another port.
    # Prefer a random URL via --url= empty is invalid; use plain `ngrok http PORT`
    # If that fails due to reserved domain conflict, user must free the other tunnel.
    if [[ -f "$RUN_DIR/ngrok.pid" ]] && pid_alive "$(cat "$RUN_DIR/ngrok.pid")"; then
      echo "[skip] ngrok already running (pid $(cat "$RUN_DIR/ngrok.pid"))"
    else
      echo "[start] ngrok http $PORT (HTTPS for iPhone mic)"
      # Local API on 4042 so we don't clash with an existing ngrok on 4040
      nohup ngrok http "$PORT" --web-addr=127.0.0.1:4042 \
        >>"$LOG_DIR/ngrok.log" 2>&1 &
      echo $! >"$RUN_DIR/ngrok.pid"
      sleep 2
    fi

    # Try both common local APIs
    for api in 4042 4040; do
      PHONE_HTTPS_URL="$(
        curl -sf "http://127.0.0.1:${api}/api/tunnels" 2>/dev/null \
          | python3 -c "
import sys, json
try:
    d=json.load(sys.stdin)
except Exception:
    sys.exit(0)
for t in d.get('tunnels') or []:
    u=t.get('public_url') or ''
    addr=(t.get('config') or {}).get('addr') or ''
    if u.startswith('https://') and ('$PORT' in addr or addr.endswith(':$PORT') or 'localhost:$PORT' in addr or '127.0.0.1:$PORT' in addr):
        print(u)
        break
    if u.startswith('https://') and '$PORT' in str(t):
        print(u)
        break
" 2>/dev/null || true
      )"
      [[ -n "$PHONE_HTTPS_URL" ]] && break
    done

    # Fallback: any https tunnel on 4042
    if [[ -z "$PHONE_HTTPS_URL" ]]; then
      PHONE_HTTPS_URL="$(
        curl -sf "http://127.0.0.1:4042/api/tunnels" 2>/dev/null \
          | python3 -c "
import sys, json
try:
    d=json.load(sys.stdin)
    for t in d.get('tunnels') or []:
        u=t.get('public_url') or ''
        if u.startswith('https://'):
            print(u); break
except Exception:
    pass
" 2>/dev/null || true
      )"
    fi

    if [[ -n "$PHONE_HTTPS_URL" ]]; then
      echo "[ok]   ngrok: $PHONE_HTTPS_URL"
    else
      echo "[warn] ngrok started but public URL not found yet."
      echo "       Check $LOG_DIR/ngrok.log or http://127.0.0.1:4042"
      echo "       If you see ERR_NGROK_334, stop the other ngrok (e.g. port 5001) first."
    fi
  fi
fi

# --- Write status snapshot ---
cat >"$RUN_DIR/status.txt" <<EOF
started: $(date -u +%Y-%m-%dT%H:%M:%SZ)
port: $PORT
mac_port: $MAC_PORT
phone_http: $PHONE_HTTP
phone_https: ${PHONE_HTTPS_URL:-}
voice: $WITH_VOICE
mac: $WITH_MAC
EOF

echo ""
echo "=== Jarvis is up ==="
echo "  Room voice:   say \"Hey Jarvis\" (wakeword log: $LOG_DIR/wakeword.log)"
echo "  Text API:     http://127.0.0.1:${PORT}/"
echo "  Phone (LAN):  $PHONE_HTTP"
echo "                (text works; iPhone site-mic needs HTTPS)"
if [[ -n "$PHONE_HTTPS_URL" ]]; then
  echo "  Phone (HTTPS mic): ${PHONE_HTTPS_URL}/phone"
  echo "                Safari → Allow microphone → use 🎙"
elif [[ "$PHONE_HTTPS" -eq 1 ]]; then
  echo "  Phone HTTPS:  not ready — see ngrok log / free conflicting tunnel"
else
  echo "  Phone mic:    re-run with  ./start_jarvis.sh --phone-https"
fi
echo "  Memory:       http://127.0.0.1:${PORT}/memory"
echo "  Engines:      http://127.0.0.1:${PORT}/workshop/engines"
echo "  Stop:         ./stop_jarvis.sh"
echo "  Logs:         $LOG_DIR/"
echo ""
