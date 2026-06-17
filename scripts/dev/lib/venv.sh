#!/usr/bin/env bash

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

PYTHON_BIN="${PYTHON_BIN:-python3.11}"

# ONE shared virtualenv at the repo root, populated by a SINGLE pip install
# across every backend's requirements.txt (plan § 6 step 6 / § 8). pip's
# resolver picks one version set that satisfies all of them, and the ~60 shared
# packages (fastapi, uvicorn, sqlalchemy, …) download exactly once. The
# database/migration requirements are included so migrations run under the same
# venv (plan § 6 step 7).
VENV_DIR="$ROOT_DIR/.venv"

REQUIREMENTS=(
    "$ROOT_DIR/services/auth-service/requirements.txt"
    "$ROOT_DIR/services/platform-core-service/requirements.txt"
    "$ROOT_DIR/services/inference-service/requirements.txt"
    "$ROOT_DIR/infrastructure/databases/requirements.txt"
)

setup_venv() {

    if [[ -n "${AI4I_SKIP_VENV:-}" ]]; then
        warn "AI4I_SKIP_VENV set — skipping shared venv create + pip install"
        return 0
    fi

    if [[ ! -d "$VENV_DIR" ]]; then
        log "Creating shared virtualenv at $VENV_DIR"
        "$PYTHON_BIN" -m venv "$VENV_DIR"
    else
        ok "Shared virtualenv already exists"
    fi

    "$VENV_DIR/bin/pip" install --upgrade pip

    local pip_args=()
    local req
    for req in "${REQUIREMENTS[@]}"; do
        if [[ -f "$req" ]]; then
            pip_args+=(-r "$req")
        else
            warn "requirements file missing: $req"
        fi
    done

    log "Installing all backend requirements into the shared venv (single resolve)..."
    # If two services pin incompatible versions of the same lib, pip fails here
    # loudly — that's a real bug to fix in requirements.txt, not paper over.
    "$VENV_DIR/bin/pip" install "${pip_args[@]}"

    ok "Shared virtualenv ready"
}
