#!/usr/bin/env bash

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

COMPOSE_FILE="$ROOT_DIR/docker-compose-local.yml"

# Wrapper around `docker compose` that pins the project directory and env file to
# the repo root. Without --env-file, compose resolves ${POSTGRES_PASSWORD} etc.
# from the .env in the *current* directory — so running `up` from anywhere but
# the repo root would start postgres/redis with the wrong (or empty) passwords.
_compose() {

    local env_args=()
    [[ -f "$ROOT_DIR/.env" ]] && env_args=(--env-file "$ROOT_DIR/.env")

    docker compose \
        --project-directory "$ROOT_DIR" \
        ${env_args[@]+"${env_args[@]}"} \
        -f "$COMPOSE_FILE" \
        "$@"
}

# Bring up infra for the resolved profile. postgres + redis carry no compose
# `profiles:` key, so they always start; the COMPOSE_PROFILE_ARGS add the
# profile-specific services (nginx-gateway, prometheus stack, opensearch …).
#
# Pull policy: we rely on docker compose's default ("missing") — cached images
# are NEVER re-pulled, only absent ones are fetched. `up --pull` (PULL_IMAGES)
# forces a refresh with "--pull always".
start_infra() {

    require_file "$COMPOSE_FILE"

    local pull_args=()
    if [[ "${PULL_IMAGES:-false}" == "true" ]]; then
        pull_args=(--pull always)
        log "Refreshing docker images (--pull always)"
    fi

    log "Starting infrastructure..."

    _compose \
        ${COMPOSE_PROFILE_ARGS[@]+"${COMPOSE_PROFILE_ARGS[@]}"} \
        up -d \
        ${pull_args[@]+"${pull_args[@]}"}

    ok "Infrastructure started"
}

# Stop every profile's containers (keep volumes). Used by `down` so it tears
# down whatever is running regardless of the profile that started it.
stop_infra() {

    require_file "$COMPOSE_FILE"

    log "Stopping infrastructure (volumes preserved)..."

    _compose "${ALL_COMPOSE_PROFILE_ARGS[@]}" stop

    ok "Infrastructure stopped"
}

# Destructive: remove containers AND volumes (used by `down --prune` / `reset`).
remove_infra() {

    require_file "$COMPOSE_FILE"

    log "Removing infrastructure containers and volumes..."

    _compose "${ALL_COMPOSE_PROFILE_ARGS[@]}" down -v

    ok "Infrastructure removed"
}
