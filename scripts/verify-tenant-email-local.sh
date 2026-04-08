#!/usr/bin/env bash
# Fetch pending email verification token from Postgres, call the verify API, then
# show the last multi-tenant log lines that may contain the generated admin password
# (only if LOG_TENANT_GENERATED_PASSWORDS=true was set before verify).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck source=/dev/null
if [[ -f .env ]]; then set -a && source .env && set +a; fi

TENANT_UUID="${1:-}"
VERIFY_BASE="${VERIFY_URL:-http://localhost:8080/api/v1/multi-tenant/email/verify}"
VERIFY_DIRECT="${MULTI_TENANT_VERIFY_URL:-http://localhost:8100/email/verify}"

if [[ -z "$TENANT_UUID" ]]; then
  echo "Usage: $0 <tenant_uuid>" >&2
  echo "  tenant_uuid = tenants.id (e.g. a7c5d73a-bc84-4c9a-8b67-ba5dc4fea607)" >&2
  echo "Optional env: VERIFY_URL (default gateway verify path), MULTI_TENANT_VERIFY_URL (direct service)" >&2
  exit 1
fi

if ! [[ "$TENANT_UUID" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]]; then
  echo "Invalid UUID: $TENANT_UUID" >&2
  exit 1
fi

PG_USER="${POSTGRES_USER:-postgres}"
PG_DB="${MULTI_TENANT_DB_NAME:-multi_tenant_db}"
PG_CONTAINER="${POSTGRES_CONTAINER:-ai4v-postgres}"
MT_CONTAINER="${MULTI_TENANT_CONTAINER:-ai4v-multi-tenant-service}"

TOKEN="$(
  docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -t -A -c \
    "SELECT token FROM tenant_email_verifications WHERE tenant_id = '$TENANT_UUID'::uuid AND verified_at IS NULL AND expires_at > NOW() ORDER BY created_at DESC LIMIT 1;" \
  | tr -d ' \r\n' || true
)"

if [[ -z "$TOKEN" ]]; then
  echo "No pending, non-expired verification token for tenant id $TENANT_UUID." >&2
  echo "If the tenant is already ACTIVE, use password reset or register again for testing." >&2
  exit 1
fi

echo "Calling verify (gateway): $VERIFY_BASE"
HTTP_CODE="$(curl -sS -o /tmp/ai4i_verify_body.txt -w "%{http_code}" -G "$VERIFY_BASE" --data-urlencode "token=$TOKEN" || true)"
cat /tmp/ai4i_verify_body.txt
echo
if [[ "$HTTP_CODE" != "200" ]]; then
  echo "Gateway returned HTTP $HTTP_CODE; trying direct multi-tenant: $VERIFY_DIRECT" >&2
  curl -sS -G "$VERIFY_DIRECT" --data-urlencode "token=$TOKEN" || true
  echo
fi

echo "--- Last multi-tenant log lines (password appears only if LOG_TENANT_GENERATED_PASSWORDS=true) ---"
docker logs "$MT_CONTAINER" 2>&1 | tail -120 | grep -E "Tenant admin credentials|LOG_TENANT_GENERATED_PASSWORDS" || {
  echo "(no credential log lines — set LOG_TENANT_GENERATED_PASSWORDS=true, recreate multi-tenant, then verify again on a PENDING tenant)"
}
