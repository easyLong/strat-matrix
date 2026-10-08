#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="${APP_ROOT:-$SCRIPT_DIR}"
ENV_FILE="${ENV_FILE:-$APP_ROOT/.env}"

dotenv_value() {
  local key="$1"
  [[ -f "$ENV_FILE" ]] || return 0
  awk -F= -v key="$key" '$1 == key { value=$0; sub(/^[^=]*=/, "", value); gsub(/^"|"$/, "", value); print value; exit }' "$ENV_FILE"
}

BACKEND_HOST="${BACKEND_HOST:-$(dotenv_value BACKEND_HOST)}"
BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-$(dotenv_value BACKEND_PORT)}"
BACKEND_PORT="${BACKEND_PORT:-6930}"
FRONTEND_HOST="${FRONTEND_HOST:-$(dotenv_value FRONTEND_HOST)}"
FRONTEND_HOST="${FRONTEND_HOST:-127.0.0.1}"
FRONTEND_PORT="${FRONTEND_PORT:-$(dotenv_value FRONTEND_PORT)}"
FRONTEND_PORT="${FRONTEND_PORT:-930}"
CHECK_HOST="${CHECK_HOST:-127.0.0.1}"
ORDINARY_SCHEDULER_ENABLED="${ORDINARY_SCHEDULER_ENABLED:-$(dotenv_value ORDINARY_SCHEDULER_ENABLED)}"
ORDINARY_SCHEDULER_ENABLED="${ORDINARY_SCHEDULER_ENABLED:-1}"
HOTSPOT_SCHEDULER_ENABLED="${HOTSPOT_SCHEDULER_ENABLED:-$(dotenv_value HOTSPOT_SCHEDULER_ENABLED)}"
HOTSPOT_SCHEDULER_ENABLED="${HOTSPOT_SCHEDULER_ENABLED:-1}"
TOPIC_LABEL_WORKER_ENABLED="${TOPIC_LABEL_WORKER_ENABLED:-$(dotenv_value TOPIC_LABEL_WORKER_ENABLED)}"
TOPIC_LABEL_WORKER_ENABLED="${TOPIC_LABEL_WORKER_ENABLED:-0}"
RUN_DIR="${RUN_DIR:-$APP_ROOT/run}"

running=0
http_failures=0

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
  http_failures=$((http_failures + 1))
  return 1
}

check_process "Backend" "$RUN_DIR/backend.pid" || true
check_process "Frontend" "$RUN_DIR/frontend.pid" || true
expected=2
if [[ "$ORDINARY_SCHEDULER_ENABLED" == "1" ]]; then
  check_process "Ordinary scheduler" "$RUN_DIR/ordinary-scheduler.pid" || true
  expected=$((expected + 1))
fi
if [[ "$HOTSPOT_SCHEDULER_ENABLED" == "1" ]]; then
  check_process "Hotspot scheduler" "$RUN_DIR/hotspot-scheduler.pid" || true
  expected=$((expected + 1))
fi
if [[ "$TOPIC_LABEL_WORKER_ENABLED" == "1" ]]; then
  check_process "Topic label worker" "$RUN_DIR/topic-label-worker.pid" || true
  expected=$((expected + 1))
fi
check_http "Backend" "http://${CHECK_HOST}:${BACKEND_PORT}/api/health" || true
check_http "Frontend" "http://${CHECK_HOST}:${FRONTEND_PORT}/" || true

if [[ "$running" -eq "$expected" && "$http_failures" -eq 0 ]]; then
  exit 0
fi
exit 1
