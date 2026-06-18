#!/usr/bin/env bash

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
source "$(dirname "${BASH_SOURCE[0]}")/pids.sh"

FRONTEND_DIR="$ROOT_DIR/frontend/simple-ui"

# Start the simple-ui Next.js dev server in the background. Only runs when the
# resolved profile asks for it (START_FRONTEND) and AI4I_SKIP_FRONTEND is unset.
# Idempotent: a live simple-ui PID is reused, so re-running `up frontend` after
# `up core` only fills in this one missing piece.
start_frontend() {

    if [[ "${START_FRONTEND:-false}" != "true" ]]; then
        return 0
    fi

    if [[ -n "${AI4I_SKIP_FRONTEND:-}" ]]; then
        warn "AI4I_SKIP_FRONTEND set — skipping simple-ui"
        return 0
    fi

    if is_running simple-ui; then
        ok "simple-ui already running (PID=$(read_pid simple-ui)) — skipping"
        return 0
    fi

    require_dir "$FRONTEND_DIR"

    local logfile="$LOG_DIR/simple-ui.log"
    : > "$logfile"

    log "Installing simple-ui dependencies (npm install, idempotent)..."
    ( cd "$FRONTEND_DIR" && npm install ) >> "$logfile" 2>&1 \
        || die "npm install failed (see $logfile)"

    log "Starting simple-ui on :3000..."
    (
        cd "$FRONTEND_DIR"
        exec npm run dev
    ) >> "$logfile" 2>&1 &

    local pid=$!

    disown "$pid" 2>/dev/null || true

    save_pid simple-ui "$pid"
    track_started simple-ui

    ok "simple-ui started (PID=$pid, log: $logfile)"
}

stop_frontend() {

    kill_service simple-ui
}
