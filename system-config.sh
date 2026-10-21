#!/usr/bin/env bash
# Shared bootstrap: launcher defaults are in code; credentials stay in MySQL.

load_system_config() {
  local matching_worker_override_set="${MATCHING_EXECUTOR_WORKER_ENABLED+x}"
  local matching_worker_override="${MATCHING_EXECUTOR_WORKER_ENABLED:-}"
  if [[ -z "${PYTHON_BIN:-}" ]]; then
    if [[ -x "$APP_ROOT/backend/.venv/bin/python" ]]; then
      PYTHON_BIN="$APP_ROOT/backend/.venv/bin/python"
    else
      PYTHON_BIN="$(command -v python3 || command -v python || true)"
    fi
  fi
  if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
    echo "Python executable not found; install backend requirements first." >&2
    return 1
  fi
  local settings
  settings="$(cd "$APP_ROOT/backend" && "$PYTHON_BIN" -m app.system_config launch-shell)" || return 1
  # The CLI emits a fixed allowlist of non-secret names, with shlex-quoted values.
  eval "$settings"
  if [[ "$matching_worker_override_set" == "x" ]]; then
    MATCHING_EXECUTOR_WORKER_ENABLED="$matching_worker_override"
  fi
  if [[ "$MATCHING_EXECUTOR_WORKER_ENABLED" != "0" \
      && "$MATCHING_EXECUTOR_WORKER_ENABLED" != "1" ]]; then
    echo "MATCHING_EXECUTOR_WORKER_ENABLED must be 0 or 1" >&2
    return 1
  fi
  [[ "$RUN_DIR" = /* ]] || RUN_DIR="$APP_ROOT/$RUN_DIR"
  [[ "$LOG_DIR" = /* ]] || LOG_DIR="$APP_ROOT/$LOG_DIR"
}
