"""
UserCredentials table queries.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from collections.abc import Iterable

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

    async def has_credentials(self, user_id: UUID) -> bool:
        """True when the user has set a password (a credentials row exists)."""
        result = await self._db.execute(
            select(UserCredentials.id).where(UserCredentials.user_id == user_id)
        )
        return result.scalar_one_or_none() is not None

    async def user_ids_with_credentials(
        self, user_ids: Iterable[UUID]
    ) -> set[UUID]:
        """Return the subset of ``user_ids`` that have a credentials row.

        One query for the whole page (used by tenant-user list responses to
        derive ``is_activated`` without an N+1 per-user lookup).
        """
        ids = list(user_ids)
        if not ids:
            return set()
        result = await self._db.execute(
            select(UserCredentials.user_id).where(
                UserCredentials.user_id.in_(ids)
            )
        )
        return set(result.scalars().all())

    async def update_password(
        self, creds: UserCredentials, password_hash: str, password_salt: str
    ) -> None:
        creds.password_hash = password_hash
        creds.password_salt = password_salt
        await self._db.flush()
