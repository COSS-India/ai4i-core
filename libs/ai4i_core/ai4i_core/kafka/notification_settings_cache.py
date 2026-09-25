"""Shared in-memory cache of configs_notification_alert — used by every
producer (auth-service, platform-core-service, payperuse_consumer) to decide
whether a notification should even be attempted before publishing: is it
enabled for this tenant (GLOBAL rows always are; INSTITUTION rows depend on
that tenant's tenant_notification_subscription row)? and, for the 2 ALERT
rows, which % bands are configured?

Pull-through cache, TTL 1 hour: every read (is_notification_enabled,
get_threshold_bands, get_notification_id, get_channels) calls _ensure_fresh()
first, which reloads the whole table from `db` — the caller's own session,
already in scope at every producer call site — whenever the cache has never
loaded or TTL_SECONDS have elapsed since the last successful load. So a
"cache miss" (nothing loaded yet) and a "cache expiry" (loaded too long ago)
both resolve the same way: a synchronous refresh_all() right there in the
calling request/message-handling path, not a background job.

Kept fresh sooner than the TTL via Redis pub/sub, the same "policy_updates"-
style pattern platform-core-service's own PolicySyncService already uses for
an identical problem (an admin-editable table, cached in every reader,
invalidated the moment a writer changes it). The writer side is
catalog_service.update_catalog, which publishes to this channel on every
scope/thresholds change (and subscription_service.py on every subscribe/
unsubscribe toggle, since that flips an INSTITUTION-scope row's effective
enablement for one tenant). The listener doesn't refetch the row itself (it
has no DB session of its own) — it just calls invalidate(), which clears
the loaded-at timestamp so the very next read anywhere in this process does
the actual reload. That keeps the listener simple and means a config
change is visible on the next real notification-worthy event, not just
eventually via TTL.

Per-tenant subscription state (tenant_notification_subscription) is
deliberately NOT part of this cached blob — it's one row per (notification,
tenant), not a fixed 9-row table, so caching it here doesn't fit the "cache
everything, invalidate everything" model above. is_notification_enabled
reads it with a direct, uncached point query instead (see its docstring).

A refresh failure (DB unreachable) leaves whatever was cached before in
place rather than wiping it — a temporary DB outage degrades to serving
last-known settings, not to "everything disabled". _loaded_at is only
bumped on success, so the next read keeps retrying instead of waiting out
the full TTL again.

All 9 rows are cached and refreshed as a whole (a full re-SELECT, not a
per-name diff) — the table is tiny (9 rows), so simplicity wins over a
partial-refresh optimisation that isn't needed at this scale.
"""
import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

CHANNEL = "notification_alert_updates"
TTL_SECONDS = 3600

_rows: Dict[str, Dict[str, Any]] = {}
_loaded_at: float = 0.0
_refresh_lock = asyncio.Lock()
_listener_task: Optional[asyncio.Task] = None


def _active_threshold_percentages(thresholds) -> List[int]:
    """Accepts either shape config.thresholds has ever been stored in: the
    current list of {"percentage": int, "active": bool} bands
    (catalog_service.py), or the pre-migration dict keyed by percent-as-
    string ({"70": false, ...}). A row still holding the old shape must not
    blow up refresh_all — that would leave _rows empty and silently disable
    every notification (not just thresholds), since is_notification_enabled
    reads from this same cache for all 9 rows."""
    if isinstance(thresholds, dict):
        return sorted(int(pct) for pct, enabled in thresholds.items() if enabled)
    return sorted(band["percentage"] for band in thresholds if band.get("active"))


async def refresh_all(db) -> None:
    """Reload every row from configs_notification_alert. Called lazily by
    _ensure_fresh() (cache miss or TTL expiry), and explicitly once at
    startup for a warm first request."""
    global _rows, _loaded_at
    try:
        result = await db.execute(
            text("SELECT id, name, scope, channels, config FROM configs_notification_alert")
        )
        new_rows: Dict[str, Dict[str, Any]] = {}
        for row in result.all():
            thresholds = (row.config or {}).get("thresholds", [])
            new_rows[row.name] = {
                "id": row.id,
                "scope": row.scope,
                "channels": list(row.channels or []),
                "threshold_bands": _active_threshold_percentages(thresholds),
            }
        _rows = new_rows
        _loaded_at = time.monotonic()
        logger.info("Notification settings cache loaded: %d row(s)", len(_rows))
    except Exception as exc:
        logger.warning("Notification settings cache refresh failed: %s", exc)


def invalidate() -> None:
    """Force the next read (in this process) to reload from DB regardless
    of TTL — called by the pub/sub listener on a catalog change."""
    global _loaded_at
    _loaded_at = 0.0


async def _ensure_fresh(db) -> None:
    """Reload if the cache has never loaded or TTL_SECONDS have elapsed
    since the last successful load. Lock-guarded so concurrent callers
    hitting expiry at the same moment don't all fire their own reload —
    the second (and later) callers just wait for the first's result."""
    if _rows and (time.monotonic() - _loaded_at) < TTL_SECONDS:
        return
    async with _refresh_lock:
        if _rows and (time.monotonic() - _loaded_at) < TTL_SECONDS:
            return
        await refresh_all(db)


async def is_notification_enabled(db, name: str, tenant_id: Optional[str] = None) -> bool:
    """False when the row is unknown (bad name, or missing even after a
    reload). A GLOBAL-scope row is always enabled — no per-institution
    opt-out. An INSTITUTION-scope row is enabled only when this tenant has
    actually subscribed (tenant_notification_subscription.subscribed) — a
    row absence for this (notification, tenant) pair reads as
    "unsubscribed", same as the subscription API's own read path
    (subscription_service._to_subscription_item). tenant_id is required for
    an INSTITUTION-scope row; omitting it (or passing None) fails closed
    (False) rather than guessing — there's no tenant to check a
    subscription for.

    This is a direct, uncached point query against
    tenant_notification_subscription's own unique index — not folded into
    the in-memory blob above, since that cache is a fixed 9-row table and
    this is one row per (notification, tenant). See the module docstring."""
    await _ensure_fresh(db)
    entry = _rows.get(name)
    if entry is None:
        return False
    if entry["scope"] == "GLOBAL":
        return True
    if not tenant_id:
        return False
    result = await db.execute(
        text(
            "SELECT subscribed FROM tenant_notification_subscription"
            " WHERE notification_id = :notification_id AND tenant_id = :tenant_id"
        ),
        {"notification_id": entry["id"], "tenant_id": str(tenant_id)},
    )
    row = result.first()
    return bool(row and row.subscribed)


async def get_threshold_bands(db, name: str) -> List[int]:
    """Sorted list of enabled percent bands for name (QUOTA_THRESHOLD /
    BUDGET_THRESHOLD) — [] for any other name or an unknown one."""
    await _ensure_fresh(db)
    entry = _rows.get(name)
    return entry["threshold_bands"] if entry else []


async def get_notification_id(db, name: str) -> Optional[int]:
    """configs_notification_alert.id for name — the ledger table's FK.
    None for an unknown name."""
    await _ensure_fresh(db)
    entry = _rows.get(name)
    return entry["id"] if entry else None


async def get_channels(db, name: str) -> List[str]:
    """Configured delivery channels for name (e.g. ["EMAIL"]) — one ledger
    row is written per channel. [] for an unknown name."""
    await _ensure_fresh(db)
    entry = _rows.get(name)
    return entry["channels"] if entry else []


def start_listener(redis_client) -> None:
    """Subscribe to the Redis notification_alert_updates channel and
    invalidate the cache on each message — no DB session needed here, the
    next real read anywhere in this process does the actual reload.

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
                    invalidate()
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
