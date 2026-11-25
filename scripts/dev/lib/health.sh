#!/usr/bin/env bash

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

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

wait_for_kafka() {

    log "Waiting for kafka..."

    # Host publish port from docker-compose/.env (default 9092). 9093 is the
    # in-container KRaft controller listener and is not published.
    local kafka_port="${KAFKA_EXTERNAL_PORT:-9092}"
    local compose_env="${COMPOSE_DIR:-${ROOT_DIR}/docker-compose}/.env"
    if [[ -f "${compose_env}" ]]; then
        local from_env
        from_env="$(grep -m1 '^KAFKA_EXTERNAL_PORT=' "${compose_env}" 2>/dev/null | cut -d= -f2- || true)"
        [[ -n "${from_env}" ]] && kafka_port="${from_env}"
    fi

    wait_for_port localhost "${kafka_port}" 180 \
        || die "Kafka failed to become healthy (localhost:${kafka_port})"

    ok "Kafka healthy"
}

wait_for_opensearch() {

    log "Waiting for opensearch..."

    wait_for_port localhost 9200 180 \
        || die "OpenSearch failed to become healthy"

    ok "OpenSearch healthy"
}

# Always wait on postgres + redis; the rest depend on the resolved profile.
wait_for_infra() {

    wait_for_postgres
    wait_for_redis

    [[ "${WAIT_KAFKA:-false}" == "true" ]]      && wait_for_kafka
    [[ "${WAIT_OPENSEARCH:-false}" == "true" ]] && wait_for_opensearch

    return 0
}

wait_for_auth_service() {

    log "Waiting for auth-service..."

    wait_for_http "http://localhost:8081/docs" 180 \
        || die "auth-service failed health check"

    ok "auth-service healthy"
}

wait_for_platform_service() {

    log "Waiting for platform-core-service..."

    wait_for_http "http://localhost:8095/docs" 180 \
        || die "platform-core-service failed health check"

    ok "platform-core-service healthy"
}

wait_for_inference_service() {

    log "Waiting for inference-service..."

    wait_for_http "http://localhost:8090/docs" 180 \
        || die "inference-service failed health check"

    ok "inference-service healthy"
}

wait_for_frontend() {

    log "Waiting for simple-ui..."

    wait_for_http "http://localhost:3000" 180 \
        || die "simple-ui failed health check"

    ok "simple-ui healthy"
}

wait_for_all_services() {

    wait_for_auth_service
    wait_for_platform_service
    wait_for_inference_service
}
