#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
APP_ROOT="${APP_ROOT:-$SCRIPT_DIR}"
source "$APP_ROOT/system-config.sh"
load_system_config initialize
NPM_BIN="${NPM_BIN:-npm}"

mkdir -p "$RUN_DIR" "$LOG_DIR"

backend_pid="$RUN_DIR/backend.pid"
frontend_pid="$RUN_DIR/frontend.pid"
java_pid="$RUN_DIR/java-backend.pid"

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
  echo "Install Python 3 and dependencies: python3 -m pip install -r python-backend/requirements.txt" >&2
  exit 1
fi

# Old pollers must stop before the API begins owning background execution.
for legacy in application-worker ordinary-scheduler hotspot-scheduler planning-workflow-worker topic-label-worker topic-vector-worker account-vector-worker ai-preparation-worker matching-executor-worker; do
  if is_running "$RUN_DIR/$legacy.pid"; then
    echo "Legacy worker is still running: $legacy. Run ./stop.sh before upgrading." >&2
    exit 1
  fi
done

# The local Java shell owns the page entry. Host mode uses the bank's existing Java service.
if [[ "$JAVA_ACCESS_MODE" == "local_development" ]]; then
  JAVA_BIN="${JAVA_BIN:-java}"
  MVN_BIN="${MVN_BIN:-mvn}"
  if ! command -v "$JAVA_BIN" >/dev/null 2>&1; then
    echo "Java 8+ is required for the local Java subproject; install a JDK or set JAVA_BIN." >&2
    exit 1
  fi
  if ! is_running "$java_pid"; then
    if [[ "${BUILD_JAVA:-1}" == "1" || ! -f "$APP_ROOT/java-backend/target/planning-business.jar" ]]; then
      if ! command -v "$MVN_BIN" >/dev/null 2>&1; then
        echo "Maven is required to build java-backend; install it or set MVN_BIN." >&2
        exit 1
      fi
      "$MVN_BIN" -B -f "$APP_ROOT/java-backend/pom.xml" package -DskipTests
    fi
    (
      cd "$APP_ROOT/python-backend"
      "$PYTHON_BIN" -m app.java_development --output "$RUN_DIR/java-backend.properties"
    )
    (
      cd "$APP_ROOT/java-backend"
      exec "$JAVA_BIN" -jar target/planning-business.jar \
        "--spring.config.additional-location=file:$RUN_DIR/java-backend.properties"
    ) >"$LOG_DIR/java-backend.log" 2>&1 &
    echo $! >"$java_pid"
    echo "Java backend started (PID $(cat "$java_pid"))."
  else
    echo "Java backend is already running (PID $(cat "$java_pid"))."
  fi
fi

if is_running "$backend_pid"; then
  echo "Backend is already running (PID $(cat "$backend_pid"))."
else
  rm -f "$backend_pid"
  (
    cd "$APP_ROOT/python-backend"
    exec "$PYTHON_BIN" -m uvicorn app.main:app --host "$BACKEND_HOST" --port "$BACKEND_PORT"
  ) >"$LOG_DIR/backend.log" 2>&1 &
  echo $! >"$backend_pid"
  echo "Backend started (PID $(cat "$backend_pid"), http://${BACKEND_HOST}:${BACKEND_PORT})."
fi

if [[ "$BUILD_FRONTEND" == "1" || ! -f "$APP_ROOT/frontend/dist/index.html" ]]; then
  if ! command -v "$NPM_BIN" >/dev/null 2>&1; then
    echo "npm not found: $NPM_BIN" >&2
    exit 1
  fi
  (
    cd "$APP_ROOT/frontend"
    # The production build needs devDependencies such as typescript,
    # vue-tsc, Vite and @types/node. A server may already have a partial
    # node_modules directory from an --omit=dev install, so checking only
    # the directory is not enough.
    if [[ ! -d node_modules || ! -d node_modules/@types/node ]]; then
      "$NPM_BIN" ci --include=dev
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
    export BACKEND_HOST BACKEND_PORT FRONTEND_HOST FRONTEND_PORT JAVA_ACCESS_MODE JAVA_GATEWAY_URL
    exec "$NPM_BIN" run preview -- --host "$FRONTEND_HOST" --port "$FRONTEND_PORT"
  ) >"$LOG_DIR/frontend.log" 2>&1 &
  echo $! >"$frontend_pid"
  echo "Frontend started (PID $(cat "$frontend_pid"), http://${FRONTEND_HOST}:${FRONTEND_PORT})."
fi

echo "Logs: $LOG_DIR/java-backend.log, $LOG_DIR/backend.log, $LOG_DIR/frontend.log"
