#!/usr/bin/env bash
#
# setup-env.sh — Generate per-service .env files from env.template files.
#
# Lives at: ai4i-core/docker-compose/scripts/setup-env.sh
# Writes into the ai4i-core tree (parent of docker-compose/).
#
# Usage (from ai4i-core/docker-compose/):
#   ./scripts/setup-env.sh
#
# Infra credentials in docker-compose/.env (POSTGRES_*, REDIS_PASSWORD, …) are
# synced into the repo-root .env before substitution so apps match Compose.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CORE_ROOT="$(cd "$COMPOSE_DIR/.." && pwd)"
COMPOSE_ENV="${COMPOSE_DIR}/.env"
ROOT_ENV="${CORE_ROOT}/.env"

looks_like_ai4i_core() {
    local candidate="$1"
    [ -f "${candidate}/env.template" ] && [ -d "${candidate}/services" ]
}

if ! looks_like_ai4i_core "${CORE_ROOT}"; then
    cat >&2 <<EOF
ERROR: ${CORE_ROOT} does not look like the ai4i-core repository root
(expected env.template and services/).

Run this script from ai4i-core/docker-compose/:
  cd /path/to/ai4i-core/docker-compose
  ./scripts/setup-env.sh
EOF
    exit 1
fi

echo "ai4i-core root: ${CORE_ROOT}"
echo "compose dir:    ${COMPOSE_DIR}"

# ── Helpers ──────────────────────────────────────────────────────────────────
read_env_file_var() {
    local file="$1"
    local var_name="$2"
    local value=""
    if [ -f "${file}" ]; then
        value=$(grep -m1 "^${var_name}=" "${file}" 2>/dev/null | cut -d'=' -f2- || true)
    fi
    echo "${value:-}"
}

# Prefer compose .env, then core root .env, then optional fallback file.
read_env_var() {
    local var_name="$1"
    local fallback_file="${2:-}"
    local value
    value="$(read_env_file_var "${COMPOSE_ENV}" "${var_name}")"
    if [ -z "${value}" ]; then
        value="$(read_env_file_var "${ROOT_ENV}" "${var_name}")"
    fi
    if [ -z "${value}" ] && [ -n "${fallback_file}" ]; then
        value="$(read_env_file_var "${fallback_file}" "${var_name}")"
    fi
    echo "${value:-}"
}

upsert_env_var() {
    local file="$1"
    local key="$2"
    local value="$3"
    if [ ! -f "${file}" ]; then
        return 0
    fi
    if grep -q "^${key}=" "${file}" 2>/dev/null; then
        local escaped
        escaped=$(printf '%s' "${value}" | sed -e 's/[|&\\]/\\&/g')
        sed -i -e "s|^${key}=.*|${key}=${escaped}|" "${file}"
    else
        printf '\n%s=%s\n' "${key}" "${value}" >> "${file}"
    fi
}

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
resolve_persistent_secret() {
    local name="$1"
    local bytes="$2"
    shift 2
    local value
    value="$(read_env_var "${name}")"
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

# ── 1. Ensure repo-root .env exists ──────────────────────────────────────────
if [ ! -f "${ROOT_ENV}" ]; then
    echo "Root .env not found — copying from env.template ..."
    cp "${CORE_ROOT}/env.template" "${ROOT_ENV}"
    echo "  Created ${ROOT_ENV}"
fi

# ── 1b. Sync infra credentials from compose .env → root .env ─────────────────
if [ -f "${COMPOSE_ENV}" ]; then
    echo "Syncing infra credentials from ${COMPOSE_ENV} → ${ROOT_ENV}"
    for key in \
        POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB POSTGRES_HOST POSTGRES_PORT \
        REDIS_PASSWORD REDIS_HOST REDIS_PORT \
        AUTH_DB_NAME MODEL_MANAGEMENT_DB_NAME \
        ALEMBIC_DB_HOST ALEMBIC_DB_PORT \
        KAFKA_SERVER \
        PLATFORM_NAME ADOPTER_LOGO_URL \
        LLM_UPSTREAM_BASE_URL
    do
        val="$(read_env_file_var "${COMPOSE_ENV}" "${key}")"
        if [ -n "${val}" ]; then
            upsert_env_var "${ROOT_ENV}" "${key}" "${val}"
        fi
    done
    upsert_env_var "${ROOT_ENV}" "POSTGRES_HOST" "localhost"
    upsert_env_var "${ROOT_ENV}" "REDIS_HOST" "localhost"
    upsert_env_var "${ROOT_ENV}" "ALEMBIC_DB_HOST" "localhost"
    kafka_port="$(read_env_file_var "${COMPOSE_ENV}" "KAFKA_EXTERNAL_PORT")"
    upsert_env_var "${ROOT_ENV}" "KAFKA_SERVER" "localhost:${kafka_port:-9092}"
else
    echo "NOTE: ${COMPOSE_ENV} not found — using values already in ${ROOT_ENV}"
    echo "      (copy .env.example → .env under docker-compose/ first)"
fi

# ── 2. Read shared values ────────────────────────────────────────────────────
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

PLATFORM_NAME="$(read_env_var PLATFORM_NAME "${CORE_ROOT}/env.template")"
ADOPTER_LOGO_URL="$(read_env_var ADOPTER_LOGO_URL "${CORE_ROOT}/env.template")"

: "${POSTGRES_HOST:=localhost}"
: "${POSTGRES_PORT:=5432}"
: "${ALEMBIC_DB_HOST:=localhost}"
: "${ALEMBIC_DB_PORT:=5432}"
: "${AUTH_DB_NAME:=ai4iplatform_auth}"
: "${MODEL_MANAGEMENT_DB_NAME:=ai4iplatform_core}"

# ── 3. Build sed replacement expressions ─────────────────────────────────────
SED_ARGS=()

sed_escape() {
    printf '%s' "$1" | sed -e 's/[&\\|]/\\&/g'
}

add_sed_replacement() {
    local placeholder="$1"
    local value="$2"
    if [ -z "${value}" ]; then
        return 0
    fi
    SED_ARGS+=(-e "s|<${placeholder}>|$(sed_escape "${value}")|g")
}

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
AUTH_ENV="${CORE_ROOT}/services/auth-service/.env"
PLATFORM_CORE_ENV="${CORE_ROOT}/services/platform-core-service/.env"
INFERENCE_ENV="${CORE_ROOT}/services/inference-service/.env"

resolve_persistent_secret PII_ENCRYPTION_KEY 64 \
    "${AUTH_ENV}" PII_ENCRYPTION_KEY \
    "${PLATFORM_CORE_ENV}" PII_ENCRYPTION_KEY
resolve_persistent_secret SERVICE_CREDENTIALS_ENCRYPTION_KEY 32 \
    "${PLATFORM_CORE_ENV}" SERVICE_CREDENTIALS_ENCRYPTION_KEY
resolve_persistent_secret INTERNAL_SERVICE_SHARED_SECRET 32 \
    "${PLATFORM_CORE_ENV}" INTERNAL_SERVICE_SHARED_SECRET \
    "${INFERENCE_ENV}" MODEL_MANAGEMENT_SERVICE_INTERNAL_TOKEN

add_sed_replacement "PII_ENCRYPTION_KEY" "${PII_ENCRYPTION_KEY}"
add_sed_replacement "SERVICE_CREDENTIALS_ENCRYPTION_KEY" "${SERVICE_CREDENTIALS_ENCRYPTION_KEY}"
add_sed_replacement "INTERNAL_SERVICE_SHARED_SECRET" "${INTERNAL_SERVICE_SHARED_SECRET}"

# ── 4. Process every env.template under ai4i-core ────────────────────────────
generated=0

while IFS= read -r -d '' template; do
    dir="$(dirname "${template}")"
    target="${dir}/.env"

    if [ "${template}" = "${CORE_ROOT}/env.template" ]; then
        continue
    fi

    case "${template}" in
        "${COMPOSE_DIR}"/*) continue ;;
    esac

    sed "${SED_ARGS[@]}" "${template}" > "${target}"

    # Service env.templates hardcode KAFKA_SERVER=localhost:9093 (old local compose).
    # This pack publishes Kafka on KAFKA_EXTERNAL_PORT (default 9092) — overwrite literals.
    kafka_server="$(read_env_file_var "${ROOT_ENV}" "KAFKA_SERVER")"
    if [ -z "${kafka_server}" ]; then
        kafka_port="$(read_env_file_var "${COMPOSE_ENV}" "KAFKA_EXTERNAL_PORT")"
        kafka_server="localhost:${kafka_port:-9092}"
    fi
    if grep -q "^KAFKA_SERVER=" "${target}" 2>/dev/null; then
        upsert_env_var "${target}" "KAFKA_SERVER" "${kafka_server}"
    fi

    echo "  GEN   ${target}"
    generated=$((generated + 1))

done < <(find "${CORE_ROOT}" -name "env.template" -not -path "*/node_modules/*" -print0 | sort -z)

echo ""
echo "Done — ${generated} .env file(s) generated."
echo "Kafka broker for host apps: ${kafka_server:-localhost:9092}"
echo "Next: run ./scripts/migrate.sh from the repo root (if not already done), then start services."
