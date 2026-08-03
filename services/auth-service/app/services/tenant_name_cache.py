"""
In-memory tenant_id -> organisation name cache.

/auth/validate is the gateway's forward-auth hot path and must stay
DB-free for the JWT/anonymous branches (see validation.py). Resolving the
caller's tenant NAME there — needed so downstream Prometheus metrics carry
the organisation name instead of the numeric tenant id as the ``tenant``
label — would otherwise require a DB round trip per request. Instead this
loads the full id -> organisation map into process memory at startup and
refreshes it periodically, mirroring role_permission_cache.py.

tenant_service.py pushes an immediate update on create/rename so renames
don't wait for the next refresh cycle; the periodic reload is the fallback
for anything the push path missed (e.g. a rolling deploy mid-transaction).
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import get_db
from app.models.tenant import Tenant

logger = logging.getLogger(__name__)

DEFAULT_REFRESH_INTERVAL_SECONDS = 60


class TenantNameCache:
    def __init__(self, refresh_interval_seconds: int = DEFAULT_REFRESH_INTERVAL_SECONDS) -> None:
        self._names: dict[int, str] = {}
        self._refresh_interval = refresh_interval_seconds
        self._task: Optional[asyncio.Task] = None

    def get_name(self, tenant_id: int) -> Optional[str]:
        return self._names.get(tenant_id)

    def set_name(self, tenant_id: int, organisation: str) -> None:
        """Push an immediate update — called by tenant_service on create/rename."""
        self._names[tenant_id] = organisation

    async def reload(self) -> None:
        """Read all tenants and rebuild the in-memory id -> organisation map."""
        new_map: dict[int, str] = {}
        async for db in get_db():
            result = await db.execute(select(Tenant.id, Tenant.organisation))
            for tenant_id, organisation in result.all():
                new_map[tenant_id] = organisation
            break
        self._names = new_map
        logger.debug("TenantNameCache: reloaded %d tenants.", len(self._names))

    async def start(self) -> None:
        """Initial load + start the background refresh task."""
        await self.reload()
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._refresh_loop())
        logger.info(
            "TenantNameCache started: %d tenants loaded; refresh interval=%ds",
            len(self._names),
            self._refresh_interval,
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
                logger.exception("TenantNameCache refresh failed (database/network issue); will retry next cycle.")
            except Exception:
                logger.exception("TenantNameCache refresh failed with unexpected error; will retry next cycle.")


# Module-level singleton — initialized in lifespan.
tenant_name_cache = TenantNameCache()
