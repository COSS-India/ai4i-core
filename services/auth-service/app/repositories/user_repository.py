"""
User table queries.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def get_by_id(self, user_id: UUID) -> Optional[User]:
        result = await self._db.execute(
            select(User).where(User.id == user_id, User.is_delete.isnot(True))
        )
        return result.scalar_one_or_none()

    async def is_active(self, user_id: UUID) -> bool:
        """Lightweight check: is user active? (no full object fetch)."""
        result = await self._db.execute(
            select(User.is_active).where(User.id == user_id, User.is_delete.isnot(True))
        )
        is_active = result.scalar_one_or_none()
        return is_active is True

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self._db.execute(
            select(User).where(
                func.lower(User.email) == email.lower().strip(),
                User.is_delete.isnot(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> Optional[User]:
        result = await self._db.execute(
            select(User).where(User.username == username, User.is_delete.isnot(True))
        )
        return result.scalar_one_or_none()

    async def list_all(self, offset: int = 0, limit: int = 100) -> list[User]:
        result = await self._db.execute(
            select(User)
            .where(User.is_delete.isnot(True))
            .order_by(func.lower(User.username).asc(), User.id.asc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_tenant(self, tenant_id: int, offset: int = 0, limit: int = 100) -> list[User]:
        result = await self._db.execute(
            select(User)
            .where(User.tenant_id == tenant_id, User.is_delete.isnot(True))
            .order_by(User.id)
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())
