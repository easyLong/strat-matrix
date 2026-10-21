#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="${APP_ROOT:-$SCRIPT_DIR}"
source "$APP_ROOT/system-config.sh"
load_system_config
NPM_BIN="${NPM_BIN:-npm}"

mkdir -p "$RUN_DIR" "$LOG_DIR"

backend_pid="$RUN_DIR/backend.pid"
frontend_pid="$RUN_DIR/frontend.pid"
scheduler_pid="$RUN_DIR/ordinary-scheduler.pid"
hotspot_scheduler_pid="$RUN_DIR/hotspot-scheduler.pid"
topic_label_worker_pid="$RUN_DIR/topic-label-worker.pid"
topic_vector_worker_pid="$RUN_DIR/topic-vector-worker.pid"
account_vector_worker_pid="$RUN_DIR/account-vector-worker.pid"
ai_preparation_worker_pid="$RUN_DIR/ai-preparation-worker.pid"
matching_executor_worker_pid="$RUN_DIR/matching-executor-worker.pid"

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

if [[ "$TOPIC_LABEL_WORKER_ENABLED" == "1" ]]; then
  (
    cd "$APP_ROOT/backend"
    "$PYTHON_BIN" -m app.topic_label_worker --check-config
  )
fi

if [[ "$TOPIC_VECTOR_WORKER_ENABLED" == "1" && "$TOPIC_VECTOR_MODEL_CONFIGURED" != "1" ]]; then
  echo "Topic vector worker enabled, but TOPIC_VECTOR_MODEL_URL is empty." >&2
  exit 1
fi

if [[ "$ACCOUNT_VECTOR_WORKER_ENABLED" == "1" ]]; then
  (
    cd "$APP_ROOT/backend"
    "$PYTHON_BIN" -m app.account_vector_worker --check-config
  )
fi

if [[ "$AI_PREPARATION_WORKER_ENABLED" == "1" ]]; then
  (
    cd "$APP_ROOT/backend"
    "$PYTHON_BIN" -m app.ai_preparation_worker --check-config
  )
fi

if [[ "$MATCHING_EXECUTOR_WORKER_ENABLED" == "1" ]]; then
  (
    cd "$APP_ROOT/backend"
    "$PYTHON_BIN" -m app.matching_executor_worker --check-config
  )
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

if [[ "$TOPIC_VECTOR_WORKER_ENABLED" == "1" ]]; then
  if is_running "$topic_vector_worker_pid"; then
    echo "Topic vector worker is already running (PID $(cat "$topic_vector_worker_pid"))."
  else
    rm -f "$topic_vector_worker_pid"
    (
      cd "$APP_ROOT/backend"
      exec "$PYTHON_BIN" -m app.topic_vector_worker
    ) >"$LOG_DIR/topic-vector-worker.log" 2>&1 &
    echo $! >"$topic_vector_worker_pid"
    echo "Topic vector worker started (PID $(cat "$topic_vector_worker_pid"))."
  fi
fi

if [[ "$ACCOUNT_VECTOR_WORKER_ENABLED" == "1" ]]; then
  if is_running "$account_vector_worker_pid"; then
    echo "Account vector worker is already running (PID $(cat "$account_vector_worker_pid"))."
  else
    rm -f "$account_vector_worker_pid"
    (
      cd "$APP_ROOT/backend"
      exec "$PYTHON_BIN" -m app.account_vector_worker
    ) >"$LOG_DIR/account-vector-worker.log" 2>&1 &
    echo $! >"$account_vector_worker_pid"
    echo "Account vector worker started (PID $(cat "$account_vector_worker_pid"))."
  fi
fi

if [[ "$AI_PREPARATION_WORKER_ENABLED" == "1" ]]; then
  if is_running "$ai_preparation_worker_pid"; then
    echo "AI preparation worker is already running (PID $(cat "$ai_preparation_worker_pid"))."
  else
    rm -f "$ai_preparation_worker_pid"
    (
      cd "$APP_ROOT/backend"
      exec "$PYTHON_BIN" -m app.ai_preparation_worker
    ) >"$LOG_DIR/ai-preparation-worker.log" 2>&1 &
    echo $! >"$ai_preparation_worker_pid"
    echo "AI preparation worker started (PID $(cat "$ai_preparation_worker_pid"))."
  fi
fi

if [[ "$MATCHING_EXECUTOR_WORKER_ENABLED" == "1" ]]; then
  if is_running "$matching_executor_worker_pid"; then
    echo "Matching executor worker is already running (PID $(cat "$matching_executor_worker_pid"))."
  else
    rm -f "$matching_executor_worker_pid"
    (
      cd "$APP_ROOT/backend"
      exec "$PYTHON_BIN" -m app.matching_executor_worker
    ) >"$LOG_DIR/matching-executor-worker.log" 2>&1 &
    echo $! >"$matching_executor_worker_pid"
    echo "Matching executor worker started (PID $(cat "$matching_executor_worker_pid"))."
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

echo "Logs: $LOG_DIR/backend.log, $LOG_DIR/ordinary-scheduler.log, $LOG_DIR/hotspot-scheduler.log, $LOG_DIR/topic-label-worker.log, $LOG_DIR/topic-vector-worker.log, $LOG_DIR/account-vector-worker.log, $LOG_DIR/ai-preparation-worker.log, $LOG_DIR/matching-executor-worker.log and $LOG_DIR/frontend.log"
