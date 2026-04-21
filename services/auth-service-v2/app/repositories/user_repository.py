"""
User table queries.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role import Role, RolePermission, UserRole
from app.models.user import User


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, user_id: int) -> Optional[User]:
        result = await self._db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self._db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_email_with_roles(self, email: str) -> Optional[tuple[User, list[str], list[int]]]:
        """Get user + role names + permission IDs in a single query.
        Returns (user, roles, permission_ids) or None if not found."""
        stmt = (
            select(
                User,
                func.array_agg(distinct(Role.name)).filter(Role.name.is_not(None)),
                func.array_agg(distinct(RolePermission.permission_id)).filter(RolePermission.permission_id.is_not(None)),
            )
            .outerjoin(UserRole, User.id == UserRole.user_id)
            .outerjoin(Role, UserRole.role_id == Role.id)
            .outerjoin(RolePermission, Role.id == RolePermission.role_id)
            .where(User.email == email)
            .group_by(User.id)
        )
        result = await self._db.execute(stmt)
        row = result.first()
        if not row:
            return None
        user, roles_raw, perm_ids_raw = row
        roles = list(roles_raw) if roles_raw else []
        perm_ids = sorted(int(p) for p in perm_ids_raw if p is not None) if perm_ids_raw else []
        return user, roles, perm_ids

    async def get_by_username(self, username: str) -> Optional[User]:
        result = await self._db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def create(self, user: User) -> User:
        self._db.add(user)
        await self._db.flush()
        return user

    async def update(self, user: User, data: dict) -> User:
        for key, value in data.items():
            if hasattr(user, key) and value is not None:
                setattr(user, key, value)
        await self._db.flush()
        return user

    async def update_last_login(self, user: User) -> None:
        user.last_login = datetime.now(timezone.utc)
        await self._db.flush()

    async def update_password(self, user: User, password_hash: str, salt: str, rounds: int) -> None:
        user.password_hash = password_hash
        user.password_salt = salt
        user.hash_rounds = rounds
        await self._db.flush()

    async def list_all(self, offset: int = 0, limit: int = 100) -> list[User]:
        result = await self._db.execute(
            select(User)
            .order_by(func.lower(User.username).asc(), User.id.asc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_tenant(self, tenant_id: str, offset: int = 0, limit: int = 100) -> list[User]:
        result = await self._db.execute(
            select(User)
            .where(User.tenant_id == tenant_id)
            .order_by(User.id)
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_distinct_tenant_ids_for_users(self, user_ids: list[int]) -> list[str]:
        if not user_ids:
            return []
        result = await self._db.execute(
            select(User.tenant_id)
            .where(User.id.in_(user_ids), User.tenant_id.is_not(None))
            .distinct()
        )
        return [row[0] for row in result.fetchall() if row[0]]

    async def count(self) -> int:
        result = await self._db.execute(select(func.count(User.id)))
        return result.scalar_one()

    async def commit(self) -> None:
        await self._db.commit()
