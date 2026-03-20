"""
Role, Permission, UserRole, RolePermission queries.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role import Permission, Role, RolePermission, UserRole


class RoleRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── Roles ──

    async def get_role_by_name(self, name: str) -> Optional[Role]:
        result = await self._db.execute(select(Role).where(Role.name == name))
        return result.scalar_one_or_none()

    async def get_role_by_id(self, role_id: int) -> Optional[Role]:
        result = await self._db.execute(select(Role).where(Role.id == role_id))
        return result.scalar_one_or_none()

    async def list_roles(self) -> list[Role]:
        result = await self._db.execute(select(Role).order_by(Role.name))
        return list(result.scalars().all())

    # ── User roles ──

    async def get_user_roles(self, user_id: int) -> list[str]:
        """Return role names for a user (most recent first)."""
        result = await self._db.execute(
            select(Role.name)
            .join(UserRole, Role.id == UserRole.role_id)
            .where(UserRole.user_id == user_id)
            .order_by(UserRole.assigned_at.desc())
        )
        return list(result.scalars().all())

    async def get_user_role_records(self, user_id: int) -> list[UserRole]:
        result = await self._db.execute(
            select(UserRole)
            .where(UserRole.user_id == user_id)
            .order_by(UserRole.assigned_at.desc())
        )
        return list(result.scalars().all())

    async def assign_role(self, user_id: int, role_id: int) -> UserRole:
        user_role = UserRole(user_id=user_id, role_id=role_id)
        self._db.add(user_role)
        await self._db.flush()
        return user_role

    async def remove_role(self, user_id: int, role_id: int) -> bool:
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

    async def get_user_permission_ids(self, user_id: int) -> list[int]:
        """Return permission IDs for a user (via roles)."""
        result = await self._db.execute(
            select(Permission.id)
            .join(RolePermission, Permission.id == RolePermission.permission_id)
            .join(Role, RolePermission.role_id == Role.id)
            .join(UserRole, Role.id == UserRole.role_id)
            .where(UserRole.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_user_permission_names(self, user_id: int) -> list[str]:
        """Return permission names for a user (via roles)."""
        result = await self._db.execute(
            select(Permission.name)
            .join(RolePermission, Permission.id == RolePermission.permission_id)
            .join(Role, RolePermission.role_id == Role.id)
            .join(UserRole, Role.id == UserRole.role_id)
            .where(UserRole.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_role_permission_ids(self, role_id: int) -> list[int]:
        result = await self._db.execute(
            select(RolePermission.permission_id).where(RolePermission.role_id == role_id)
        )
        return list(result.scalars().all())

    async def commit(self) -> None:
        await self._db.commit()
