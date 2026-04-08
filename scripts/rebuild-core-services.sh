#!/usr/bin/env bash
# Rebuild and start core stack services (run from repo root).
# Usage: ./scripts/rebuild-core-services.sh
# If you see "permission denied" on the Docker socket, use either:
#   sudo ./scripts/rebuild-core-services.sh
#   or: sudo usermod -aG docker "$USER" && newgrp docker   # then run without sudo

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SERVICES=(
  model-management-service
  auth-service
  apisix
  multi-tenant-service
  policy-engine
  simple-ui-frontend
  nmt-service
  pay-per-use-service
)

echo "Building: ${SERVICES[*]}"
docker compose build "${SERVICES[@]}"

echo "Starting: ${SERVICES[*]}"
docker compose up -d "${SERVICES[@]}"

echo "Done. Status:"
docker compose ps "${SERVICES[@]}"
