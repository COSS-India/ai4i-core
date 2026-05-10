"""
In-memory role -> permission_ids cache.

Roles and role-permission assignments change rarely; resolving a user's
permission set on every login by joining users -> user_roles -> role_permissions
on the hot path is wasteful. This module loads role_id -> list[permission_id]
into process memory at startup and refreshes it every refresh_interval_seconds.

Eventual consistency: admin role-permission mutations propagate within the
refresh window (default 60s). Multiple workers each maintain their own copy.
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import get_db
from app.models.role import RolePermission

logger = logging.getLogger(__name__)

DEFAULT_REFRESH_INTERVAL_SECONDS = 60


class RolePermissionCache:
    def __init__(self, refresh_interval_seconds: int = DEFAULT_REFRESH_INTERVAL_SECONDS) -> None:
        self._role_perms: dict[int, list[int]] = {}
        self._refresh_interval = refresh_interval_seconds
        self._task: Optional[asyncio.Task] = None

    def get_user_permission_ids(self, role_ids: list[int]) -> list[int]:
        """Union of permission IDs across the given roles."""
        out: set[int] = set()
        for rid in role_ids:
            out.update(self._role_perms.get(rid, []))
        return sorted(out)

    async def reload(self) -> None:
        """Read all role_permissions rows and rebuild the in-memory map."""
        new_map: dict[int, list[int]] = {}
        async for db in get_db():
            result = await db.execute(
                select(RolePermission.role_id, RolePermission.permission_id)
            )
            for role_id, permission_id in result.all():
                new_map.setdefault(role_id, []).append(permission_id)
            break
        for rid in new_map:
            new_map[rid].sort()
        self._role_perms = new_map
        logger.debug(
            "RolePermissionCache: reloaded %d roles, %d total bindings.",
            len(self._role_perms),
            sum(len(v) for v in self._role_perms.values()),
        )

    async def start(self) -> None:
        """Initial load + start the background refresh task."""
        await self.reload()
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._refresh_loop())
        logger.info(
            "RolePermissionCache started: %d roles loaded; refresh interval=%ds",
            len(self._role_perms),
            self._refresh_interval,
        )

    async def stop(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    async def _refresh_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(self._refresh_interval)
                await self.reload()
            except asyncio.CancelledError:
                raise
            except (OSError, SQLAlchemyError):
                logger.exception("RolePermissionCache refresh failed (database/network issue); will retry next cycle.")
            except Exception:
                logger.exception("RolePermissionCache refresh failed with unexpected error; will retry next cycle.")


# Module-level singleton — initialized in lifespan.
role_permission_cache = RolePermissionCache()
