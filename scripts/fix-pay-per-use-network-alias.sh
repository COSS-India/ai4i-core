#!/usr/bin/env bash
# Ensure Docker DNS name `pay-per-use-service` resolves (compose alias).
# Run if APISIX/nginx used pay-per-use-service:8006 and you see 503s, or `Aliases` is null on inspect.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=/dev/null
if [[ -f "$ROOT/.env" ]]; then set -a && source "$ROOT/.env" && set +a; fi
PROJECT="${COMPOSE_PROJECT_NAME:-ai4i-orchestrate}"
NET="${PROJECT}_microservices-network"
CTR="ai4v-pay-per-use-service"

docker network disconnect "$NET" "$CTR" 2>/dev/null || true
docker network connect --alias pay-per-use-service "$NET" "$CTR"
echo "Connected $CTR to $NET with alias pay-per-use-service"
