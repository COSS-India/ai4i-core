#!/usr/bin/env bash

set -euo pipefail

source "$(dirname "$0")/lib/common.sh"

ROOT_ENV="$ROOT_DIR/.env"
ROOT_TEMPLATE="$ROOT_DIR/env.template"

create_root_env() {

    if [[ -f "$ROOT_ENV" ]]; then
        ok "Root .env already exists"
        return
    fi

    require_file "$ROOT_TEMPLATE"

    cp "$ROOT_TEMPLATE" "$ROOT_ENV"

    ok "Created root .env"
}

generate_service_envs() {

    require_file "$ROOT_DIR/scripts/setup-env.sh"

    chmod +x "$ROOT_DIR/scripts/setup-env.sh"

    (
        cd "$ROOT_DIR"
        ./scripts/setup-env.sh
    )

    ok "Generated service .env files"
}

bootstrap_env() {

    log "Bootstrapping environment..."

    create_root_env

    generate_service_envs
}