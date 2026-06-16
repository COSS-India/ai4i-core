#!/usr/bin/env bash

set -euo pipefail

source "$(dirname "$0")/lib/common.sh"

PYTHON_BIN="python3.11"

create_venv() {

    local dir="$1"

    if [[ ! -d "$dir/.venv" ]]; then

        log "Creating venv: $dir"

        "$PYTHON_BIN" -m venv "$dir/.venv"
    fi

    ok "Venv ready: $dir"
}

install_requirements() {

    local dir="$1"

    local req="$dir/requirements.txt"

    if [[ ! -f "$req" ]]; then
        warn "requirements.txt missing in $dir"
        return
    fi

    log "Installing dependencies for $dir"

    "$dir/.venv/bin/pip" install --upgrade pip

    "$dir/.venv/bin/pip" install -r "$req"

    ok "Dependencies installed: $dir"
}

setup_database_venv() {

    local dir="$ROOT_DIR/infrastructure/databases"

    create_venv "$dir"

    install_requirements "$dir"
}

setup_auth_venv() {

    local dir="$ROOT_DIR/services/auth-service"

    create_venv "$dir"

    install_requirements "$dir"
}

setup_platform_venv() {

    local dir="$ROOT_DIR/services/platform-core-service"

    create_venv "$dir"

    install_requirements "$dir"
}

setup_inference_venv() {

    local dir="$ROOT_DIR/services/inference-service"

    create_venv "$dir"

    install_requirements "$dir"
}

setup_all_venvs() {

    setup_database_venv

    setup_auth_venv

    setup_platform_venv

    setup_inference_venv

    ok "All virtual environments ready"
}