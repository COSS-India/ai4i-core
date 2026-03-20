"""
APIKey table queries.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import APIKey
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

    async def get_by_token_id(self, token_id: str) -> Optional[APIKey]:
        result = await self._db.execute(select(APIKey).where(APIKey.token_id == token_id))
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: int, active_only: bool = False) -> list[APIKey]:
        query = select(APIKey).where(APIKey.user_id == user_id)
        if active_only:
            query = query.where(APIKey.is_active == True, APIKey.is_revoked == False)  # noqa: E712
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

    async def revoke(self, api_key: APIKey) -> None:
        api_key.is_revoked = True
        api_key.is_active = False
        api_key.status = "revoked"
        await self._db.flush()

    async def update_last_used(self, api_key: APIKey) -> None:
        api_key.last_used = datetime.now(timezone.utc)
        await self._db.flush()

    async def commit(self) -> None:
        await self._db.commit()
