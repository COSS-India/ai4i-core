#!/usr/bin/env bash

set -euo pipefail

source "$(dirname "$0")/lib/common.sh"
source "$(dirname "$0")/lib/pids.sh"

start_auth_service() {

    log "Starting auth-service..."

    (
        cd "$ROOT_DIR/services/auth-service"

        source .venv/bin/activate

        uvicorn \
            app.main:app \
            --host 0.0.0.0 \
            --port 8081
    ) > "$LOG_DIR/auth-service.log" 2>&1 &

    local pid=$!

    save_pid auth-service "$pid"

    ok "auth-service started (PID=$pid)"
}

start_platform_service() {

    log "Starting platform-core-service..."

    (
        cd "$ROOT_DIR/services/platform-core-service"

        source .venv/bin/activate

        uvicorn \
            app.main:app \
            --host 0.0.0.0 \
            --port 8095
    ) > "$LOG_DIR/platform-core-service.log" 2>&1 &

    local pid=$!

    save_pid platform-core-service "$pid"

    ok "platform-core-service started (PID=$pid)"
}

start_inference_service() {

    log "Starting inference-service..."

    (
        cd "$ROOT_DIR/services/inference-service"

        source .venv/bin/activate

        uvicorn \
            main:app \
            --host 0.0.0.0 \
            --port 8090
    ) > "$LOG_DIR/inference-service.log" 2>&1 &

    local pid=$!

    save_pid inference-service "$pid"

    ok "inference-service started (PID=$pid)"
}

stop_auth_service() {

    kill_service auth-service
}

stop_platform_service() {

    kill_service platform-core-service
}

stop_inference_service() {

    kill_service inference-service
}

start_all_services() {

    start_auth_service

    sleep 5

    start_platform_service

    sleep 5

    start_inference_service

    ok "All backend services started"
}

stop_all_services() {

    stop_auth_service

    stop_platform_service

    stop_inference_service

    ok "All backend services stopped"
}