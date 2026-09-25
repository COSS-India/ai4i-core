"""Shared Redis-backed cache of configs_notification_alert — used by every
producer (auth-service, platform-core-service, payperuse_consumer) to decide
whether a notification should even be attempted before publishing: is it
enabled (recipient_roles has at least one selected role)? and, for the 2
ALERT rows, which % bands are configured?

Backed by Redis (not process memory) so every service instance/replica reads
the identical cached settings instead of keeping its own copy — replicas no
longer drift for up to an hour, and a restarted instance finds the cache
already warm instead of starting cold. Same "move it into Redis, same TTL/
invalidation semantics, just shared" precedent as the tenant budget counter
(payperuse_consumer/_billing.py, INCRBYFLOAT replacing the in-process SUM).

Pull-through cache, TTL 1 hour: every read (is_notification_enabled,
get_threshold_bands, get_notification_id, get_channels) calls _load_rows()
first, which reloads the whole table from `db` — the caller's own session,
already in scope at every producer call site — whenever Redis has no cached
copy (never loaded, or the key expired). All 9 rows are stored as one JSON
blob under a single Redis key with a native TTL (SETEX), so "cache miss" and
"cache expiry" both resolve the same way: Redis simply no longer has the key,
and the next read anywhere, on any instance, does the real reload and
repopulates it for everyone else too.

Kept fresh sooner than the TTL via Redis pub/sub, the same "policy_updates"-
style pattern platform-core-service's own PolicySyncService already uses for
an identical problem (an admin-editable table, cached by every reader,
invalidated the moment a writer changes it). The writer side is
catalog_service.update_catalog, which publishes to this channel on every
recipient_roles/thresholds change. The listener doesn't refetch the row
itself (it has no DB session of its own) — it just deletes the Redis key,
which clears the cache for every instance at once, so the very next read
anywhere does the actual reload. That keeps the listener simple and means a
config change is visible on the next real notification-worthy event, not
just eventually via TTL.

A refresh failure (DB unreachable, or Redis unreachable) leaves whatever was
cached before in place rather than wiping it — a temporary DB/Redis outage
degrades to serving last-known settings, not to "everything disabled".
Redis is only written to on a successful DB read, so a failed refresh keeps
retrying on the next call instead of poisoning the cache with an empty
result.

configure(redis_client) must be called once at service startup (before
refresh_all()/any read) to hand this module the Redis client it should use
— see its docstring for why this isn't just ai4i_core.bootstrap's own
singleton.
"""
import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

CHANNEL = "notification_alert_updates"
TTL_SECONDS = 3600
CACHE_KEY = "core:notification_settings:all"

_refresh_lock = asyncio.Lock()
_listener_task: Optional[asyncio.Task] = None
_redis_client = None


def configure(redis_client) -> None:
    """Set the Redis client this module reads/writes through. Must be
    called once at service startup, before refresh_all()/any read — not
    every service uses ai4i_core.bootstrap's own Redis singleton (auth-
    service and platform-core-service each run their own local Redis
    client instead, kafka-consumers uses the shared one), so the client is
    threaded in explicitly rather than assumed."""
    global _redis_client
    _redis_client = redis_client


def get_redis_client():
    if _redis_client is None:
        raise RuntimeError(
            "notification_settings_cache.configure(redis_client) was not called"
        )
    return _redis_client


def _active_threshold_percentages(thresholds) -> List[int]:
    """Accepts either shape config.thresholds has ever been stored in: the
    current list of {"percentage": int, "active": bool} bands
    (catalog_service.py), or the pre-migration dict keyed by percent-as-
    string ({"70": false, ...}). A row still holding the old shape must not
    blow up refresh_all — that would leave the cache empty and silently
    disable every notification (not just thresholds), since
    is_notification_enabled reads from this same cache for all 9 rows."""
    if isinstance(thresholds, dict):
        return sorted(int(pct) for pct, enabled in thresholds.items() if enabled)
    return sorted(band["percentage"] for band in thresholds if band.get("active"))


async def refresh_all(db) -> None:
    """Reload every row from configs_notification_alert and store the whole
    table as one JSON blob in Redis with a fresh TTL. Called lazily by
    _ensure_fresh() (cache miss or TTL expiry), and explicitly once at
    startup for a warm first request."""
    try:
        result = await db.execute(
            text("SELECT id, name, recipient_roles, channels, config FROM configs_notification_alert")
        )
        new_rows: Dict[str, Dict[str, Any]] = {}
        for row in result.all():
            thresholds = (row.config or {}).get("thresholds", [])
            new_rows[row.name] = {
                "id": row.id,
                "recipient_roles": row.recipient_roles or {},
                "channels": list(row.channels or []),
                "threshold_bands": _active_threshold_percentages(thresholds),
            }
        await get_redis_client().set(CACHE_KEY, json.dumps(new_rows), ex=TTL_SECONDS)
        logger.info("Notification settings cache loaded: %d row(s)", len(new_rows))
    except Exception as exc:
        logger.warning("Notification settings cache refresh failed: %s", exc)


async def invalidate() -> None:
    """Delete the shared Redis cache key so the next read (on ANY instance)
    reloads from DB regardless of TTL — called by the pub/sub listener on a
    catalog change. A failed delete just means the entry lives out its TTL
    instead of being invalidated early."""
    try:
        await get_redis_client().delete(CACHE_KEY)
    except Exception as exc:
        logger.warning("Notification settings cache invalidation failed: %s", exc)


async def _load_rows(db) -> Dict[str, Dict[str, Any]]:
    """Return the cached table, refreshing from DB first when Redis has no
    copy (missing or expired). Lock-guarded so concurrent callers on this
    instance hitting a miss at the same moment don't all fire their own
    reload — the second (and later) callers just wait for the first's
    result."""
    try:
        cached = await get_redis_client().get(CACHE_KEY)
    except Exception as exc:
        logger.warning("Notification settings cache read failed: %s", exc)
        cached = None
    if cached is not None:
        return json.loads(cached)

    async with _refresh_lock:
        try:
            cached = await get_redis_client().get(CACHE_KEY)
        except Exception:
            cached = None
        if cached is not None:
            return json.loads(cached)
        await refresh_all(db)

    try:
        cached = await get_redis_client().get(CACHE_KEY)
    except Exception as exc:
        logger.warning("Notification settings cache read failed: %s", exc)
        cached = None
    return json.loads(cached) if cached is not None else {}


async def is_notification_enabled(db, name: str) -> bool:
    """False when the row is unknown (bad name, or missing even after a
    reload) or its recipient_roles has no role turned on — nobody to
    notify, so the caller should skip publishing entirely."""
    rows = await _load_rows(db)
    entry = rows.get(name)
    if entry is None:
        return False
    return any(entry["recipient_roles"].values())


async def get_threshold_bands(db, name: str) -> List[int]:
    """Sorted list of enabled percent bands for name (QUOTA_THRESHOLD /
    BUDGET_THRESHOLD) — [] for any other name or an unknown one."""
    rows = await _load_rows(db)
    entry = rows.get(name)
    return entry["threshold_bands"] if entry else []


async def get_notification_id(db, name: str) -> Optional[int]:
    """configs_notification_alert.id for name — the ledger table's FK.
    None for an unknown name."""
    rows = await _load_rows(db)
    entry = rows.get(name)
    return entry["id"] if entry else None


async def get_channels(db, name: str) -> List[str]:
    """Configured delivery channels for name (e.g. ["EMAIL"]) — one ledger
    row is written per channel. [] for an unknown name."""
    rows = await _load_rows(db)
    entry = rows.get(name)
    return entry["channels"] if entry else []


def start_listener(redis_client) -> None:
    """Subscribe to the Redis notification_alert_updates channel and
    invalidate the shared cache key on each message — no DB session needed
    here, the next real read anywhere (this instance or any other) does the
    actual reload.

    Parameters
    ----------
    redis_client : aioredis client instance
    """
    global _listener_task
    _listener_task = asyncio.create_task(
        _listen(redis_client), name="notification_settings_cache_listener"
    )


async def stop_listener() -> None:
    global _listener_task
    if _listener_task and not _listener_task.done():
        _listener_task.cancel()
        await asyncio.gather(_listener_task, return_exceptions=True)
    _listener_task = None


async def _listen(redis_client) -> None:
    while True:
        pubsub = redis_client.pubsub()
        try:
            await pubsub.subscribe(CHANNEL)
            logger.info("Notification settings cache listening on Redis channel '%s'", CHANNEL)
            async for message in pubsub.listen():
                if message.get("type") == "message":
                    await invalidate()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Notification settings cache listener error (reconnecting in 5s): %s", exc)
            await asyncio.sleep(5)
        finally:
            # Without this, a dropped/failed connection is never returned to
            # the client's pool — each retry then leaks one more pubsub
            # connection, eventually exhausting it ("Too many connections")
            # and permanently breaking this listener until the process is
            # restarted. Closing here (success, failure, or cancellation)
            # is what makes the retry loop actually safe to run indefinitely.
            try:
                await pubsub.aclose()
            except Exception:
                pass
