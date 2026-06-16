#!/usr/bin/env bash

set -euo pipefail

source "$(dirname "$0")/lib/common.sh"

wait_for_postgres() {

    log "Waiting for postgres..."

    wait_for_port localhost 5432 180 \
        || die "Postgres failed to become healthy"

    ok "Postgres healthy"
}

wait_for_redis() {

    log "Waiting for redis..."

    wait_for_port localhost 6379 180 \
        || die "Redis failed to become healthy"

    ok "Redis healthy"
}

wait_for_nginx() {

    log "Waiting for nginx gateway..."

    wait_for_port localhost 8080 180 \
        || die "Nginx failed to become healthy"

    ok "Nginx healthy"
}

wait_for_core_infra() {

    wait_for_postgres
    wait_for_redis
    wait_for_nginx
}

wait_for_auth_service() {

    log "Waiting for auth-service..."

    wait_for_http \
        "http://localhost:8081/docs" \
        180 \
        || die "auth-service failed health check"

    ok "auth-service healthy"
}

wait_for_platform_service() {

    log "Waiting for platform-core-service..."

    wait_for_http \
        "http://localhost:8095/docs" \
        180 \
        || die "platform-core-service failed health check"

    ok "platform-core-service healthy"
}

wait_for_inference_service() {

    log "Waiting for inference-service..."

    wait_for_http \
        "http://localhost:8090/docs" \
        180 \
        || die "inference-service failed health check"

    ok "inference-service healthy"
}

wait_for_all_services() {

    wait_for_auth_service

    wait_for_platform_service

    wait_for_inference_service
}

