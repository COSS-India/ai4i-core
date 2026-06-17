#!/usr/bin/env bash

set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

ROOT_ENV="$ROOT_DIR/.env"
ROOT_TEMPLATE="$ROOT_DIR/env.template"
INFERENCE_ENV="$ROOT_DIR/services/inference-service/.env"
PLATFORM_ENV="$ROOT_DIR/services/platform-core-service/.env"
DEV_SECRETS="$ROOT_DIR/dev.secrets"

# Credentials are NEVER hardcoded in this (public) repo. They come from, in order:
#   1. AI4I_* environment variables, or
#   2. an untracked dev.secrets file (see dev.secrets.example) that exports them, or
#   3. a randomly-generated value (passwords only) so the one-command flow still works.
# Whatever is resolved is written ONCE into the gitignored root .env, which drives
# both the dockerised postgres/redis and every service .env (via setup-env.sh) —
# one source of truth, so container and service credentials always match.

# Escape a value for safe use on the right-hand side of a sed s|...|...| command
# (handles backslash, the | delimiter, and & which means "whole match").
_sed_escape() {
    printf '%s' "$1" | sed -e 's/[\\&|]/\\&/g'
}

# Generate a random secret. python3.11 is a prerequisite, openssl is near-universal;
# the date fallback is a last resort for local-only dev passwords.
gen_secret() {
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -hex 16
    elif command -v python3.11 >/dev/null 2>&1; then
        python3.11 -c 'import secrets; print(secrets.token_hex(16))'
    else
        date +%s%N | sha256sum 2>/dev/null | cut -c1-32 || echo "dev_local_changeme"
    fi
}

# Source an untracked dev.secrets file (if present) so its `export AI4I_*=...`
# lines populate the environment before we resolve credentials.
load_dev_secrets() {
    [[ -f "$DEV_SECRETS" ]] || return 0
    log "Sourcing $DEV_SECRETS for credential overrides"
    set -a
    # shellcheck disable=SC1090
    source "$DEV_SECRETS"
    set +a
}

# Create the root .env from the template, filling the credential placeholders.
# Never overwrites an existing .env.
create_root_env() {

    if [[ -f "$ROOT_ENV" ]]; then
        ok "Root .env already exists (left untouched)"
        return
    fi

    require_file "$ROOT_TEMPLATE"

    # Username isn't a secret — a stable default is fine. Passwords are resolved
    # from env/dev.secrets, else generated randomly (never a committed literal).
    local pg_user="${AI4I_POSTGRES_USER:-ai4i_user}"
    local pg_pass="${AI4I_POSTGRES_PASSWORD:-}"
    local redis_pass="${AI4I_REDIS_PASSWORD:-}"

    if [[ -z "$pg_pass" ]]; then
        pg_pass="$(gen_secret)"
        log "No AI4I_POSTGRES_PASSWORD provided — generated a random one (set it in dev.secrets to pin)"
    fi
    if [[ -z "$redis_pass" ]]; then
        redis_pass="$(gen_secret)"
        log "No AI4I_REDIS_PASSWORD provided — generated a random one"
    fi

    sed \
        -e "s|<YOUR_POSTGRES_USER>|$(_sed_escape "$pg_user")|g" \
        -e "s|<YOUR_POSTGRES_PASSWORD>|$(_sed_escape "$pg_pass")|g" \
        -e "s|<YOUR_REDIS_PASSWORD>|$(_sed_escape "$redis_pass")|g" \
        "$ROOT_TEMPLATE" > "$ROOT_ENV"

    ok "Created root .env (credentials from env / dev.secrets / generated)"

    warn_stale_postgres_volume
}

# Postgres only applies POSTGRES_USER/PASSWORD when it FIRST initialises its data
# volume. If a volume already exists (e.g. from an earlier run with different
# credentials), a freshly-generated .env won't match it and every service will
# fail to authenticate. Warn loudly when we detect that combination.
warn_stale_postgres_volume() {

    command -v docker >/dev/null 2>&1 || return 0

    local vol
    vol="$(docker volume ls -q 2>/dev/null | grep -i 'postgres-data' | head -1 || true)"

    if [[ -n "$vol" ]]; then
        warn "Existing postgres data volume detected: $vol"
        warn "Postgres sets credentials only on first init, so it may NOT match the"
        warn "new .env. If services fail to authenticate, reset the volume:"
        warn "    ./scripts/dev/down --prune     # or: ./scripts/dev/reset"
    fi
}

generate_service_envs() {

    require_file "$ROOT_DIR/scripts/setup-env.sh"

    chmod +x "$ROOT_DIR/scripts/setup-env.sh"

    (
        cd "$ROOT_DIR"
        ./scripts/setup-env.sh
    )

    ok "Generated service .env files"
}

# Fill the SMTP placeholders that setup-env.sh doesn't handle, in the generated
# platform-core .env, from AI4I_SMTP_* env vars. Defaults to EMPTY (alert email
# simply stays disabled). The live secret is never committed — supply it at run
# time, e.g.:
#   AI4I_SMTP_AUTH_USERNAME=... AI4I_SMTP_AUTH_PASSWORD=... ./scripts/dev/up
fill_smtp() {

    [[ -f "$PLATFORM_ENV" ]] || return 0

    local user="${AI4I_SMTP_AUTH_USERNAME:-}"
    local pass="${AI4I_SMTP_AUTH_PASSWORD:-}"

    sed -i.bak \
        -e "s|<YOUR_SMTP_USERNAME>|$(_sed_escape "$user")|g" \
        -e "s|<YOUR_SMTP_PASSWORD>|$(_sed_escape "$pass")|g" \
        "$PLATFORM_ENV"
    rm -f "$PLATFORM_ENV.bak"

    if [[ -n "${AI4I_SMTP_SMARTHOST:-}" ]]; then
        sed -i.bak "s|^SMTP_SMARTHOST=.*|SMTP_SMARTHOST=$(_sed_escape "$AI4I_SMTP_SMARTHOST")|" "$PLATFORM_ENV"
        rm -f "$PLATFORM_ENV.bak"
    fi

    if [[ -n "${AI4I_SMTP_FROM:-}" ]]; then
        sed -i.bak "s|^SMTP_FROM=.*|SMTP_FROM=$(_sed_escape "$AI4I_SMTP_FROM")|" "$PLATFORM_ENV"
        rm -f "$PLATFORM_ENV.bak"
    fi

    if [[ -n "$user$pass" ]]; then
        log "Injected SMTP credentials from AI4I_SMTP_* env vars"
    else
        log "No AI4I_SMTP_* env vars set — alert email left disabled (placeholders cleared)"
    fi

    return 0
}

bootstrap_env() {

    log "Bootstrapping environment..."

    load_dev_secrets

    create_root_env

    generate_service_envs

    fill_smtp
}

# Flip KAFKA_ENABLED in the inference-service .env so the trace exporter ships
# spans to Kafka while the logging stack is up, and degrades to stdout-only
# afterwards (plan § 5). `up` sets true for logging/all; `down` reverts to false.
toggle_kafka() {

    local enabled="$1"

    [[ -f "$INFERENCE_ENV" ]] || return 0

    if grep -q '^KAFKA_ENABLED=' "$INFERENCE_ENV"; then
        # -i.bak works on both GNU and BSD sed; remove the backup afterwards.
        sed -i.bak "s/^KAFKA_ENABLED=.*/KAFKA_ENABLED=${enabled}/" "$INFERENCE_ENV"
        rm -f "$INFERENCE_ENV.bak"
    else
        printf '\nKAFKA_ENABLED=%s\n' "$enabled" >> "$INFERENCE_ENV"
    fi

    log "Set KAFKA_ENABLED=${enabled} in inference-service/.env"
}
