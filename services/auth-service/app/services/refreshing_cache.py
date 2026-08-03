"""
Base for an in-memory cache that loads once at startup and refreshes on a
fixed interval in the background — shared by RolePermissionCache and
TenantNameCache, which otherwise differ only in what they load and how they
count what's loaded.
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)

DEFAULT_REFRESH_INTERVAL_SECONDS = 60


class RefreshingCache:
    """Subclasses implement ``reload()`` (the actual data load) and
    ``_loaded_count()`` (an item count for the startup/refresh log lines)."""

    def __init__(self, refresh_interval_seconds: int = DEFAULT_REFRESH_INTERVAL_SECONDS) -> None:
        self._refresh_interval = refresh_interval_seconds
        self._task: Optional[asyncio.Task] = None

    async def reload(self) -> None:
        raise NotImplementedError

    def _loaded_count(self) -> int:
        raise NotImplementedError

    async def start(self) -> None:
        """Initial load + start the background refresh task."""
        await self.reload()
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._refresh_loop())
        logger.info(
            "%s started: %d items loaded; refresh interval=%ds",
            type(self).__name__, self._loaded_count(), self._refresh_interval,
        )

    async def stop(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        self._task = None

    async def _refresh_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._refresh_interval)
                await self.reload()
            except asyncio.CancelledError:
                raise
            except (OSError, SQLAlchemyError):
                logger.exception(
                    "%s refresh failed (database/network issue); will retry next cycle.",
                    type(self).__name__,
                )
            except Exception:
                logger.exception(
                    "%s refresh failed with unexpected error; will retry next cycle.",
                    type(self).__name__,
                )
