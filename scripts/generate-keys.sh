#!/usr/bin/env bash
#
# generate-keys.sh — Generate RS256 RSA key pairs for the auth service.
#
# Reads RS256_KEY_DIRECTORY and RS256_MIN_KEY_COUNT from the auth service's
# .env (services/auth-service-v2/.env) and ensures at least that many PEM
# key pairs exist on disk, using the naming convention:
#
#     key_01_private.pem / key_01_public.pem
#     key_02_private.pem / key_02_public.pem
#     ...
#
# Idempotent by default — existing key slots are skipped. Use --force to
# overwrite.
#
# Usage:
#   ./scripts/generate-keys.sh                 # top up to RS256_MIN_KEY_COUNT
#   ./scripts/generate-keys.sh --count 15      # ensure at least 15 pairs
#   ./scripts/generate-keys.sh --key-size 4096
#   ./scripts/generate-keys.sh --dir /custom/path
#   ./scripts/generate-keys.sh --force         # overwrite existing pairs
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
AUTH_SERVICE_DIR="$ROOT_DIR/services/auth-service-v2"
AUTH_ENV="$AUTH_SERVICE_DIR/.env"

# ── 1. Parse CLI args ───────────────────────────────────────────────────────
DIR_OVERRIDE=""
COUNT_OVERRIDE=""
KEY_SIZE=2048
FORCE=false

usage() {
    sed -n '2,21p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit "${1:-0}"
}

while [ $# -gt 0 ]; do
    case "$1" in
        --dir)       DIR_OVERRIDE="$2"; shift 2 ;;
        --count)     COUNT_OVERRIDE="$2"; shift 2 ;;
        --key-size)  KEY_SIZE="$2"; shift 2 ;;
        --force)     FORCE=true; shift ;;
        -h|--help)   usage 0 ;;
        *) echo "ERROR: unknown argument: $1" >&2; usage 1 ;;
    esac
done

case "$KEY_SIZE" in
    2048|3072|4096) ;;
    *) echo "ERROR: --key-size must be 2048, 3072, or 4096 (got $KEY_SIZE)" >&2; exit 2 ;;
esac

# ── 2. Read RS256_* from auth service .env (unless overridden) ──────────────
read_env_var() {
    local var_name="$1"
    local file="$2"
    [ -f "$file" ] || { echo ""; return 0; }
    grep -m1 "^${var_name}=" "$file" 2>/dev/null | cut -d'=' -f2- || true
}

if [ -n "$DIR_OVERRIDE" ]; then
    KEY_DIR="$DIR_OVERRIDE"
else
    RS256_KEY_DIRECTORY="$(read_env_var RS256_KEY_DIRECTORY "$AUTH_ENV")"
    RS256_KEY_DIRECTORY="${RS256_KEY_DIRECTORY:-keys}"
    # Relative paths are resolved against the auth service root, matching
    # how the service itself interprets RS256_KEY_DIRECTORY at runtime.
    if [[ "$RS256_KEY_DIRECTORY" = /* ]]; then
        KEY_DIR="$RS256_KEY_DIRECTORY"
    else
        KEY_DIR="$AUTH_SERVICE_DIR/$RS256_KEY_DIRECTORY"
    fi
fi

if [ -n "$COUNT_OVERRIDE" ]; then
    TARGET_COUNT="$COUNT_OVERRIDE"
else
    RS256_MIN_KEY_COUNT="$(read_env_var RS256_MIN_KEY_COUNT "$AUTH_ENV")"
    TARGET_COUNT="${RS256_MIN_KEY_COUNT:-10}"
fi

if ! [[ "$TARGET_COUNT" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: target count must be a positive integer (got '$TARGET_COUNT')" >&2
    exit 2
fi

# ── 3. Summary ──────────────────────────────────────────────────────────────
echo "Key directory : $KEY_DIR"
echo "Target pairs  : $TARGET_COUNT"
echo "Key size      : $KEY_SIZE bits"
echo "Force rewrite : $FORCE"
echo ""

mkdir -p "$KEY_DIR"

# ── 4. Generate key pairs ───────────────────────────────────────────────────
generated=0
skipped=0

for i in $(seq 1 "$TARGET_COUNT"); do
    kid=$(printf "key_%02d" "$i")
    priv_path="$KEY_DIR/${kid}_private.pem"
    pub_path="$KEY_DIR/${kid}_public.pem"

    if [ -f "$priv_path" ] && [ -f "$pub_path" ] && [ "$FORCE" = false ]; then
        echo "  [skip] $kid already exists"
        skipped=$((skipped + 1))
        continue
    fi

    if [ -f "$priv_path" ] || [ -f "$pub_path" ]; then
        if [ "$FORCE" = true ]; then
            echo "  [force] overwriting $kid"
        else
            echo "  [fix]  completing partial $kid"
        fi
        rm -f "$priv_path" "$pub_path"
    fi

    # PKCS#8 unencrypted private key (matches what load_pem_private_key expects
    # with password=None in app/core/security.py).
    openssl genpkey \
        -algorithm RSA \
        -pkeyopt "rsa_keygen_bits:$KEY_SIZE" \
        -out "$priv_path" \
        -quiet 2>/dev/null

    chmod 600 "$priv_path" 2>/dev/null || true

    # SubjectPublicKeyInfo-encoded public key.
    openssl rsa -in "$priv_path" -pubout -out "$pub_path" 2>/dev/null

    echo "  [ok]   generated $kid (${KEY_SIZE}-bit)"
    generated=$((generated + 1))
done

echo ""
echo "Done. Generated $generated new key pair(s); $skipped already present."
