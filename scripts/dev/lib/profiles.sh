#!/usr/bin/env bash

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

# Translate a profile name into the knobs the rest of the tooling reads.
# Every profile builds on `core` (postgres + redis + the three native backend
# services); the named docker-compose profiles only ADD services on top.
#
# Sets these globals:
#   COMPOSE_PROFILE_ARGS  array of "--profile X" passed to docker compose
#   START_FRONTEND        "true"/"false" — start simple-ui natively
#   ENABLE_KAFKA          "true"/"false" — flip KAFKA_ENABLED in inference .env
#   WAIT_KAFKA            "true"/"false"
#   WAIT_OPENSEARCH       "true"/"false"
resolve_profile() {

    local profile="$1"

    COMPOSE_PROFILE_ARGS=()
    START_FRONTEND="false"
    ENABLE_KAFKA="false"
    WAIT_KAFKA="false"
    WAIT_OPENSEARCH="false"

    case "$profile" in

        core)
            ;;

        frontend)
            # simple-ui runs natively (npm run dev); no compose services to add.
            START_FRONTEND="true"
            ;;

        observability)
            COMPOSE_PROFILE_ARGS=(--profile observability)
            ;;

        logging)
            COMPOSE_PROFILE_ARGS=(--profile logging)
            ENABLE_KAFKA="true"
            WAIT_KAFKA="true"
            WAIT_OPENSEARCH="true"
            ;;

        all)
            COMPOSE_PROFILE_ARGS=(--profile observability --profile logging)
            START_FRONTEND="true"
            ENABLE_KAFKA="true"
            WAIT_KAFKA="true"
            WAIT_OPENSEARCH="true"
            ;;

        *)
            die "Unsupported profile: '$profile' (use: core | frontend | observability | logging | all)"
            ;;
    esac
}

# Every docker-compose profile we know about — used by `down` to stop
# whatever might be running regardless of which profile started it.
ALL_COMPOSE_PROFILE_ARGS=(--profile observability --profile logging)
