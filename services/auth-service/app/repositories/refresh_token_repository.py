"""
RefreshToken table queries.

One refresh token per user (user_id is the PK). A new login overwrites
the existing row via upsert.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh import RefreshToken


class RefreshTokenRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def upsert(self, user_id: UUID, token: str) -> RefreshToken:
        """Insert or overwrite the refresh token for this user."""
        existing = await self.get_by_user_id(user_id)
        if existing:
            existing.refresh_token = token
            await self._db.flush()
            return existing
        new_token = RefreshToken(user_id=user_id, refresh_token=token)
        self._db.add(new_token)
        await self._db.flush()
        return new_token

    async def get_by_token(self, token: str) -> Optional[RefreshToken]:
        result = await self._db.execute(
            select(RefreshToken).where(RefreshToken.refresh_token == token)
        )
        return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: UUID) -> Optional[RefreshToken]:
        result = await self._db.execute(
            select(RefreshToken).where(RefreshToken.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def delete_by_user_id(self, user_id: UUID) -> None:
        existing = await self.get_by_user_id(user_id)
        if existing:
            await self._db.delete(existing)
            await self._db.flush()

    async def commit(self) -> None:
        await self._db.commit()
