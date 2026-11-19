#!/usr/bin/env bash

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

PYTHON_BIN="${PYTHON_BIN:-python3.11}"

# One virtualenv per backend, each installed from that backend's own pinned
# requirements.txt — the same file its Docker image installs, so local runs the
# same library versions as the deployed image. Services pin different versions
# of some shared packages (e.g. inference holds cryptography and numpy lower),
# so they cannot share one environment.
#
# The repo-root .venv holds the migration requirements only (used by
# migrate.sh).
MIGRATION_VENV_DIR="$ROOT_DIR/.venv"

SERVICE_DIRS=(
    "services/auth-service"
    "services/platform-core-service"
    "services/inference-service"
)

# Path of the virtualenv for a service directory (relative to the repo root).
service_venv() {
    echo "$ROOT_DIR/$1/.venv"
}

_setup_one_venv() {

    local venv="$1"
    local req="$2"

    [[ -f "$req" ]] || die "requirements file missing: $req"

    if [[ ! -d "$venv" ]]; then
        log "Creating virtualenv at $venv"
        "$PYTHON_BIN" -m venv "$venv"
    else
        ok "Virtualenv already exists: $venv"
    fi

    "$venv/bin/pip" install --upgrade pip
    log "Installing $req..."
    "$venv/bin/pip" install -r "$req"
}

setup_venv() {

    if [[ -n "${AI4I_SKIP_VENV:-}" ]]; then
        warn "AI4I_SKIP_VENV set — skipping virtualenv create + pip install"
        return 0
    fi

    local dir
    for dir in "${SERVICE_DIRS[@]}"; do
        _setup_one_venv "$(service_venv "$dir")" "$ROOT_DIR/$dir/requirements.txt"
    done

    _setup_one_venv "$MIGRATION_VENV_DIR" "$ROOT_DIR/infrastructure/databases/requirements.txt"

    ok "Virtualenvs ready"
}
