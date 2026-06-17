#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

RUN_DIR="$ROOT_DIR/.run"
# AI4I_LOGS_DIR lets the user redirect backgrounded logs (see plan § 10).
LOG_DIR="${AI4I_LOGS_DIR:-$ROOT_DIR/logs}"

mkdir -p "$RUN_DIR"
mkdir -p "$LOG_DIR"

log() {
    echo "[INFO] $*"
}

warn() {
    echo "[WARN] $*" >&2
}

error() {
    echo "[ERROR] $*" >&2
}

die() {
    error "$*"
    exit 1
}

ok() {
    echo "[OK] $*"
}

require_file() {
    local file="$1"

    [[ -f "$file" ]] || die "Missing file: $file"
}

require_dir() {
    local dir="$1"

    [[ -d "$dir" ]] || die "Missing directory: $dir"
}

is_wsl() {
    grep -qi microsoft /proc/version 2>/dev/null
}

# Services started during the current `up` run. The orchestrator's failure
# trap reads this to tear down only what it launched, leaving docker alone.
# Guarded so re-sourcing common.sh doesn't clobber an in-progress list.
if [[ -z "${STARTED_SERVICES_INIT:-}" ]]; then
    STARTED_SERVICES=()
    STARTED_SERVICES_INIT=1
fi

track_started() {
    STARTED_SERVICES+=("$1")
}

wait_for_port() {

    local host="$1"
    local port="$2"
    local timeout="${3:-120}"

    local start
    start=$(date +%s)

    while true; do

        if nc -z "$host" "$port" >/dev/null 2>&1; then
            return 0
        fi

        if (( $(date +%s) - start > timeout )); then
            return 1
        fi

        sleep 2
    done
}

wait_for_http() {

    local url="$1"
    local timeout="${2:-120}"

    local start
    start=$(date +%s)

    while true; do

        if curl -fsS "$url" >/dev/null 2>&1; then
            return 0
        fi

        if (( $(date +%s) - start > timeout )); then
            return 1
        fi

        sleep 2
    done
}
