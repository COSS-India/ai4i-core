"""In-memory cache of configs_notification_alert, keyed by event name.

Design doc §8, step 2: "read from an in-memory cache that refreshes from the
database once an hour." Process-local — this consumer runs one instance
today (design doc doesn't call for more), so there's no cross-instance
invalidation to build; a PATCH made through the Catalog API is picked up
here within CONFIG_CACHE_TTL_SECONDS, not instantly.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from ai4i_core.logging import get_logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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
        return (time.monotonic() - self._loaded_at) >= Constants.CONFIG_CACHE_TTL_SECONDS

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


async def get_config(db: AsyncSession, event_name: str) -> Optional[NotificationConfig]:
    return await _cache.get(db, event_name)
