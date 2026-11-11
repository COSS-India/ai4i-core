#!/usr/bin/env bash
# Run the database CLI against host-reachable Postgres (Compose maps :5432).
# Prefer: ./scripts/migrate.sh …
#
# Usage: ./scripts/run-migration-cli.sh [command] [args...]
# Valid commands: migrate, migrate:all, rollback, migrate:status, migrate:fresh, make:migration
# Example: ./scripts/run-migration-cli.sh migrate:status
# Example: ./scripts/run-migration-cli.sh migrate:all

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

# Local Compose no longer ships a migration-runner container; run on the host
# with POSTGRES_HOST=localhost (see docker-compose/SETUP-GUIDE.md).
exec python infrastructure/databases/cli.py "$@"
