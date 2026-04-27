"""
APIKey table queries.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import APIKey
from app.models.role import Permission
from app.models.user import User


class APIKeyRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, api_key: APIKey) -> APIKey:
        self._db.add(api_key)
        await self._db.flush()
        return api_key

    async def get_by_id(self, key_id: int) -> Optional[APIKey]:
        result = await self._db.execute(select(APIKey).where(APIKey.id == key_id))
        return result.scalar_one_or_none()

    async def get_by_api_key(self, api_key_value: str) -> Optional[APIKey]:
        """Look up a key by the token_id stored in the api_key column."""
        result = await self._db.execute(
            select(APIKey).where(APIKey.api_key == api_key_value)
        )
        return result.scalar_one_or_none()

    async def get_permission_names_by_ids(self, permission_ids: list[int]) -> dict[int, str]:
        if not permission_ids:
            return {}
        result = await self._db.execute(
            select(Permission.id, Permission.name).where(
                Permission.id.in_(permission_ids)
            )
        )
        return {pid: name for pid, name in result.all()}

    async def list_by_user(self, user_id: UUID, active_only: bool = False) -> list[APIKey]:
        query = select(APIKey).where(APIKey.user_id == user_id)
        if active_only:
            query = query.where(APIKey.is_active == True)  # noqa: E712
        result = await self._db.execute(query.order_by(APIKey.created_at.desc()))
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

    async def update(self, api_key: APIKey, data: dict) -> APIKey:
        for key, value in data.items():
            if hasattr(api_key, key) and value is not None:
                setattr(api_key, key, value)
        await self._db.flush()
        return api_key

    async def deactivate(self, api_key: APIKey) -> None:
        api_key.is_active = False
        await self._db.flush()

    async def commit(self) -> None:
        await self._db.commit()
