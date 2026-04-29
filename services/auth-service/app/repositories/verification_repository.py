"""
TokenVerification table queries — used for email activation setup links.

The token_verification table has no user_id FK column. User identity is
embedded in the signed JWT token string itself, and created_by stores
the user UUID string to allow bulk-deactivation on resend.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.verification import TokenVerification
from app.repositories.base import BaseRepository


class VerificationRepository(BaseRepository):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def get_by_token(self, token: str) -> Optional[TokenVerification]:
        result = await self._db.execute(
            select(TokenVerification).where(TokenVerification.token == token)
        )
        return result.scalar_one_or_none()

    async def deactivate(self, token_obj: TokenVerification) -> None:
        token_obj.is_active = False
        await self._db.flush()

    async def deactivate_all_for_user(self, user_uuid: str) -> None:
        """Mark all active tokens for a user as inactive before issuing a new one."""
        result = await self._db.execute(
            select(TokenVerification).where(
                TokenVerification.created_by == user_uuid,
                TokenVerification.is_active == True,  # noqa: E712
            )
        )
        for token_obj in result.scalars().all():
            token_obj.is_active = False
        await self._db.flush()
