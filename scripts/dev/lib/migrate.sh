#!/usr/bin/env bash

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

# Run migrations under the repo-root venv, which holds
# infrastructure/databases/requirements.txt (the same file the deployed
# migration job installs). scripts/migrate.sh honours PYTHON_BIN.
run_migrations() {

    log "Running database migrations..."

    local venv="$ROOT_DIR/.venv"

    [[ -d "$venv" ]] \
        || die "Migration venv missing at $venv — run setup_venv first"

    export PYTHON_BIN="$venv/bin/python"

    # Only apply committed migrations. `migrate.sh ... upgrade` never generates
    # revision files, so bringing up the stack cannot create `*_auto_<timestamp>.py`;
    # generating one is a deliberate `migrate.sh ... revision --autogenerate` step a
    # dev runs when they change models.
    (
        cd "$ROOT_DIR"
        ./scripts/migrate.sh all upgrade
    )

    ok "Database migrations complete"
}
