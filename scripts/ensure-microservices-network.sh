#!/usr/bin/env bash
# Create the compose shared network if missing (required when microservices-network is external: true).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=/dev/null
[[ -f "$ROOT/.env" ]] && set -a && source "$ROOT/.env" && set +a || true
NET="${COMPOSE_PROJECT_NAME:-ai4i-orchestrate}_microservices-network"
if docker network inspect "$NET" >/dev/null 2>&1; then
  echo "Network $NET already exists."
  exit 0
fi
docker network create --driver bridge "$NET"
echo "Created network $NET"
