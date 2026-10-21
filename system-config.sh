#!/usr/bin/env bash
# Shared bootstrap: Python location is a launcher option; settings come from MySQL.

load_system_config() {
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
  [[ "$RUN_DIR" = /* ]] || RUN_DIR="$APP_ROOT/$RUN_DIR"
  [[ "$LOG_DIR" = /* ]] || LOG_DIR="$APP_ROOT/$LOG_DIR"
}
