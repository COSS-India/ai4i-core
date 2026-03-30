"""
Role assignment and permission checking.
Uses Redis cache for permission lookups (cache-aside pattern).
"""

import logging

from app.core.exceptions import EntityNotFoundError
from app.models.role import Permission, Role
from app.repositories.role_repository import RoleRepository
from app.services.cache_service import CacheService

logger = logging.getLogger(__name__)


class RoleService:
    def __init__(self, role_repo: RoleRepository, cache_service: CacheService) -> None:
        self._roles = role_repo
        self._cache = cache_service

    # ── Cached permission lookups (hot path) ──

    async def get_user_permission_ids_cached(self, user_id: int) -> list[int]:
        """
        Get permission IDs for a user. Redis first, DB fallback, cache on miss.
        This is the hot-path method used during login and token refresh.
        """
        # Get user's role IDs first
        role_records = await self._roles.get_user_role_records(user_id)
        if not role_records:
            return []

        all_perm_ids: set[int] = set()
        uncached_role_ids: list[int] = []

        # Check Redis for each role's permissions
        for ur in role_records:
            cached = await self._cache.get_role_permissions(ur.role_id)
            if cached is not None:
                all_perm_ids.update(cached)
            else:
                uncached_role_ids.append(ur.role_id)

        # Fetch uncached from DB and cache them
        if uncached_role_ids:
            for role_id in uncached_role_ids:
                perm_ids = await self._roles.get_role_permission_ids(role_id)
                all_perm_ids.update(perm_ids)
                # Cache for next time
                await self._cache.cache_role_permissions(role_id, perm_ids)

        return sorted(all_perm_ids)

    # ── Role management ──

    async def assign_role(self, user_id: int, role_name: str) -> None:
        """Assign a role to a user. Ensures single-role per user."""
        role = await self._roles.get_role_by_name(role_name)
        if not role:
            raise EntityNotFoundError(f"Role '{role_name}'")

        existing = await self._roles.get_user_role_records(user_id)
        for ur in existing:
            await self._roles.remove_role(user_id, ur.role_id)
            # Invalidate cache for removed role
            await self._cache.invalidate_role_cache(ur.role_id)

        await self._roles.assign_role(user_id, role.id)
        await self._roles.commit()
        logger.info("Role '%s' assigned to user %d", role_name, user_id)

    async def remove_role(self, user_id: int, role_name: str) -> None:
        role = await self._roles.get_role_by_name(role_name)
        if not role:
            raise EntityNotFoundError(f"Role '{role_name}'")
        removed = await self._roles.remove_role(user_id, role.id)
        if not removed:
            raise EntityNotFoundError("UserRole")
        await self._cache.invalidate_role_cache(role.id)
        await self._roles.commit()

    async def get_user_roles(self, user_id: int) -> list[str]:
        return await self._roles.get_user_roles(user_id)

    async def get_user_permission_ids(self, user_id: int) -> list[int]:
        """Direct DB lookup (use get_user_permission_ids_cached for hot paths)."""
        return await self._roles.get_user_permission_ids(user_id)

    async def check_permission(self, user_id: int, resource: str, action: str) -> bool:
        permissions = await self._roles.get_user_permission_names(user_id)
        return f"{resource}.{action}" in permissions

    async def list_roles(self) -> list[Role]:
        return await self._roles.list_roles()

    async def list_permissions(self) -> list[Permission]:
        return await self._roles.list_permissions()

    async def list_inference_permissions(self) -> list[Permission]:
        # Exclude non-inference API domains requested by product.
        excluded_resources = (
            "model-management",
            "model_management",
            "multi_tenant",
            "multi-tenant",
            "pii_guard",
        )
        return await self._roles.list_inference_permissions(excluded_resources=excluded_resources)
