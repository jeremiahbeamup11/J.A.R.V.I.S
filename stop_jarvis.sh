#!/usr/bin/env bash
# Stop processes started by start_jarvis.sh (pid files under data/run/).

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
RUN_DIR="$ROOT/data/run"

stop_one() {
  local name="$1"
  local pidfile="$RUN_DIR/${name}.pid"
  if [[ ! -f "$pidfile" ]]; then
    echo "[skip] $name (no pid file)"
    return 0
  fi
  local pid
  pid="$(cat "$pidfile" 2>/dev/null || true)"
  if [[ -z "$pid" ]]; then
    rm -f "$pidfile"
    echo "[skip] $name (empty pid)"
    return 0
  fi
  if kill -0 "$pid" 2>/dev/null; then
    echo "[stop] $name pid $pid"
    kill "$pid" 2>/dev/null || true
    sleep 0.4
    if kill -0 "$pid" 2>/dev/null; then
      kill -9 "$pid" 2>/dev/null || true
    fi
  else
    echo "[skip] $name (pid $pid not running)"
  fi
  rm -f "$pidfile"
}

echo "=== Jarvis stop ==="
# Order: voice first (holds mic), then tunnel, then API, then mac agent
for name in wakeword ngrok orchestrator mac_agent; do
  stop_one "$name"
done

# Optional: clear status
rm -f "$RUN_DIR/status.txt" 2>/dev/null || true
echo "Done. (Orphan processes on :8010/:8765 not in pid files are left alone.)"
