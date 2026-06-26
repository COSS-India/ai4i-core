"""
PPU monthly quota rollover — cron job.

Runs once at midnight UTC on the 1st of every month.
Clears all quota-{inference_name} flags from Redis (ppu:flags:{api_key})
for every tenant that has an active tier assignment.

What it does NOT touch:
  - budget-exhausted flag  (wallet does not reset monthly)
  - ppu_quota_usage DB rows (Kafka consumer creates new-month rows automatically)
  - auth:apikey:{key} strings (existing auth structure is untouched)

Redis keys used (both written by other parts of the PPU system):
  ppu:keys:{tenant_id}  — SET of api_key strings for the tenant (managed by auth-service)
  ppu:flags:{api_key}   — Hash of PPU enforcement flags (managed by Kafka billing consumer)
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import text

from app.core.config import settings
from app.core.database import get_primary_session_factory
from app.core.redis import get_redis_client

logger = logging.getLogger(__name__)

_SQL_ACTIVE_TENANT_IDS = text(
    """
    SELECT DISTINCT tenant_id
    FROM ppu_tenant_tier_assignments
    WHERE NOW() BETWEEN effective_from AND effective_to
    """
)


def _seconds_until_next_month_start() -> float:
    """Seconds from now until 00:00:00 UTC on the 1st of next month."""
    now = datetime.now(timezone.utc)
    year = now.year + 1 if now.month == 12 else now.year
    month = 1 if now.month == 12 else now.month + 1
    next_start = datetime(year, month, 1, tzinfo=timezone.utc)
    return max(0.0, (next_start - now).total_seconds())

class QuotaRolloverService:
    """Clears monthly quota Redis flags at the start of each billing month."""

    async def run_loop(self) -> None:
        """Background loop — sleeps until the 1st of each month, then rolls over."""
        while True:
            delay = _seconds_until_next_month_start()
            logger.info(
                "PPU quota rollover: next run in %.0f seconds (%.1f hours)",
                delay,
                delay / 3600,
            )
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                logger.info("PPU quota rollover loop cancelled during sleep.")
                raise

            try:
                await self._rollover()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("PPU quota rollover failed: %s", exc, exc_info=True)

    async def _rollover(self) -> None:
        now = datetime.now(timezone.utc)
        logger.info("PPU quota rollover starting for %s-%02d", now.year, now.month)

        inference_names = [
            name.strip()
            for name in settings.ppu_inference_types.split(",")
            if name.strip()
        ]
        if not inference_names:
            logger.warning("PPU quota rollover: ppu_inference_types is empty, nothing to clear.")
            return

        quota_fields = [f"quota-{name}" for name in inference_names]

        tenant_ids = await self._fetch_active_tenant_ids()
        if not tenant_ids:
            logger.info("PPU quota rollover: no active tenant assignments found.")
            return

        redis = get_redis_client()
        keys_cleared = 0
        tenants_processed = 0

        for tenant_id in tenant_ids:
            api_keys: set[str] = await redis.smembers(f"ppu:keys:{tenant_id}")
            if not api_keys:
                continue
            for api_key in api_keys:
                deleted = await redis.hdel(f"ppu:flags:{api_key}", *quota_fields)
                keys_cleared += deleted
            tenants_processed += 1

        logger.info(
            "PPU quota rollover complete: %d tenants processed, %d quota flag(s) cleared.",
            tenants_processed,
            keys_cleared,
        )

    async def _fetch_active_tenant_ids(self) -> list[str]:
        factory = get_primary_session_factory()
        try:
            async with factory() as session:
                result = await session.execute(_SQL_ACTIVE_TENANT_IDS)
                return [str(row[0]) for row in result.fetchall()]
        except Exception as exc:
            logger.error("PPU quota rollover: failed to fetch active tenants: %s", exc, exc_info=True)
            return []
