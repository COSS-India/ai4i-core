"""backfill budget-exhausted for keys with no allocated_budget

APIKeyService.create_api_key now treats allocated_budget IS NULL as
exhausted unconditionally (previously only blocked when the owning Tenant
ALSO had no Budget - a Key under an Application deliberately left with no
budget of its own, even under a funded Tenant, was "intentionally
uncapped" and never flagged). That fix only changes what NEW
create_api_key calls do; a Key created before it shipped already has its
cached_data written WITHOUT budget-exhausted, and nothing else ever
re-visits it - the allocation engine only recomputes this flag for a Key
that actually participates in a Budget Allocation edit. A Key whose
Application was never touched by one stays exactly as it was created,
serving every request indefinitely with no budget_usage row and no
enforcement.

Two things this backfill must get right, both raised in review:

1. Eligibility must match APIKeyRepository._active_key_conditions(
   require_cached_data=True) EXACTLY: is_active, not expired, AND
   cached_data IS NOT NULL. cached_data is nullable and stays NULL for a
   key created while its Application/Tenant was inactive, or a legacy row
   - every in-app writer (set_budget_exhausted_for_key,
   patch_cached_data_field_for_keys) deliberately skips those rows, because
   _rehydrate_cache_from_db treats a NULL cached_data as fail-closed
   (raises InvalidAPIKeyError, i.e. 401). COALESCE-ing a NULL into
   '{}'::jsonb here would manufacture a non-empty {"budget-exhausted": "1"}
   snapshot for a row nothing else ever intended to serve at all - turning
   a 401 into a 429 immediately, and worse, making that row eligible for a
   LATER per-key allocation edit to write "budget-exhausted": "0" onto it,
   at which point it rehydrates as a fully VALID key with an EMPTY
   permission list. Excluding cached_data IS NULL rows (same as every
   other writer) avoids all of that.

2. DB-only is not enough. An already-cached Redis hash for one of these
   keys keeps serving its current (unflagged) state until it naturally
   expires - up to api_key_expire_days (default 365) - or is refreshed by
   an unrelated write path. For a key actually in active use (exactly the
   population this exists to fix), that is not a bound worth relying on.
   So this also pushes budget-exhausted=1 directly onto Redis for any of
   these keys currently resident there, mirroring
   APIKeyService.set_budget_exhausted_for_keys's own "HSET only if the
   Redis hash already exists" behaviour (patch_api_key_cache_field) rather
   than manufacturing a Redis entry that was never populated.

Idempotent - safe to re-run.

Revision ID: f3a9b1c7d2e6
Revises: 569df8229653
Create Date: 2026-09-17 00:00:00.000000

"""
import logging
import os
from typing import Sequence, Union

from alembic import op
import redis
import sqlalchemy as sa

revision: str = 'f3a9b1c7d2e6'
down_revision: Union[str, None] = '569df8229653'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, None] = None

logger = logging.getLogger("alembic.runtime.migration")

# Mirrors app.services.cache_service.REDIS_API_KEY_PREFIX - kept as a
# literal here (not imported) since a migration must not depend on the
# service's app package being importable/initializable in every
# environment this runs in.
_REDIS_API_KEY_PREFIX = "auth:apikey:"
_BUDGET_EXHAUSTED_FIELD = "budget-exhausted"


def _env_host_port(host_var: str, port_var: str, default_port: int) -> tuple[str, int]:
    """Read a host/port pair from two env vars, tolerating Kubernetes'
    auto-injected Docker-links-style value for a Service literally named
    the same as the var prefix (e.g. a "redis" Service makes Kubernetes
    inject REDIS_PORT=tcp://10.100.206.16:6379 into every pod in the
    namespace, clobbering a plain-integer REDIS_PORT the deployment itself
    never set) - "tcp://host:port" in either var is parsed for its real
    host/port instead of failing int() outright."""
    from urllib.parse import urlparse

    raw_host = os.getenv(host_var, "localhost")
    raw_port = os.getenv(port_var, str(default_port))
    host, port = raw_host, default_port
    if "://" in raw_host:
        parsed = urlparse(raw_host)
        host = parsed.hostname or host
        port = parsed.port or port
    if "://" in raw_port:
        parsed = urlparse(raw_port)
        host = parsed.hostname or host
        port = parsed.port or port
    else:
        port = int(raw_port)
    return host, port


def _redis_client() -> "redis.Redis | None":
    """Best-effort sync Redis client from the same env vars app.core.config
    reads (REDIS_HOST/PORT/DB/PASSWORD) - read directly rather than
    importing app.core.config, so this migration doesn't depend on the
    full app settings module (JWT keys, PII crypto, ...) initializing
    cleanly in whatever environment runs migrations. Returns None (logged,
    not raised) whenever this can't stand up a working client for ANY
    reason - unreachable Redis, or an env var in an unexpected shape (see
    _env_host_port) - since the DB half of this backfill must still land
    even when Redis is unavailable at migration time: the Redis half is a
    best-effort acceleration of the self-heal, not the correctness-bearing
    half (the DB write, and the entry's own TTL, get there eventually
    either way). Deliberately catches broadly (not just redis.RedisError)
    - a crash here must never take the whole migration transaction down
    with it, rolling back the DB backfill that had already succeeded."""
    try:
        host, port = _env_host_port("REDIS_HOST", "REDIS_PORT", 6379)
        db = int(os.getenv("REDIS_DB", "0"))
        password = os.getenv("REDIS_PASSWORD") or None
        client = redis.Redis(
            host=host, port=port, db=db, password=password,
            decode_responses=True, socket_timeout=5, socket_connect_timeout=5,
        )
        client.ping()
        return client
    except Exception as exc:  # noqa: BLE001 - see docstring: must never crash the migration
        logger.warning(
            "f3a9b1c7d2e6: could not set up a Redis client (%s) - DB backfill will still "
            "run; already-cached keys self-heal on their own TTL/next refresh instead.",
            exc,
        )
        return None


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            """
            SELECT id, api_key
            FROM api_key
            WHERE allocated_budget IS NULL
              AND is_active = true
              AND (expires_at IS NULL OR expires_at > now())
              AND cached_data IS NOT NULL
            """
        )
    )
    rows = result.fetchall()
    if not rows:
        logger.info("f3a9b1c7d2e6: no eligible key(s) to backfill.")
        return

    api_key_ids = [row.id for row in rows]
    conn.execute(
        sa.text(
            """
            UPDATE api_key
            SET cached_data = cached_data || '{"budget-exhausted": "1"}'::jsonb
            WHERE id = ANY(:ids)
            """
        ),
        {"ids": api_key_ids},
    )
    logger.info(
        "f3a9b1c7d2e6: backfilled budget-exhausted in cached_data for %d key(s).",
        len(api_key_ids),
    )

    redis_client = _redis_client()
    if redis_client is None:
        return
    patched = 0
    try:
        for row in rows:
            key = f"{_REDIS_API_KEY_PREFIX}{row.api_key}"
            if redis_client.exists(key):
                redis_client.hset(key, _BUDGET_EXHAUSTED_FIELD, "1")
                patched += 1
    finally:
        redis_client.close()
    logger.info(
        "f3a9b1c7d2e6: pushed budget-exhausted onto %d already-cached Redis key(s).",
        patched,
    )


def downgrade() -> None:
    # Data-correction migration; which rows were touched (vs. already having
    # budget-exhausted=1 from some other, legitimate reason) isn't
    # recoverable, so downgrade is a no-op.
    pass
