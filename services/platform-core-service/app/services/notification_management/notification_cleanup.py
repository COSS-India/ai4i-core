"""Daily notification cleanup: failure-log rows past their retention, and
quota ledger rows of billing months older than 3 months. Both deletes are
safe to run twice, so every pod runs this and no lock is needed.
"""

import asyncio
import logging

from ai4i_core.kafka import get_notification_runtime, notifications_configured, purge_failures, purge_old_quota_rows

from app.core.config import settings

logger = logging.getLogger(__name__)


async def run_cleanup() -> None:
    rt = get_notification_runtime()
    async with rt.core_session_factory() as session:
        failures = await purge_failures(session, rt.config.notif_failure_retention_days)
        quota_rows = await purge_old_quota_rows(session)
        await session.commit()
    logger.info("Notification cleanup removed %d failure row(s) and %d quota ledger row(s)", failures, quota_rows)


async def run_forever() -> None:
    """Background loop started in the app lifespan."""
    while True:
        try:
            if notifications_configured():
                await run_cleanup()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Notification cleanup failed")
        await asyncio.sleep(settings.notification_cleanup_interval_s)
