"""Tier status and rate limit for /auth/validate: Redis first, DB on a miss.

platform-core writes ``core:tier:{tier_id}``; this only repairs a missing key
(flush, eviction, auth deployed first) with one SELECT, written back only if the
key is still absent. A tier unknown to both is treated as ACTIVE with no limit.
"""
import logging
from typing import Optional

from sqlalchemy import text

from app.core.database import get_platform_core_session_factory
from app.services.cache_service import CacheService

logger = logging.getLogger(__name__)

_TIER_SQL = text(
    "SELECT status::text, rate_limit FROM tiers WHERE id::text = :tier_id AND status != 'DELETED'"
)


async def get_tier(tier_id: str, cache: CacheService) -> tuple[Optional[str], Optional[int]]:
    """``(status, rate_limit)`` for ``tier_id``; ``(None, None)`` when unknown."""
    cached = await cache.get_tier_cache(tier_id)
    if cached is not None:
        return cached

    factory = get_platform_core_session_factory()
    if factory is None:
        return None, None
    try:
        async with factory() as session:
            row = (await session.execute(_TIER_SQL, {"tier_id": tier_id})).first()
    except Exception as exc:
        logger.warning("Tier %s DB lookup failed; treating as active, no rate limit: %s", tier_id, exc)
        return None, None
    if row is None:
        return None, None

    status, rate_limit = row
    await cache.set_tier_cache(tier_id, status, rate_limit)
    return status, rate_limit
