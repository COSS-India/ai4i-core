#!/usr/bin/env bash
# Run the database CLI inside the Docker network so POSTGRES_HOST=postgres resolves.
# Usage: ./scripts/run-migration-cli.sh [command] [args...]
# Valid commands: migrate, migrate:all, rollback, migrate:status, migrate:fresh, make:migration
# Example: ./scripts/run-migration-cli.sh migrate:status
# Example: ./scripts/run-migration-cli.sh migrate:all

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

docker compose -f docker-compose-local.yml run --rm migration-runner python infrastructure/databases/cli.py "$@"
