"""
Role assignment and permission checking.
Permission IDs for roles are resolved from the database (no Redis role cache).
"""

import logging
from uuid import UUID

from app.core.exceptions import EntityNotFoundError, ValidationError
from app.models.role import Permission, Role
from app.repositories.role_repository import RoleRepository
from app.services.cache_service import CacheService

logger = logging.getLogger(__name__)

_GUEST_ROLE_NAME = "GUEST"


def _normalize_service_slug(value: str) -> str:
    return value.strip().lower().replace("_", "-")


class RoleService:
    def __init__(self, role_repo: RoleRepository, cache_service: CacheService) -> None:
        self._roles = role_repo
        self._cache = cache_service

    @staticmethod
    def _expanded_excluded_resources_for_platform_inference() -> tuple[str, ...]:
        base = (
            "model-management",
            "pii_guard",
        )
        expanded: set[str] = set()
        for res in base:
            expanded.add(res)
            expanded.add(res.replace("-", "_"))
            expanded.add(res.replace("_", "-"))
        return tuple(sorted(expanded))

    # ── Cached permission lookups (hot path) ──

    async def get_user_permission_ids_cached(self, user_id: UUID) -> list[int]:
        """
        Get permission IDs for a user (union of all assigned roles) from the database.
        """
        role_records = await self._roles.get_user_role_records(user_id)
        if not role_records:
            return []

        all_perm_ids: set[int] = set()
        for ur in role_records:
            perm_ids = await self._roles.get_role_permission_ids(ur.role_id)
            all_perm_ids.update(perm_ids)

        return sorted(all_perm_ids)

    # ── Role management ──

    async def assign_role(self, user_id: UUID, role_name: str) -> None:
        """
        Assign a role to a user. Permissions are additive — existing roles are
        kept. Silently skips if the user already has this role.
        """
        role = await self._roles.get_role_by_name(role_name)
        if not role:
            raise EntityNotFoundError(f"Role '{role_name}'")

        existing = await self._roles.get_user_role_record(user_id, role.role_id)
        if existing:
            return

        await self._roles.assign_role(user_id, role.role_id)
        await self._roles.commit()
        logger.info("Role '%s' assigned to user %s", role_name, user_id)

    async def remove_role(self, user_id: UUID, role_name: str) -> None:
        role = await self._roles.get_role_by_name(role_name)
        if not role:
            raise EntityNotFoundError(f"Role '{role_name}'")
        removed = await self._roles.remove_role(user_id, role.role_id)
        if not removed:
            raise EntityNotFoundError("UserRole")
        await self._roles.commit()

    async def get_user_roles(self, user_id: UUID) -> list[str]:
        return await self._roles.get_user_roles(user_id)

    async def get_user_permission_ids(self, user_id: UUID) -> list[int]:
        return await self._roles.get_user_permission_ids(user_id)

    async def check_permission(self, user_id: UUID, resource: str, action: str) -> bool:
        permissions = await self._roles.get_user_permission_names(user_id)
        return f"{resource}.{action}" in permissions

    async def list_roles(self) -> list[Role]:
        return await self._roles.list_roles()

    async def list_permissions(self) -> list[Permission]:
        return await self._roles.list_permissions()

    async def list_inference_permissions(self) -> list[Permission]:
        return await self._roles.list_inference_permissions(
            excluded_resources=self._expanded_excluded_resources_for_platform_inference(),
        )

    async def _managed_guest_inference_permissions(self) -> list[Permission]:
        return await self.list_inference_permissions()

    async def assign_guest_inference_services(self, services: list[str]) -> list[str]:
        managed = await self._managed_guest_inference_permissions()
        by_norm_resource: dict[str, Permission] = {}
        for perm in managed:
            key = _normalize_service_slug(perm.resource)
            by_norm_resource[key] = perm

        managed_ids = [p.permission_id for p in managed]
        ordered_unique: list[str] = []
        seen: set[str] = set()
        for raw in services:
            key = _normalize_service_slug(raw)
            if not key:
                raise ValidationError(
                    message="Invalid service slug.",
                    code="INVALID_GUEST_SERVICE",
                    errors=["Empty service name is not allowed."],
                )
            if key in seen:
                continue
            seen.add(key)
            ordered_unique.append(raw)

        resolved: list[Permission] = []
        errors: list[str] = []
        for raw in ordered_unique:
            key = _normalize_service_slug(raw)
            perm = by_norm_resource.get(key)
            if perm is None:
                errors.append(f"Unknown or non-assignable inference service: {raw!r}")
            else:
                resolved.append(perm)
        if errors:
            raise ValidationError(
                message="One or more services are not assignable to the guest role.",
                code="INVALID_GUEST_SERVICE",
                errors=errors,
            )

        guest = await self._roles.get_role_by_name(_GUEST_ROLE_NAME)
        if not guest:
            raise EntityNotFoundError(f"Role '{_GUEST_ROLE_NAME}'")

        await self._roles.delete_role_permissions_for_permission_ids(guest.role_id, managed_ids)
        await self._roles.insert_role_permissions(guest.role_id, [p.permission_id for p in resolved])
        await self._roles.commit()
        logger.info("GUEST inference services set to: %s", [p.resource for p in resolved])
        return [p.resource for p in resolved]

    async def list_guest_inference_services(self) -> list[str]:
        guest = await self._roles.get_role_by_name(_GUEST_ROLE_NAME)
        if not guest:
            raise EntityNotFoundError(f"Role '{_GUEST_ROLE_NAME}'")

        managed = await self._managed_guest_inference_permissions()
        managed_id_set = {p.permission_id for p in managed}
        id_to_resource = {p.permission_id: p.resource for p in managed}

        role_perm_ids = await self._roles.get_role_permission_ids(guest.role_id)
        active = sorted(
            id_to_resource[pid]
            for pid in role_perm_ids
            if pid in managed_id_set and pid in id_to_resource
        )
        return active
