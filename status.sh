#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="${APP_ROOT:-$SCRIPT_DIR}"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
RUN_DIR="${RUN_DIR:-$APP_ROOT/run}"

running=0

check_process() {
  local name="$1"
  local pid_file="$2"
  if [[ -s "$pid_file" ]]; then
    local pid
    pid="$(cat "$pid_file")"
    if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
      echo "$name: running (PID $pid)"
      running=$((running + 1))
      return 0
    fi
  fi
  echo "$name: stopped"
  return 1
}

check_http() {
  local name="$1"
  local url="$2"
  if command -v curl >/dev/null 2>&1 && curl --silent --show-error --max-time 3 --fail "$url" >/dev/null; then
    echo "$name HTTP: healthy ($url)"
    return 0
  fi
  echo "$name HTTP: unavailable ($url)"
  return 1
}

check_process "Backend" "$RUN_DIR/backend.pid" || true
check_process "Frontend" "$RUN_DIR/frontend.pid" || true
check_http "Backend" "http://${BACKEND_HOST}:${BACKEND_PORT}/api/health" || true
check_http "Frontend" "http://${FRONTEND_HOST}:${FRONTEND_PORT}/" || true

if [[ "$running" -eq 2 ]]; then
  exit 0
fi
exit 1
