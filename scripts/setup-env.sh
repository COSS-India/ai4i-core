#!/usr/bin/env bash
#
# setup-env.sh — thin wrapper around the Docker Compose pack generator.
#
# Canonical script: docker-compose/scripts/setup-env.sh
# Prefer running from the compose directory:
#   cd docker-compose && ./scripts/setup-env.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_SETUP="${ROOT_DIR}/docker-compose/scripts/setup-env.sh"

if [ ! -f "$COMPOSE_SETUP" ]; then
  echo "ERROR: missing $COMPOSE_SETUP" >&2
  exit 1
fi

exec bash "$COMPOSE_SETUP" "$@"
