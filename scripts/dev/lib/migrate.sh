#!/usr/bin/env bash

set -euo pipefail

source "$(dirname "$0")/lib/common.sh"

run_migrations() {

    log "Running database migrations..."

    local db_venv

    db_venv="$ROOT_DIR/infrastructure/databases/.venv"

    [[ -d "$db_venv" ]] \
        || die "Database venv missing"

    export PYTHON_BIN="$db_venv/bin/python"

    (
        cd "$ROOT_DIR"

        ./scripts/migrate.sh all upgrade
    )

    ok "Database migrations complete"
}