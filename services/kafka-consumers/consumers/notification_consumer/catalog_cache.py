"""In-memory cache of configs_notification_alert, keyed by event name.

Design doc §8, step 2: "read from an in-memory cache that refreshes from the
database once an hour" — that TTL is still the floor, but it's no longer the
only way this cache gets fresh: start_listener() below subscribes to the
SAME Redis channel (NOTIFICATION_SETTINGS_CHANNEL,
"notification_alert_updates") the shared producer-side cache
(libs/ai4i_core/ai4i_core/kafka/notification_settings_cache.py) listens on,
so a catalog PATCH is picked up within seconds rather than up to an hour
late. The channel name is imported, not re-typed, so a publisher and this
subscriber can never silently drift onto two different strings.

The message payload is never inspected — same as the shared lib's own
listener — any publish on this channel just means "something changed,
reload on next read." Whether platform-core-service's catalog_service
actually publishes there yet is a separate, already-flagged gap; this
listener is correct and inert either way — a channel with no publisher
just means this cache falls back to its TTL, same as before.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

import redis.asyncio as aioredis
from ai4i_core.kafka import NOTIFICATION_SETTINGS_CHANNEL
from ai4i_core.logging import get_logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from bootstrap.config import get_redis_settings
from consumers.notification_consumer.config import Constants

logger = get_logger(__name__)


@dataclass(frozen=True)
class NotificationConfig:
    """One row of configs_notification_alert, as this consumer needs it.

    No separate is_enabled column exists — "off" is expressed purely as
    "no role in recipient_roles is True" (handler.py's gate)."""

    id: int
    name: str
    type: str
    module: str
    channels: list
    recipient_roles: Dict[str, bool] = field(default_factory=dict)
    thresholds: Dict[str, bool] = field(default_factory=dict)


class _Cache:
    def __init__(self) -> None:
        self._by_name: Dict[str, NotificationConfig] = {}
        self._loaded_at: float = 0.0

    def _is_stale(self) -> bool:
        # Never-loaded must be unconditionally stale — time.monotonic()'s
        # reference point is unspecified (often system/VM boot), so on a
        # short-uptime host (WSL2 recently restarted, etc.) it can return a
        # value smaller than CONFIG_CACHE_TTL_SECONDS even on a process's
        # very first check. Comparing only against the clock let _by_name
        # stay permanently empty — this is what the shared producer-side
        # cache's own `if _rows and (...)` guard already protects against.
        if not self._by_name:
            return True
        return (time.monotonic() - self._loaded_at) >= Constants.CONFIG_CACHE_TTL_SECONDS

    def invalidate(self) -> None:
        """Force the next get() to reload regardless of TTL — called by the
        pub/sub listener on a catalog change. Same trick as the shared
        producer-side cache: just clear _loaded_at, no lock needed since
        the next real read does the actual (lock-free here — this cache
        has no concurrent-refresh guard, unlike the shared one, because
        this consumer processes one message at a time) reload."""
        self._loaded_at = 0.0

    async def get(self, db: AsyncSession, event_name: str) -> Optional[NotificationConfig]:
        if self._is_stale():
            await self._refresh(db)
        return self._by_name.get(event_name)

    async def _refresh(self, db: AsyncSession) -> None:
        result = await db.execute(
            text(
                "SELECT id, name, type, module, channels, recipient_roles, config"
                "  FROM configs_notification_alert"
            )
        )
        by_name: Dict[str, NotificationConfig] = {}
        for row in result.mappings():
            recipient_roles = row["recipient_roles"] or {}
            config = row["config"] or {}
            # Defensive: some raw-SQL/driver paths hand back jsonb as text
            # rather than an already-decoded object — never trust the shape.
            if isinstance(recipient_roles, str):
                import json
                recipient_roles = json.loads(recipient_roles) if recipient_roles else {}
            if isinstance(config, str):
                import json
                config = json.loads(config) if config else {}
            by_name[row["name"]] = NotificationConfig(
                id=row["id"],
                name=row["name"],
                type=row["type"],
                module=row["module"],
                channels=list(row["channels"] or []),
                recipient_roles=recipient_roles,
                thresholds=config.get("thresholds", {}) or {},
            )
        self._by_name = by_name
        self._loaded_at = time.monotonic()
        logger.info("Notification config cache refreshed | rows=%d", len(by_name))


_cache = _Cache()
_listener_task: Optional[asyncio.Task] = None


async def get_config(db: AsyncSession, event_name: str) -> Optional[NotificationConfig]:
    return await _cache.get(db, event_name)


def invalidate() -> None:
    """Force the next read (in this process) to reload from DB regardless
    of TTL. Called by the pub/sub listener below on a catalog change."""
    _cache.invalidate()


def start_listener() -> None:
    """Subscribe to NOTIFICATION_SETTINGS_CHANNEL and invalidate the cache
    on every message. Call once at startup (main.py, after infra() opens
    Redis) — but note this does NOT reuse the shared get_redis_client()
    connection (see _listen()'s docstring for why: its socket_timeout is
    wrong for a blocking pub/sub read). A dedicated connection is opened
    and closed by this module alone.
    """
    global _listener_task
    _listener_task = asyncio.create_task(_listen(), name="catalog_cache_listener")


async def stop_listener() -> None:
    global _listener_task
    if _listener_task and not _listener_task.done():
        _listener_task.cancel()
        await asyncio.gather(_listener_task, return_exceptions=True)
    _listener_task = None


async def _listen() -> None:
    """Own connection, socket_timeout=None — deliberately NOT the shared
    get_redis_client() one. That client is built with socket_timeout=10 (or
    whatever REDIS_TIMEOUT is), which is correct for ordinary request/reply
    calls but wrong here: pubsub.listen() blocks waiting for the NEXT
    message, which may legitimately be much more than 10s away. Sharing
    that client made this loop time out and reconnect every ~10-15s even
    when nothing was wrong — a silent, useless reconnect storm that not
    only spammed the log but could exhaust Redis's connection limit over
    time. A dedicated, no-timeout connection is what makes "block until a
    message arrives" actually mean that."""
    rd = get_redis_settings()
    while True:
        client = aioredis.from_url(rd.get_redis_url(), socket_timeout=None, decode_responses=True)
        pubsub = client.pubsub()
        try:
            await pubsub.subscribe(NOTIFICATION_SETTINGS_CHANNEL)
            logger.info(
                "Notification catalog cache listening on Redis channel '%s'",
                NOTIFICATION_SETTINGS_CHANNEL,
            )
            async for message in pubsub.listen():
                if message.get("type") == "message":
                    invalidate()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "Notification catalog cache listener error (reconnecting in 5s): %s", exc
            )
            await asyncio.sleep(5)
        finally:
            # Without this, a dropped/failed connection is never returned to
            # the client's pool — each retry then leaks one more pubsub
            # connection, eventually exhausting it and permanently breaking
            # this listener until the process is restarted.
            try:
                await pubsub.aclose()
            except Exception:
                pass
            try:
                await client.aclose()
            except Exception:
                pass
