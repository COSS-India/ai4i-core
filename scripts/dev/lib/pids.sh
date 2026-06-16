#!/usr/bin/env bash

set -euo pipefail

source "$(dirname "$0")/lib/common.sh"

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

kill_service() {

    local service="$1"

    if is_running "$service"; then

        local pid

        pid=$(read_pid "$service")

        kill "$pid"

        rm -f "$(pid_file "$service")"

        ok "Stopped $service"
    fi
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