"""
UserCredentials table queries.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credentials import UserCredentials
from app.repositories.base import BaseRepository


class CredentialsRepository(BaseRepository):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def get_by_user_id(self, user_id: UUID) -> Optional[UserCredentials]:
        result = await self._db.execute(
            select(UserCredentials).where(UserCredentials.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def update_password(
        self, creds: UserCredentials, password_hash: str, password_salt: str
    ) -> None:
        creds.password_hash = password_hash
        creds.password_salt = password_salt
        await self._db.flush()
