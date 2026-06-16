#!/usr/bin/env bash

set -euo pipefail

source "$(dirname "$0")/lib/common.sh"

COMPOSE_FILE="$ROOT_DIR/docker-compose-local.yml"

start_core_infra() {

    require_file "$COMPOSE_FILE"

    log "Starting infrastructure..."

    docker compose \
        -f "$COMPOSE_FILE" \
        up -d \
        postgres \
        redis \
        nginx-gateway

    ok "Infrastructure started"
}

stop_core_infra() {

    require_file "$COMPOSE_FILE"

    log "Stopping infrastructure..."

    docker compose \
        -f "$COMPOSE_FILE" \
        stop \
        postgres \
        redis \
        nginx-gateway

    ok "Infrastructure stopped"
}

remove_core_infra() {

    require_file "$COMPOSE_FILE"

    log "Removing infrastructure..."

    docker compose \
        -f "$COMPOSE_FILE" \
        down

    ok "Infrastructure removed"
}