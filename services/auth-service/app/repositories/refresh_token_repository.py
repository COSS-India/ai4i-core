"""
RefreshToken table queries.

One refresh token per user (user_id is the PK). A new login overwrites
the existing row via upsert.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh import RefreshToken
from app.repositories.base import BaseRepository


class RefreshTokenRepository(BaseRepository):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def upsert(self, user_id: UUID, token: str) -> RefreshToken:
        """Insert or overwrite the refresh token for this user using atomic upsert.

        Uses PostgreSQL ON CONFLICT DO UPDATE to ensure atomicity under concurrent
        logins for the same user. This prevents race conditions where two concurrent
        requests both read "no existing row" and both attempt INSERT.
        """
        stmt = pg_insert(RefreshToken).values(user_id=user_id, refresh_token=token)
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id"],
            set_={"refresh_token": stmt.excluded.refresh_token, "updated_at": func.now()},
        )
        await self._db.execute(stmt)
        await self._db.flush()
        return await self.get_by_user_id(user_id)

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
