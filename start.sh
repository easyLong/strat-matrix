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
export BACKEND_PORT FRONTEND_PORT
if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON_BIN="$PYTHON_BIN"
elif [[ -x "$APP_ROOT/backend/.venv/bin/python" ]]; then
  PYTHON_BIN="$APP_ROOT/backend/.venv/bin/python"
else
  PYTHON_BIN="$(command -v python3 || command -v python || true)"
fi
NPM_BIN="${NPM_BIN:-npm}"
BUILD_FRONTEND="${BUILD_FRONTEND:-1}"
ORDINARY_SCHEDULER_ENABLED="${ORDINARY_SCHEDULER_ENABLED:-$(dotenv_value ORDINARY_SCHEDULER_ENABLED)}"
ORDINARY_SCHEDULER_ENABLED="${ORDINARY_SCHEDULER_ENABLED:-1}"
HOTSPOT_SCHEDULER_ENABLED="${HOTSPOT_SCHEDULER_ENABLED:-$(dotenv_value HOTSPOT_SCHEDULER_ENABLED)}"
HOTSPOT_SCHEDULER_ENABLED="${HOTSPOT_SCHEDULER_ENABLED:-1}"
TOPIC_LABEL_WORKER_ENABLED="${TOPIC_LABEL_WORKER_ENABLED:-$(dotenv_value TOPIC_LABEL_WORKER_ENABLED)}"
TOPIC_LABEL_WORKER_ENABLED="${TOPIC_LABEL_WORKER_ENABLED:-0}"
LABEL_MODEL_URL="${LABEL_MODEL_URL:-$(dotenv_value LABEL_MODEL_URL)}"
RUN_DIR="${RUN_DIR:-$APP_ROOT/run}"
LOG_DIR="${LOG_DIR:-$APP_ROOT/logs}"

mkdir -p "$RUN_DIR" "$LOG_DIR"

backend_pid="$RUN_DIR/backend.pid"
frontend_pid="$RUN_DIR/frontend.pid"
scheduler_pid="$RUN_DIR/ordinary-scheduler.pid"
hotspot_scheduler_pid="$RUN_DIR/hotspot-scheduler.pid"
topic_label_worker_pid="$RUN_DIR/topic-label-worker.pid"

is_running() {
  local pid_file="$1"
  [[ -s "$pid_file" ]] || return 1
  local pid
  pid="$(cat "$pid_file")"
  [[ "$pid" =~ ^[0-9]+$ ]] || return 1
  kill -0 "$pid" 2>/dev/null
}

if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
  echo "Python executable not found: ${PYTHON_BIN:-python3}" >&2
  echo "Install Python 3 and dependencies: python3 -m pip install -r backend/requirements.txt" >&2
  exit 1
fi

if [[ "$TOPIC_LABEL_WORKER_ENABLED" == "1" && -z "$LABEL_MODEL_URL" ]]; then
  echo "Topic label worker enabled, but LABEL_MODEL_URL is empty." >&2
  exit 1
fi

if is_running "$backend_pid"; then
  echo "Backend is already running (PID $(cat "$backend_pid"))."
else
  rm -f "$backend_pid"
  (
    cd "$APP_ROOT/backend"
    exec "$PYTHON_BIN" -m uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT"
  ) >"$LOG_DIR/backend.log" 2>&1 &
  echo $! >"$backend_pid"
  echo "Backend started (PID $(cat "$backend_pid"), http://${BACKEND_HOST}:${BACKEND_PORT})."
fi

if [[ "$ORDINARY_SCHEDULER_ENABLED" == "1" ]]; then
  if is_running "$scheduler_pid"; then
    echo "Ordinary scheduler is already running (PID $(cat "$scheduler_pid"))."
  else
    rm -f "$scheduler_pid"
    (
      cd "$APP_ROOT/backend"
      exec "$PYTHON_BIN" -m app.ordinary_scheduler
    ) >"$LOG_DIR/ordinary-scheduler.log" 2>&1 &
    echo $! >"$scheduler_pid"
    echo "Ordinary scheduler started (PID $(cat "$scheduler_pid"), Asia/Shanghai)."
  fi
fi

if [[ "$HOTSPOT_SCHEDULER_ENABLED" == "1" ]]; then
  if is_running "$hotspot_scheduler_pid"; then
    echo "Hotspot scheduler is already running (PID $(cat "$hotspot_scheduler_pid"))."
  else
    rm -f "$hotspot_scheduler_pid"
    (
      cd "$APP_ROOT/backend"
      exec "$PYTHON_BIN" -m app.hotspot_scheduler
    ) >"$LOG_DIR/hotspot-scheduler.log" 2>&1 &
    echo $! >"$hotspot_scheduler_pid"
    echo "Hotspot scheduler started (PID $(cat "$hotspot_scheduler_pid"), Asia/Shanghai)."
  fi
fi

if [[ "$TOPIC_LABEL_WORKER_ENABLED" == "1" ]]; then
  if is_running "$topic_label_worker_pid"; then
    echo "Topic label worker is already running (PID $(cat "$topic_label_worker_pid"))."
  else
    rm -f "$topic_label_worker_pid"
    (
      cd "$APP_ROOT/backend"
      exec "$PYTHON_BIN" -m app.topic_label_worker
    ) >"$LOG_DIR/topic-label-worker.log" 2>&1 &
    echo $! >"$topic_label_worker_pid"
    echo "Topic label worker started (PID $(cat "$topic_label_worker_pid"))."
  fi
fi

if [[ "$BUILD_FRONTEND" == "1" || ! -f "$APP_ROOT/frontend/dist/index.html" ]]; then
  if ! command -v "$NPM_BIN" >/dev/null 2>&1; then
    echo "npm not found: $NPM_BIN" >&2
    exit 1
  fi
  (
    cd "$APP_ROOT/frontend"
    if [[ ! -d node_modules ]]; then
      "$NPM_BIN" ci
    fi
    "$NPM_BIN" run build
  )
fi

if is_running "$frontend_pid"; then
  echo "Frontend is already running (PID $(cat "$frontend_pid"))."
else
  rm -f "$frontend_pid"
  (
    cd "$APP_ROOT/frontend"
    exec "$NPM_BIN" run preview -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
  ) >"$LOG_DIR/frontend.log" 2>&1 &
  echo $! >"$frontend_pid"
  echo "Frontend started (PID $(cat "$frontend_pid"), http://${FRONTEND_HOST}:${FRONTEND_PORT})."
fi

echo "Logs: $LOG_DIR/backend.log, $LOG_DIR/ordinary-scheduler.log, $LOG_DIR/hotspot-scheduler.log, $LOG_DIR/topic-label-worker.log and $LOG_DIR/frontend.log"
