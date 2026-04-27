"""
Role, Permission, UserRole, RolePermission queries.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role import Permission, Role, RolePermission, UserRole
from app.repositories.base import BaseRepository


class RoleRepository(BaseRepository):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    # ── Roles ──

    async def get_role_by_name(self, name: str) -> Optional[Role]:
        result = await self._db.execute(select(Role).where(Role.name == name))
        return result.scalar_one_or_none()

    async def get_role_by_id(self, role_id: int) -> Optional[Role]:
        result = await self._db.execute(select(Role).where(Role.role_id == role_id))
        return result.scalar_one_or_none()

    async def list_roles(self) -> list[Role]:
        result = await self._db.execute(select(Role).order_by(Role.name))
        return list(result.scalars().all())

    # ── User roles ──

    async def get_user_roles(self, user_id: UUID) -> list[str]:
        result = await self._db.execute(
            select(Role.name)
            .join(UserRole, Role.role_id == UserRole.role_id)
            .where(UserRole.user_id == user_id)
            .order_by(UserRole.created_at.desc())
        )
        return list(result.scalars().all())

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
            .where(
                Permission.action == "inference",
                Permission.name.like("%.inference"),
            )
            .order_by(Permission.name)
        )
        if excluded_resources:
            stmt = stmt.where(Permission.resource.notin_(excluded_resources))
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_user_permission_ids(self, user_id: UUID) -> list[int]:
        result = await self._db.execute(
            select(Permission.permission_id)
            .join(RolePermission, Permission.permission_id == RolePermission.permission_id)
            .join(Role, RolePermission.role_id == Role.role_id)
            .join(UserRole, Role.role_id == UserRole.role_id)
            .where(UserRole.user_id == user_id)
            .distinct()
        )
        return list(result.scalars().all())

    async def get_user_permission_names(self, user_id: UUID) -> list[str]:
        result = await self._db.execute(
            select(Permission.name)
            .join(RolePermission, Permission.permission_id == RolePermission.permission_id)
            .join(Role, RolePermission.role_id == Role.role_id)
            .join(UserRole, Role.role_id == UserRole.role_id)
            .where(UserRole.user_id == user_id)
            .distinct()
        )
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
            select(Permission.permission_id, Permission.name).where(
                Permission.permission_id.in_(permission_ids)
            )
        )
        return {pid: name for pid, name in result.all()}

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
        for pid in permission_ids:
            self._db.add(RolePermission(role_id=role_id, permission_id=pid))
        await self._db.flush()
