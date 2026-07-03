#!/usr/bin/env bash

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

pid_file() {

    local service="$1"

    echo "$RUN_DIR/${service}.pid"
}

save_pid() {

    local service="$1"
    local pid="$2"

    echo "$pid" > "$(pid_file "$service")"
}

read_pid() {

    local service="$1"

    local file
    file=$(pid_file "$service")

    [[ -f "$file" ]] || return 1

    cat "$file"
}

is_running() {

    local service="$1"

    local pid

    pid=$(read_pid "$service") || return 1

    kill -0 "$pid" >/dev/null 2>&1
}

# SIGTERM, wait up to 10s for a graceful exit, then SIGKILL survivors.
kill_service() {

    local service="$1"

    if ! is_running "$service"; then
        rm -f "$(pid_file "$service")"
        return 0
    fi

    local pid
    pid=$(read_pid "$service")

    log "Stopping $service (PID=$pid)..."

    kill "$pid" >/dev/null 2>&1 || true

    local waited=0
    while (( waited < 10 )); do

        kill -0 "$pid" >/dev/null 2>&1 || break

        sleep 1
        waited=$((waited + 1))
    done

    if kill -0 "$pid" >/dev/null 2>&1; then
        warn "$service did not stop within 10s — sending SIGKILL"
        kill -9 "$pid" >/dev/null 2>&1 || true
    fi

    rm -f "$(pid_file "$service")"

    ok "Stopped $service"
}

cleanup_dead_pids() {

    for pidfile in "$RUN_DIR"/*.pid; do

        [[ -e "$pidfile" ]] || continue

        pid=$(cat "$pidfile")

        if ! kill -0 "$pid" >/dev/null 2>&1; then
            rm -f "$pidfile"
        fi
    done
}
