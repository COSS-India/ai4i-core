#!/usr/bin/env bash

set -euo pipefail

source "$(dirname "$0")/lib/common.sh"

check_python() {

    command -v python3.11 >/dev/null 2>&1 \
        || die "python3.11 not installed"

    ok "Python 3.11 found"
}

check_git() {

    command -v git >/dev/null 2>&1 \
        || die "git not installed"

    ok "Git found"
}

check_docker() {

    command -v docker >/dev/null 2>&1 \
        || die "docker not installed"

    docker info >/dev/null 2>&1 \
        || die "docker daemon not running"

    ok "Docker running"
}

check_compose() {

    docker compose version >/dev/null 2>&1 \
        || die "docker compose not available"

    ok "Docker Compose found"
}

check_node() {

    command -v node >/dev/null 2>&1 \
        || die "node not installed"

    command -v npm >/dev/null 2>&1 \
        || die "npm not installed"

    ok "Node + npm found"
}

run_prereq_checks() {

    log "Checking prerequisites..."

    check_python
    check_git
    check_docker
    check_compose
    check_node

    ok "All prerequisites satisfied"
}