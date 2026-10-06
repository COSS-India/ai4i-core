"""After a settings or subscription commit: rebuild the shared Redis value
and publish the invalidation, so every producer pod drops its L1 copy and
refills from Redis (ai4i_core.kafka). Never fails the request — a Redis
problem is a CACHE failure row, and staleness is bounded by the cache TTLs.
"""

import logging
from typing import Sequence

from ai4i_core.kafka import notifications_configured, refresh_settings, refresh_subscriptions

logger = logging.getLogger(__name__)


async def after_settings_write(names: Sequence) -> None:
    if not notifications_configured():
        return
    try:
        await refresh_settings(names)
    except Exception as exc:
        logger.warning("Notification settings refresh failed for %s: %s", list(names), exc)


async def after_subscription_write(tenant_ids: Sequence[str]) -> None:
    if not notifications_configured() or not tenant_ids:
        return
    try:
        await refresh_subscriptions([str(t) for t in tenant_ids])
    except Exception as exc:
        logger.warning("Notification subscription refresh failed for %d tenant(s): %s", len(tenant_ids), exc)
