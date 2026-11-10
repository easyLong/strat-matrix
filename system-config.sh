#!/usr/bin/env bash
# Shared bootstrap: launcher defaults are in code; credentials stay in MySQL.

load_system_config() {
  if [[ -z "${PYTHON_BIN:-}" ]]; then
    if [[ -x "$APP_ROOT/python-backend/.venv/bin/python" ]]; then
      PYTHON_BIN="$APP_ROOT/python-backend/.venv/bin/python"
    else
      PYTHON_BIN="$(command -v python3 || command -v python || true)"
    fi
  fi
  if [[ -z "$PYTHON_BIN" || ! -x "$PYTHON_BIN" ]]; then
    echo "Python executable not found; install python-backend requirements first." >&2
    return 1
  fi
  local settings
  if [[ "${1:-}" == "initialize" ]]; then
    (cd "$APP_ROOT/python-backend" && "$PYTHON_BIN" -m app.content_planning.init_shared_workflow_db) || return 1
  fi
  settings="$(cd "$APP_ROOT/python-backend" && "$PYTHON_BIN" -m app.content_planning.system_config launch-shell)" || return 1
  # The CLI emits a fixed allowlist of non-secret names, with shlex-quoted values.
  eval "$settings"
  [[ "$RUN_DIR" = /* ]] || RUN_DIR="$APP_ROOT/$RUN_DIR"
  [[ "$LOG_DIR" = /* ]] || LOG_DIR="$APP_ROOT/$LOG_DIR"
}
