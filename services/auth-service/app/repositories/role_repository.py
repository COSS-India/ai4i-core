"""
Role, Permission, UserRole, RolePermission queries.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import delete, select , func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role import Permission, Role, RolePermission, UserRole
from app.models.role_name import RoleName, role_name_to_str
from app.repositories.base import BaseRepository
from app.models.user import User


class RoleRepository(BaseRepository):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    # ── Roles ──

    async def get_role_by_name(self, name: str | RoleName) -> Optional[Role]:
        normalized = role_name_to_str(name)
        result = await self._db.execute(select(Role).where(Role.name == normalized))
        return result.scalar_one_or_none()

    async def list_roles(self) -> list[Role]:
        result = await self._db.execute(select(Role).order_by(Role.name))
        return list(result.scalars().all())

    # ── User roles ──

    async def get_user_roles(self, user_id: UUID) -> list[str]:
        result = await self._db.execute(
            select(Role.name)
            .join(UserRole, Role.id == UserRole.role_id)
            .where(UserRole.user_id == user_id)
            .order_by(UserRole.created_at.desc())
        )
        return [role_name_to_str(n) for n in result.scalars().all()]

    async def get_roles_for_users(self, user_ids: list[UUID]) -> dict[UUID, list[str]]:
        """Batch-fetch role names for many users (one query)."""
        if not user_ids:
            return {}
        result = await self._db.execute(
            select(UserRole.user_id, Role.name)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.user_id.in_(user_ids))
            .order_by(UserRole.user_id, UserRole.created_at.desc())
        )
        roles_by_user: dict[UUID, list[str]] = {uid: [] for uid in user_ids}
        for user_id, role_name in result.all():
            roles_by_user[user_id].append(role_name_to_str(role_name))
        return roles_by_user

    async def count_tenant_admins_in_tenant(self, tenant_id: int) -> int:
        """Count active, non-deleted TENANT ADMIN users in a given tenant."""
        result = await self._db.execute(
            select(sa_func.count())
            .select_from(UserRole)
            .join(Role, Role.id == UserRole.role_id)
            .join(User, User.id == UserRole.user_id)
            .where(
                Role.name == RoleName.TENANT_ADMIN.value,
                User.tenant_id == tenant_id,
                User.is_delete.isnot(True),
                User.is_active.is_(True),
            )
        )
        return result.scalar_one()

    async def get_user_role_records(self, user_id: UUID) -> list[UserRole]:
        result = await self._db.execute(
            select(UserRole)
            .where(UserRole.user_id == user_id)
            .order_by(UserRole.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_user_role_record(self, user_id: UUID, role_id: int) -> Optional[UserRole]:
        result = await self._db.execute(
            select(UserRole).where(
                UserRole.user_id == user_id, UserRole.role_id == role_id
            )
        )
        return result.scalar_one_or_none()

    async def assign_role(self, user_id: UUID, role_id: int) -> UserRole:
        user_role = UserRole(user_id=user_id, role_id=role_id)
        self._db.add(user_role)
        await self._db.flush()
        return user_role

    async def remove_role(self, user_id: UUID, role_id: int) -> bool:
        result = await self._db.execute(
            select(UserRole).where(
                UserRole.user_id == user_id, UserRole.role_id == role_id
            )
        )
        user_role = result.scalar_one_or_none()
        if user_role:
            await self._db.delete(user_role)
            await self._db.flush()
            return True
        return False

    # ── Permissions ──

    async def list_permissions(self) -> list[Permission]:
        result = await self._db.execute(select(Permission).order_by(Permission.name))
        return list(result.scalars().all())

    async def list_inference_permissions(
        self,
        excluded_resources: tuple[str, ...] = (),
    ) -> list[Permission]:
        stmt = (
            select(Permission)
            .where(Permission.action == "inference")
            .order_by(Permission.resource)
        )
        if excluded_resources:
            stmt = stmt.where(Permission.resource.notin_(excluded_resources))
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_role_permission_ids(self, role_id: int) -> list[int]:
        result = await self._db.execute(
            select(RolePermission.permission_id).where(RolePermission.role_id == role_id)
        )
        return list(result.scalars().all())

    async def get_permission_names_by_ids(self, permission_ids: list[int]) -> dict[int, str]:
        if not permission_ids:
            return {}
        result = await self._db.execute(
            select(Permission.id, Permission.name).where(
                Permission.id.in_(permission_ids)
            )
        )
        return {pid: name for pid, name in result.all()}

    async def get_permission_ids_by_names(self, permission_names: list[str]) -> dict[str, int]:
        if not permission_names:
            return {}
        result = await self._db.execute(
            select(Permission.name, Permission.id).where(
                Permission.name.in_(permission_names)
            )
        )
        return {name: pid for name, pid in result.all()}

    async def delete_role_permissions_for_permission_ids(
        self, role_id: int, permission_ids: list[int]
    ) -> None:
        if not permission_ids:
            return
        await self._db.execute(
            delete(RolePermission).where(
                RolePermission.role_id == role_id,
                RolePermission.permission_id.in_(permission_ids),
            )
        )
        await self._db.flush()

    async def insert_role_permissions(self, role_id: int, permission_ids: list[int]) -> None:
        self._db.add_all([RolePermission(role_id=role_id, permission_id=pid) for pid in permission_ids])
        await self._db.flush()
