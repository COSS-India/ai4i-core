"""
In-memory tier_id → status cache for the /auth/validate hot path.

Validation must stay DB-free on every request. The tier's status (ACTIVE /
DEACTIVATED / …) is needed to refuse requests when a tenant's tier is
deactivated, but the tier row lives in platform-core, not auth-service. This
cache solves that: it loads {tier_id: status} from the platform-core DB at
startup and refreshes every N seconds in the background — the same pattern as
role_permission_cache.py and tenant_name_cache.py.

Fail-open on an empty cache: if the platform-core DB is not configured, or
the first load has not completed yet, an unknown tier is treated as ACTIVE and
logged. Blocking all API-key traffic because a cache has not loaded is a
self-inflicted outage; failing open is the deliberate choice here.
"""

import logging
from typing import Optional

from sqlalchemy import text

from app.core.database import get_platform_core_session_factory
from app.services.refreshing_cache import DEFAULT_REFRESH_INTERVAL_SECONDS, RefreshingCache

logger = logging.getLogger(__name__)

_ACTIVE_STATUS = "ACTIVE"


class TierStatusCache(RefreshingCache):
    def __init__(self, refresh_interval_seconds: int = DEFAULT_REFRESH_INTERVAL_SECONDS) -> None:
        super().__init__(refresh_interval_seconds)
        self._statuses: dict[str, str] = {}

    def get_status(self, tier_id: str) -> Optional[str]:
        """Return the cached status string for ``tier_id``, or None on a miss."""
        return self._statuses.get(tier_id)

    def is_active(self, tier_id: str) -> bool:
        """True when the tier is ACTIVE or unknown (fail-open).

        An empty cache (platform-core DB not configured, or first load pending)
        returns True for every tier so that a cold start never blocks traffic.
        """
        status = self._statuses.get(tier_id)
        if status is None:
            if self._statuses:
                # Cache is loaded but tier is genuinely unknown — log and fail open.
                logger.warning(
                    "TierStatusCache: tier_id %s not found in cache; treating as ACTIVE (fail-open).",
                    tier_id,
                )
            return True
        return status == _ACTIVE_STATUS

    def _loaded_count(self) -> int:
        return len(self._statuses)

    async def reload(self) -> None:
        """Read all tier id→status pairs from the platform-core DB."""
        factory = get_platform_core_session_factory()
        if factory is None:
            logger.debug("TierStatusCache: platform-core DB not configured; skipping reload.")
            return
        new_map: dict[str, str] = {}
        async with factory() as session:
            result = await session.execute(
                text("SELECT id::text, status FROM tiers WHERE status != 'DELETED'")
            )
            for tier_id, status in result.all():
                new_map[tier_id] = status
        self._statuses = new_map
        logger.debug("TierStatusCache: reloaded %d tiers.", len(self._statuses))


# Module-level singleton — started in lifespan (main.py).
tier_status_cache = TierStatusCache()
