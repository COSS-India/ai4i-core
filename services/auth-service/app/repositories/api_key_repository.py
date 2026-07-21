"""
APIKey table queries.

No business logic, no Redis calls — Postgres only.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import APIKey
from app.models.role import Permission
from app.models.user import User
from app.repositories.base import BaseRepository


class APIKeyRepository(BaseRepository):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def get_by_id(self, key_id: int) -> Optional[APIKey]:
        result = await self._db.execute(
            select(APIKey).where(APIKey.id == key_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_for_owner(self, key_id: int, user_id: UUID) -> Optional[APIKey]:
        """Ownership-scoped lookup: returns None whether the key doesn't exist or belongs
        to a different user, so the caller cannot enumerate valid key IDs."""
        result = await self._db.execute(
            select(APIKey).where(APIKey.id == key_id, APIKey.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_api_key(self, api_key_value: str) -> Optional[APIKey]:
        result = await self._db.execute(
            select(APIKey).where(APIKey.api_key == api_key_value)
        )
        return result.scalar_one_or_none()

    async def get_permission_names_by_ids(self, permission_ids: list[int]) -> dict[int, str]:
        if not permission_ids:
            return {}
        result = await self._db.execute(
            select(Permission.id, Permission.name).where(Permission.id.in_(permission_ids))
        )
        return {pid: name for pid, name in result.all()}

    async def list_by_user(self, user_id: UUID) -> list[APIKey]:
        result = await self._db.execute(
            select(APIKey)
            .where(APIKey.user_id == user_id)
            .order_by(APIKey.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_all_with_users(self, offset: int = 0, limit: int = 100) -> list[tuple[APIKey, User]]:
        result = await self._db.execute(
            select(APIKey, User)
            .join(User, APIKey.user_id == User.id)
            .order_by(APIKey.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.all())

    async def revoke(self, api_key: APIKey) -> None:
        api_key.is_active = False
        await self._db.flush()
