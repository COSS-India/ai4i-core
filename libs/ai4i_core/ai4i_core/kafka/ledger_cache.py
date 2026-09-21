"""Redis-backed fast-path cache mirroring ledger_notification_alert.status —
a pre-check in front of the real atomic DB UPSERT in ledger.py, never a
substitute for it.

The DB's guarded UPSERT (INSERT ... ON CONFLICT ... WHERE status IS
DISTINCT FROM EXCLUDED.status) is what stays authoritative under
concurrent/multi-replica writes — that's the actual correctness mechanism
(design doc §5-7). This cache exists only to skip that DB round trip on the
very common case where the status genuinely hasn't changed since it was
last recorded (nothing to record, nothing to publish): a repeated
BUDGET_THRESHOLD check on a tenant sitting at the same percent, or a
BUDGET_EXHAUSTED check on a tenant that's already been marked exhausted.

Backed by Redis (not process memory) so this fast path actually hits for
multi-replica producers too — a status recorded by one replica is now
visible to every other replica's pre-check, not just the one that wrote it.
That closes the old gap where each replica only ever saw its own writes and
fell through to the DB for anything recorded elsewhere, same rationale as
notification_settings_cache's move and the tenant budget counter's move to
an atomic Redis primitive.

Being wrong here is always safe, never wrong-in-a-way-that-matters: a
stale or missing cache entry only ever causes one extra DB call (falling
through to the real UPSERT, which still answers correctly) — it can never
cause a missed dedup or a duplicate publish, because the DB WHERE clause is
what actually decides "is this new", not this cache. A cache HIT (status
matches exactly) is what's trusted to skip the DB entirely.

TTL 1 hour, same bound as notification_settings_cache, implemented as a
native Redis key TTL (SETEX) rather than a manually-tracked timestamp — a
stale entry simply expires out of Redis and the next check falls through to
the DB, same self-healing behaviour as before.
"""
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

TTL_SECONDS = 3600
KEY_PREFIX = "core:notif_ledger:"

_redis_client = None


def configure(redis_client) -> None:
    """Set the Redis client this module reads/writes through — same
    reasoning and same call as notification_settings_cache.configure()
    (see its docstring): not every service uses ai4i_core.bootstrap's own
    Redis singleton, so it's threaded in explicitly rather than assumed."""
    global _redis_client
    _redis_client = redis_client


def get_redis_client():
    if _redis_client is None:
        raise RuntimeError("ledger_cache.configure(redis_client) was not called")
    return _redis_client


def _key(notification_id: int, tenant_id: str, subject_json: str, channel: str) -> str:
    return f"{KEY_PREFIX}{notification_id}:{tenant_id}:{subject_json}:{channel}"


async def matches_cached_status(
    notification_id: int, tenant_id: str, subject_json: str, channel: str, status: Dict[str, Any]
) -> bool:
    """True only when this exact status["value"] is already known (in
    Redis, from any replica) to be current for this row — safe to skip the
    DB entirely. False for a miss, an expired entry, a different value, or
    a Redis error (all of which fall through to the DB).

    Compares only status["value"], not the whole {"value", "delivery"}
    object — delivery is updated independently downstream (the consumer
    marking a row sent/failed/skipped after this producer already wrote
    "in_progress"), and that alone must never look like "this is a new
    occurrence" to either this cache or the DB's own guard (ledger.py's
    _UPSERT_SQL WHERE clause makes the identical comparison)."""
    try:
        cached_value = await get_redis_client().hget(_key(notification_id, tenant_id, subject_json, channel), "value")
    except Exception as exc:
        logger.warning("Ledger cache read failed: %s", exc)
        return False
    if cached_value is None:
        return False
    return cached_value == _encode_value(status.get("value"))


async def set_cached_status(
    notification_id: int, tenant_id: str, subject_json: str, channel: str, status: Dict[str, Any]
) -> None:
    """Record `status` as the row's now-current value — called after any DB
    check (whether it changed the row or found it already matching), since
    either outcome confirms the DB now holds exactly this status."""
    key = _key(notification_id, tenant_id, subject_json, channel)
    try:
        redis = get_redis_client()
        pipe = redis.pipeline()
        pipe.hset(key, "value", _encode_value(status.get("value")))
        pipe.expire(key, TTL_SECONDS)
        await pipe.execute()
    except Exception as exc:
        logger.warning("Ledger cache write failed: %s", exc)


def _encode_value(value: Any) -> str:
    """status["value"] is a bool, int, or ISO timestamp string (design doc
    §6) — stringifying is enough to compare exactly since none of those
    three shapes are ambiguous once stringified (True/False never collide
    with an int or a timestamp string)."""
    return str(value)
