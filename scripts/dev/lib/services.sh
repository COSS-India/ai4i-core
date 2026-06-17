#!/usr/bin/env bash

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/pids.sh"

VENV_DIR="$ROOT_DIR/.venv"

# Start one backend under uvicorn in the background, hot-reload on. Idempotent:
# if a live PID is already recorded, it's reused rather than double-started.
_start_service() {

    local name="$1"
    local dir="$2"
    local app="$3"
    local port="$4"

    if is_running "$name"; then
        ok "$name already running (PID=$(read_pid "$name")) — skipping"
        return 0
    fi

    log "Starting $name on :$port..."

    (
        cd "$ROOT_DIR/$dir"
        # shellcheck disable=SC1091
        source "$VENV_DIR/bin/activate"
        # exec so $! is the uvicorn PID itself (kept accurate for stop).
        exec uvicorn "$app" --host 0.0.0.0 --port "$port" --reload
    ) > "$LOG_DIR/$name.log" 2>&1 &

    local pid=$!

    # Detach from the shell's job table so the service survives terminal close
    # (nohup would keep itself as the parent and break PID tracking; disown
    # keeps $pid pointing at uvicorn itself).
    disown "$pid" 2>/dev/null || true

    save_pid "$name" "$pid"
    track_started "$name"

    ok "$name started (PID=$pid, log: $LOG_DIR/$name.log)"
}

start_all_services() {

    [[ -d "$VENV_DIR" ]] \
        || die "Shared venv missing at $VENV_DIR — run setup_venv first"

    _start_service auth-service           services/auth-service           app.main:app 8081
    _start_service platform-core-service  services/platform-core-service  app.main:app 8095
    _start_service inference-service      services/inference-service      main:app     8090

    ok "Backend services started"
}

stop_all_services() {

    kill_service auth-service
    kill_service platform-core-service
    kill_service inference-service

    ok "Backend services stopped"
}
