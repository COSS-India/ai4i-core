#!/usr/bin/env bash

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

# Refuse to run in a native Windows shell (git-bash / MSYS / Cygwin). Windows
# contributors go through WSL2 — see SETUP_GUIDE.md § Windows (WSL).
check_os() {

    case "$(uname -s 2>/dev/null)" in
        MINGW*|MSYS*|CYGWIN*)
            die "Native Windows shell detected. Open a WSL2 terminal and re-run (see SETUP_GUIDE.md § Windows)."
            ;;
    esac

    ok "OS supported"
}

check_python() {

    command -v python3.11 >/dev/null 2>&1 \
        || die "python3.11 not installed (try scripts/dev/install-prereqs.sh)"

    ok "Python 3.11 found"
}

check_git() {

    command -v git >/dev/null 2>&1 \
        || die "git not installed"

    ok "Git found"
}

check_docker() {

    command -v docker >/dev/null 2>&1 \
        || die "docker not installed (try scripts/dev/install-prereqs.sh)"

    docker info >/dev/null 2>&1 \
        || die "docker daemon not running"

    ok "Docker running"
}

check_compose() {

    docker compose version >/dev/null 2>&1 \
        || die "docker compose v2 not available"

    ok "Docker Compose found"
}

check_node() {

    command -v node >/dev/null 2>&1 \
        || die "node not installed (needed for the frontend profile)"

    command -v npm >/dev/null 2>&1 \
        || die "npm not installed"

    local major
    major="$(node -v | sed 's/^v//' | cut -d. -f1)"

    if [[ "$major" -lt 18 ]]; then
        die "node >= 18 required (found $(node -v))"
    fi

    ok "Node $(node -v) + npm found"
}

# Node is only required when the frontend will actually be started, so a
# backend-only `core` run doesn't force a node install.
run_prereq_checks() {

    local needs_node="${1:-false}"

    log "Checking prerequisites..."

    check_os
    check_python
    check_git
    check_docker
    check_compose

    if [[ "$needs_node" == "true" ]]; then
        check_node
    fi

    ok "All prerequisites satisfied"
}
