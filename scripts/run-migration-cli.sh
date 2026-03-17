#!/usr/bin/env bash
# Run the database CLI inside the Docker network so POSTGRES_HOST=postgres resolves.
# Usage: ./scripts/run-migration-cli.sh [command] [args...]
# Example: ./scripts/run-migration-cli.sh init:external
# Example: ./scripts/run-migration-cli.sh seed:all

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

docker compose -f docker-compose-local.yml run --rm migration-runner python infrastructure/databases/cli.py "$@"
