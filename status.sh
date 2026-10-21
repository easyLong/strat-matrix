#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="${APP_ROOT:-$SCRIPT_DIR}"
source "$APP_ROOT/system-config.sh"
load_system_config

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
if [[ "$TOPIC_VECTOR_WORKER_ENABLED" == "1" ]]; then
  check_process "Topic vector worker" "$RUN_DIR/topic-vector-worker.pid" || true
  expected=$((expected + 1))
fi
if [[ "$ACCOUNT_VECTOR_WORKER_ENABLED" == "1" ]]; then
  check_process "Account vector worker" "$RUN_DIR/account-vector-worker.pid" || true
  expected=$((expected + 1))
fi
if [[ "$AI_PREPARATION_WORKER_ENABLED" == "1" ]]; then
  check_process "AI preparation worker" "$RUN_DIR/ai-preparation-worker.pid" || true
  expected=$((expected + 1))
fi
if [[ "$MATCHING_EXECUTOR_WORKER_ENABLED" == "1" ]]; then
  check_process "Matching executor worker" "$RUN_DIR/matching-executor-worker.pid" || true
  expected=$((expected + 1))
fi
check_http "Backend" "http://${CHECK_HOST}:${BACKEND_PORT}/api/health" || true
check_http "Frontend" "http://${CHECK_HOST}:${FRONTEND_PORT}/" || true

if [[ "$running" -eq "$expected" && "$http_failures" -eq 0 ]]; then
  exit 0
fi
exit 1
