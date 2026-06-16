#!/usr/bin/env bash

set -euo pipefail

source "$(dirname "$0")/lib/common.sh"

ROOT_ENV="$ROOT_DIR/.env"
ROOT_TEMPLATE="$ROOT_DIR/env.template"

create_root_env() {

    require_file "$ROOT_TEMPLATE"

    if [[ ! -f "$ROOT_ENV" ]]; then
        cp "$ROOT_TEMPLATE" "$ROOT_ENV"
        ok "Created root .env"
    else
        ok "Root .env already exists"
    fi

    set_default "POSTGRES_USER" "postgres"
    set_default "POSTGRES_PASSWORD" "postgres"
    set_default "REDIS_PASSWORD" "changeme"

    warn_if_missing_llm
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

set_default() {

    local key="$1"
    local value="$2"

    if grep -q "^${key}=" "$ROOT_ENV"; then

        local current
        current=$(grep "^${key}=" "$ROOT_ENV" | cut -d= -f2-)

        if [[ -z "$current" ]] || [[ "$current" =~ ^\<.*\>$ ]]; then
            sed -i "s|^${key}=.*|${key}=${value}|" "$ROOT_ENV"
            ok "Set default for ${key}"
        fi

    else
        echo "${key}=${value}" >> "$ROOT_ENV"
        ok "Added ${key}"
    fi
}

warn_if_missing_llm() {

    if grep -q "^LLM_UPSTREAM_BASE_URL=" "$ROOT_ENV"; then

        local value
        value=$(grep "^LLM_UPSTREAM_BASE_URL=" "$ROOT_ENV" | cut -d= -f2-)

        if [[ -z "$value" ]] || [[ "$value" =~ ^\<.*\>$ ]]; then
            warn "LLM_UPSTREAM_BASE_URL is not configured."
            warn "LLM-based inference will not work until configured."
        fi
    fi
}