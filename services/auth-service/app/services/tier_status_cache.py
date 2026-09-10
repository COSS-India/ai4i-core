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

from app.core.config import settings
from app.core.database import get_platform_core_session_factory
from app.services.refreshing_cache import RefreshingCache

logger = logging.getLogger(__name__)

_ACTIVE_STATUS = "ACTIVE"


class TierStatusCache(RefreshingCache):
    def __init__(self, refresh_interval_seconds: int) -> None:
        super().__init__(refresh_interval_seconds)
        self._statuses: dict[str, str] = {}
        # True only after reload() has completed at least once — distinct from
        # _statuses being non-empty, which can happen via set_status() before
        # the first full load.
        self._ever_loaded: bool = False
        # Tracks tier_ids already warned this cycle so each unknown tier logs
        # at most once per reload interval rather than once per request.
        self._warned_ids: set[str] = set()

    def get_status(self, tier_id: str) -> Optional[str]:
        """Return the cached status string for ``tier_id``, or None on a miss."""
        return self._statuses.get(tier_id)

    def set_status(self, tier_id: str, status: str) -> None:
        """Immediately update one entry — used by push notifications from platform-core
        so that status changes take effect without waiting for the next reload cycle."""
        self._statuses[tier_id] = status

    def is_active(self, tier_id: str) -> bool:
        """True when the tier is ACTIVE or unknown (fail-open).

        Before the first reload() completes (including the window where
        set_status() may have populated a single entry), every tier is treated
        as ACTIVE and no warning is emitted — a cold-start should never block
        traffic or flood logs.

        After the first full load, each genuinely unknown tier_id is warned
        once per reload cycle (not once per request) to keep the hot-path
        log volume proportional to the number of unknown tiers, not to traffic.
        """
        status = self._statuses.get(tier_id)
        if status is None:
            if self._ever_loaded and tier_id not in self._warned_ids:
                self._warned_ids.add(tier_id)
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
        pre = dict(self._statuses)  # snapshot before the await window opens
        new_map: dict[str, str] = {}
        async with factory() as session:
            result = await session.execute(
                text("SELECT id::text, status FROM tiers WHERE status != 'DELETED'")
            )
            for tier_id, status in result.all():
                new_map[tier_id] = status
        for tier_id, db_status in new_map.items():
            # If _statuses[tier_id] differs from pre, a push landed during the
            # await window — keep the live pushed value instead of the stale DB value.
            if self._statuses.get(tier_id) == pre.get(tier_id):
                self._statuses[tier_id] = db_status
        for k in list(self._statuses):
            if k not in new_map:
                del self._statuses[k]
        self._ever_loaded = True
        self._warned_ids.clear()
        logger.debug("TierStatusCache: reloaded %d tiers.", len(self._statuses))


# Module-level singleton — started in lifespan (main.py).
tier_status_cache = TierStatusCache(settings.tier_status_cache_refresh_interval_seconds)
