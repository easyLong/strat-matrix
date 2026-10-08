#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="${APP_ROOT:-$SCRIPT_DIR}"
RUN_DIR="${RUN_DIR:-$APP_ROOT/run}"

stop_one() {
  local name="$1"
  local pid_file="$2"
  if [[ ! -s "$pid_file" ]]; then
    echo "$name is not running."
    return 0
  fi
  local pid
  pid="$(cat "$pid_file")"
  if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    for _ in {1..20}; do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.25
    done
    if kill -0 "$pid" 2>/dev/null; then
      kill -TERM "$pid" 2>/dev/null || true
    fi
    echo "$name stopped (PID $pid)."
  else
    echo "$name process is gone; removing stale PID file."
  fi
  rm -f "$pid_file"
}

stop_one "Topic label worker" "$RUN_DIR/topic-label-worker.pid"
stop_one "Hotspot scheduler" "$RUN_DIR/hotspot-scheduler.pid"
stop_one "Ordinary scheduler" "$RUN_DIR/ordinary-scheduler.pid"
stop_one "Frontend" "$RUN_DIR/frontend.pid"
stop_one "Backend" "$RUN_DIR/backend.pid"
