#!/usr/bin/env bash

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

# Run migrations under the shared root venv (plan § 6 step 7). The existing
# scripts/migrate.sh honours PYTHON_BIN, so we point it at the shared venv's
# interpreter rather than maintaining a separate migration venv.
run_migrations() {

    log "Running database migrations..."

    local venv="$ROOT_DIR/.venv"

    [[ -d "$venv" ]] \
        || die "Shared venv missing at $venv — run setup_venv first"

    export PYTHON_BIN="$venv/bin/python"

    # Only apply committed migrations — never autogenerate. Bringing up the stack
    # must not create new `*_auto_<timestamp>.py` revision files; that's a
    # deliberate `migrate.sh ... revision` step a dev runs when they change models.
    # migrate.sh defaults to apply-only, so no flag is needed here.
    (
        cd "$ROOT_DIR"
        ./scripts/migrate.sh all upgrade
    )

    ok "Database migrations complete"
}
