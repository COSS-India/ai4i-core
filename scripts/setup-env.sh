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
# Optional 2nd arg: fallback file (e.g. env.template) when root .env value is blank.
read_env_var() {
    local var_name="$1"
    local fallback_file="${2:-}"
    local value
    value=$(grep -m1 "^${var_name}=" "$ROOT_ENV" 2>/dev/null | cut -d'=' -f2- || true)
    if [ -z "${value}" ] && [ -n "${fallback_file}" ]; then
        value=$(grep -m1 "^${var_name}=" "$fallback_file" 2>/dev/null | cut -d'=' -f2- || true)
    fi
    echo "${value:-}"
}

# Generate <bytes> random bytes, base64-encoded.
gen_base64_key() {
    local bytes="$1"
    if command -v python3.11 >/dev/null 2>&1; then
        python3.11 -c "import base64, os; print(base64.b64encode(os.urandom(${bytes})).decode())"
    elif command -v python3 >/dev/null 2>&1; then
        python3 -c "import base64, os; print(base64.b64encode(os.urandom(${bytes})).decode())"
    elif command -v openssl >/dev/null 2>&1; then
        openssl rand -base64 "${bytes}" | tr -d '\n'
    else
        echo "ERROR: need python3 or openssl to generate secrets" >&2
        exit 1
    fi
}

# Resolve a secret that must survive re-runs into the variable <name>, in order:
#   root .env override → value already in an existing service .env → generate.
# Usage: resolve_persistent_secret <name> <bytes> [<service .env> <key>]...
# Blank values and unfilled <PLACEHOLDER> tokens count as unset.
resolve_persistent_secret() {
    local name="$1"
    local bytes="$2"
    shift 2
    local value
    value="$(read_env_var "$name")"
    while [ "$#" -ge 2 ]; do
        case "${value}" in
            "" | "<"*">") ;;
            *) break ;;
        esac
        if [ -f "$1" ]; then
            value="$(grep -m1 "^$2=" "$1" 2>/dev/null | cut -d'=' -f2- || true)"
        fi
        shift 2
    done
    case "${value}" in
        "" | "<"*">")
            value="$(gen_base64_key "${bytes}")"
            echo "  GEN   ${name} (new random value)"
            ;;
    esac
    printf -v "${name}" '%s' "${value}"
}

POSTGRES_USER="$(read_env_var POSTGRES_USER)"
POSTGRES_PASSWORD="$(read_env_var POSTGRES_PASSWORD)"
POSTGRES_HOST="$(read_env_var POSTGRES_HOST)"
POSTGRES_PORT="$(read_env_var POSTGRES_PORT)"
POSTGRES_DB="$(read_env_var POSTGRES_DB)"

AUTH_DB_NAME="$(read_env_var AUTH_DB_NAME)"
MODEL_MANAGEMENT_DB_NAME="$(read_env_var MODEL_MANAGEMENT_DB_NAME)"

REDIS_PASSWORD="$(read_env_var REDIS_PASSWORD)"

ALEMBIC_DB_HOST="$(read_env_var ALEMBIC_DB_HOST)"
ALEMBIC_DB_PORT="$(read_env_var ALEMBIC_DB_PORT)"

LLM_UPSTREAM_BASE_URL="$(read_env_var LLM_UPSTREAM_BASE_URL)"

# Branding — root .env, else env.template; copied into simple-ui, auth-service,
# platform-core-service and kafka-consumers (notifications_consumer).
PLATFORM_NAME="$(read_env_var PLATFORM_NAME "$ROOT_DIR/env.template")"
ADOPTER_LOGO_URL="$(read_env_var ADOPTER_LOGO_URL "$ROOT_DIR/env.template")"

# ── 3. Build sed replacement expressions ─────────────────────────────────────
SED_ARGS=()

# Escape sed replacement metacharacters in a value (&, \, and | delimiter).
# Unescaped, & expands to the matched <PLACEHOLDER> and | aborts the script.
sed_escape() {
    printf '%s' "$1" | sed -e 's/[&\\|]/\\&/g'
}

add_sed_replacement() {
    local placeholder="$1"
    local value="$2"

    # If a value isn't set in root .env, keep the <PLACEHOLDER> token intact.
    if [ -z "${value}" ]; then
        return 0
    fi

    SED_ARGS+=(-e "s|<${placeholder}>|$(sed_escape "${value}")|g")
}

# Always substitute (empty is valid — e.g. unset logo falls back to the default SVG).
add_sed_replacement_allow_empty() {
    local placeholder="$1"
    local value="$2"
    SED_ARGS+=(-e "s|<${placeholder}>|$(sed_escape "${value}")|g")
}

add_sed_replacement "POSTGRES_USER" "${POSTGRES_USER}"
add_sed_replacement "POSTGRES_PASSWORD" "${POSTGRES_PASSWORD}"
add_sed_replacement "POSTGRES_HOST" "${POSTGRES_HOST}"
add_sed_replacement "POSTGRES_PORT" "${POSTGRES_PORT}"
add_sed_replacement "POSTGRES_DB" "${POSTGRES_DB}"
add_sed_replacement "AUTH_DB_NAME" "${AUTH_DB_NAME}"
add_sed_replacement "MODEL_MANAGEMENT_DB_NAME" "${MODEL_MANAGEMENT_DB_NAME}"
add_sed_replacement "YOUR_REDIS_PASSWORD" "${REDIS_PASSWORD}"
add_sed_replacement "ALEMBIC_DB_HOST" "${ALEMBIC_DB_HOST}"
add_sed_replacement "ALEMBIC_DB_PORT" "${ALEMBIC_DB_PORT}"
add_sed_replacement "YOUR_LLM_UPSTREAM_BASE_URL" "${LLM_UPSTREAM_BASE_URL}"
add_sed_replacement_allow_empty "PLATFORM_NAME" "${PLATFORM_NAME}"
add_sed_replacement_allow_empty "ADOPTER_LOGO_URL" "${ADOPTER_LOGO_URL}"

# ── 3b. Persistent secrets ───────────────────────────────────────────────────
# Re-running setup-env.sh must not rotate these: a new encryption key leaves
# already-encrypted rows unreadable, and a new shared secret must reach both
# services at once.
AUTH_ENV="$ROOT_DIR/services/auth-service/.env"
PLATFORM_CORE_ENV="$ROOT_DIR/services/platform-core-service/.env"
INFERENCE_ENV="$ROOT_DIR/services/inference-service/.env"

# AES-256-SIV key for PII (64 bytes), shared by auth-service and platform-core.
resolve_persistent_secret PII_ENCRYPTION_KEY 64 \
    "$AUTH_ENV" PII_ENCRYPTION_KEY \
    "$PLATFORM_CORE_ENV" PII_ENCRYPTION_KEY
# AES-256-GCM key for mm_services.llm_auth_token (32 bytes).
resolve_persistent_secret SERVICE_CREDENTIALS_ENCRYPTION_KEY 32 \
    "$PLATFORM_CORE_ENV" SERVICE_CREDENTIALS_ENCRYPTION_KEY
# Written to platform-core and inference-service, so the two always match.
resolve_persistent_secret INTERNAL_SERVICE_SHARED_SECRET 32 \
    "$PLATFORM_CORE_ENV" INTERNAL_SERVICE_SHARED_SECRET \
    "$INFERENCE_ENV" MODEL_MANAGEMENT_SERVICE_INTERNAL_TOKEN

add_sed_replacement "PII_ENCRYPTION_KEY" "${PII_ENCRYPTION_KEY}"
add_sed_replacement "SERVICE_CREDENTIALS_ENCRYPTION_KEY" "${SERVICE_CREDENTIALS_ENCRYPTION_KEY}"
add_sed_replacement "INTERNAL_SERVICE_SHARED_SECRET" "${INTERNAL_SERVICE_SHARED_SECRET}"

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
