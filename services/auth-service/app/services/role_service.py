"""
Role assignment and permission checking.
Per-user permission resolution reads role_ids from the DB and unions
their permission_ids from the in-process role_permission_cache.
"""

import logging
from uuid import UUID

from app.core.exceptions import AppError, EntityNotFoundError, ValidationError
from app.models.role import Permission, Role
from app.core.config import RoleName
from app.utils.auth_helper import role_name_to_str
from app.repositories.role_repository import RoleRepository
from app.services.role_permission_cache import role_permission_cache

logger = logging.getLogger(__name__)


def _normalize_service_slug(value: str) -> str:
    return value.strip().lower().replace("_", "-")


class RoleService:
    def __init__(self, role_repo: RoleRepository) -> None:
        self._roles = role_repo

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

    # ── Role management ──

    async def ensure_role_exists(self, role_name: str | RoleName) -> None:
        """Raise EntityNotFoundError when the role name is not in the database."""
        key = role_name_to_str(role_name)
        if not await self._roles.get_role_by_name(key):
            raise EntityNotFoundError(f"Role '{key}'")

    async def assign_role(
        self, user_id: UUID, role_name: str | RoleName, *, commit: bool = True
    ) -> None:
        """
        Assign a role to a user. Permissions are additive — existing roles are
        kept. Silently skips if the user already has this role.

        When ``commit=False``, flush only — caller commits the shared session
        (e.g. tenant user PATCH batches role + profile in one transaction).
        """
        key = role_name_to_str(role_name)
        role = await self._roles.get_role_by_name(key)
        if not role:
            raise EntityNotFoundError(f"Role '{key}'")

        existing = await self._roles.get_user_role_record(user_id, role.id)
        if existing:
            return

        await self._roles.assign_role(user_id, role.id)
        if commit:
            await self._roles.commit()
            logger.info("Role '%s' assigned to user %s", key, user_id)

    async def remove_role(
        self, user_id: UUID, role_name: str | RoleName, *, commit: bool = True
    ) -> None:
        """When ``commit=False``, defer commit to the caller's session commit."""
        key = role_name_to_str(role_name)
        role = await self._roles.get_role_by_name(key)
        if not role:
            raise EntityNotFoundError(f"Role '{key}'")
        removed = await self._roles.remove_role(user_id, role.id)
        if not removed:
            raise AppError(message="The user does not have this role assigned.", code="NOT_FOUND", status_code=404)
        if commit:
            await self._roles.commit()

    async def get_user_roles(self, user_id: UUID) -> list[str]:
        return await self._roles.get_user_roles(user_id)

    async def get_roles_for_users(self, user_ids: list[UUID]) -> dict[UUID, list[str]]:
        return await self._roles.get_roles_for_users(user_ids)

    async def count_tenant_admins_in_tenant(self, tenant_id: int) -> int:
        return await self._roles.count_tenant_admins_in_tenant(tenant_id)

    async def get_user_permission_ids(self, user_id: UUID) -> list[int]:
        """
        Union of permission IDs across all roles assigned to a user.
        Reads role_ids from DB and resolves permissions via the in-memory
        role_permission_cache (no per-role DB query on the hot path).
        """
        role_records = await self._roles.get_user_role_records(user_id)
        if not role_records:
            return []
        role_ids = [ur.role_id for ur in role_records]
        return role_permission_cache.get_user_permission_ids(role_ids)

    async def list_roles(self) -> list[Role]:
        return await self._roles.list_roles()

    async def list_permissions(self) -> list[Permission]:
        return await self._roles.list_permissions()

    async def list_inference_permissions(self) -> list[Permission]:
        return await self._roles.list_inference_permissions(
            excluded_resources=self._expanded_excluded_resources_for_platform_inference(),
        )

    async def assign_guest_inference_services(self, services: list[str]) -> list[str]:
        managed = await self.list_inference_permissions()
        by_norm_resource: dict[str, Permission] = {}
        for perm in managed:
            key = _normalize_service_slug(perm.resource)
            by_norm_resource[key] = perm

        managed_ids = [p.id for p in managed]
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

        guest = await self._roles.get_role_by_name(RoleName.GUEST)
        if not guest:
            raise EntityNotFoundError(f"Role '{RoleName.GUEST.value}'")

        await self._roles.delete_role_permissions_for_permission_ids(guest.id, managed_ids)
        await self._roles.insert_role_permissions(guest.id, [p.id for p in resolved])
        await self._roles.commit()
        logger.info("GUEST inference services set to: %s", [p.resource for p in resolved])
        return [p.resource for p in resolved]

    async def list_guest_inference_services(self) -> list[str]:
        guest = await self._roles.get_role_by_name(RoleName.GUEST)
        if not guest:
            raise EntityNotFoundError(f"Role '{RoleName.GUEST.value}'")

        managed = await self.list_inference_permissions()
        managed_id_set = {p.id for p in managed}
        id_to_resource = {p.id: p.resource for p in managed}

        role_perm_ids = await self._roles.get_role_permission_ids(guest.id)
        active = sorted(
            id_to_resource[pid]
            for pid in role_perm_ids
            if pid in managed_id_set and pid in id_to_resource
        )
        return active
