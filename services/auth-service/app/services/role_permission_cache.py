"""
In-memory role -> permission_ids cache.

Roles and role-permission assignments change rarely; resolving a user's
permission set on every login by joining users -> user_roles -> role_permissions
on the hot path is wasteful. This module loads role_id -> list[permission_id]
into process memory at startup and refreshes it every refresh_interval_seconds.

Eventual consistency: admin role-permission mutations propagate within the
refresh window (default 60s). Multiple workers each maintain their own copy.
"""

import logging

from sqlalchemy import select

from app.core.database import get_db
from app.models.role import RolePermission
from app.services.refreshing_cache import DEFAULT_REFRESH_INTERVAL_SECONDS, RefreshingCache

logger = logging.getLogger(__name__)


class RolePermissionCache(RefreshingCache):
    def __init__(self, refresh_interval_seconds: int = DEFAULT_REFRESH_INTERVAL_SECONDS) -> None:
        super().__init__(refresh_interval_seconds)
        self._role_perms: dict[int, list[int]] = {}

    def get_user_permission_ids(self, role_ids: list[int]) -> list[int]:
        """Union of permission IDs across the given roles."""
        out: set[int] = set()
        for rid in role_ids:
            out.update(self._role_perms.get(rid, []))
        return sorted(out)

    def _loaded_count(self) -> int:
        return len(self._role_perms)

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


# Module-level singleton — initialized in lifespan.
role_permission_cache = RolePermissionCache()
