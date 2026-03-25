#!/usr/bin/env bash
#
# setup-env.sh — Generate .env files from env.template files.
#
# Reads Postgres credentials, DB names, and other shared values from the root
# .env and substitutes <PLACEHOLDER> tokens in every env.template found under
# the project tree.
#
# Usage:
#   ./scripts/setup-env.sh   # (Re)generate all .env files from templates
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── 1. Ensure root .env exists ──────────────────────────────────────────────
ROOT_ENV="$ROOT_DIR/.env"
if [ ! -f "$ROOT_ENV" ]; then
    echo "Root .env not found — copying from env.template ..."
    cp "$ROOT_DIR/env.template" "$ROOT_ENV"
    echo "  Created $ROOT_ENV (edit it to set your values, then re-run this script)"
fi

# ── 2. Read specific variables from root .env ────────────────────────────────
# We parse the file manually rather than sourcing it, because values like
# <YOUR_REDIS_PASSWORD> would break bash's source command.
read_env_var() {
    local var_name="$1"
    local default="$2"
    local value
    value=$(grep -m1 "^${var_name}=" "$ROOT_ENV" 2>/dev/null | cut -d'=' -f2- || true)
    echo "${value:-$default}"
}

POSTGRES_USER="$(read_env_var POSTGRES_USER postgres)"
POSTGRES_PASSWORD="$(read_env_var POSTGRES_PASSWORD postgres)"
POSTGRES_HOST="$(read_env_var POSTGRES_HOST postgres)"
POSTGRES_PORT="$(read_env_var POSTGRES_PORT 5432)"
POSTGRES_DB="$(read_env_var POSTGRES_DB ai4i_platform)"

AUTH_DB_NAME="$(read_env_var AUTH_DB_NAME auth_db)"
MULTI_TENANT_DB_NAME="$(read_env_var MULTI_TENANT_DB_NAME multi_tenant_db)"
CONFIG_DB_NAME="$(read_env_var CONFIG_DB_NAME config_db)"
MODEL_MANAGEMENT_DB_NAME="$(read_env_var MODEL_MANAGEMENT_DB_NAME model_management_db)"
DASHBOARD_DB_NAME="$(read_env_var DASHBOARD_DB_NAME dashboard_db)"
TELEMETRY_DB_NAME="$(read_env_var TELEMETRY_DB_NAME telemetry_db)"
METRICS_DB_NAME="$(read_env_var METRICS_DB_NAME metrics_db)"
ALERTING_DB_NAME="$(read_env_var ALERTING_DB_NAME alerting_db)"

ALEMBIC_DB_HOST="$(read_env_var ALEMBIC_DB_HOST localhost)"
ALEMBIC_DB_PORT="$(read_env_var ALEMBIC_DB_PORT 5434)"

# ── 3. Build sed replacement expressions ─────────────────────────────────────
SED_ARGS=(
    -e "s|<POSTGRES_USER>|${POSTGRES_USER}|g"
    -e "s|<POSTGRES_PASSWORD>|${POSTGRES_PASSWORD}|g"
    -e "s|<POSTGRES_HOST>|${POSTGRES_HOST}|g"
    -e "s|<POSTGRES_PORT>|${POSTGRES_PORT}|g"
    -e "s|<POSTGRES_DB>|${POSTGRES_DB}|g"
    -e "s|<AUTH_DB_NAME>|${AUTH_DB_NAME}|g"
    -e "s|<MULTI_TENANT_DB_NAME>|${MULTI_TENANT_DB_NAME}|g"
    -e "s|<CONFIG_DB_NAME>|${CONFIG_DB_NAME}|g"
    -e "s|<MODEL_MANAGEMENT_DB_NAME>|${MODEL_MANAGEMENT_DB_NAME}|g"
    -e "s|<DASHBOARD_DB_NAME>|${DASHBOARD_DB_NAME}|g"
    -e "s|<TELEMETRY_DB_NAME>|${TELEMETRY_DB_NAME}|g"
    -e "s|<METRICS_DB_NAME>|${METRICS_DB_NAME}|g"
    -e "s|<ALERTING_DB_NAME>|${ALERTING_DB_NAME}|g"
    -e "s|<ALEMBIC_DB_HOST>|${ALEMBIC_DB_HOST}|g"
    -e "s|<ALEMBIC_DB_PORT>|${ALEMBIC_DB_PORT}|g"
)

# ── 4. Process every env.template ────────────────────────────────────────────
generated=0

while IFS= read -r -d '' template; do
    dir="$(dirname "$template")"
    target="$dir/.env"

    # The root env.template is the source of truth — skip it.
    if [ "$template" = "$ROOT_DIR/env.template" ]; then
        continue
    fi

    sed "${SED_ARGS[@]}" "$template" > "$target"
    echo "  GEN   $target"
    generated=$((generated + 1))

done < <(find "$ROOT_DIR" -name "env.template" -not -path "*/node_modules/*" -print0 | sort -z)

echo ""
echo "Done — $generated .env file(s) generated."
