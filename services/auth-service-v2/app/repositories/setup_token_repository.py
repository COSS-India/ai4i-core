"""
Setup token table queries.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.setup_token import SetupToken


class SetupTokenRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, setup_token: SetupToken) -> SetupToken:
        self._db.add(setup_token)
        await self._db.flush()
        return setup_token

    async def get_by_token(self, token: str) -> Optional[SetupToken]:
        result = await self._db.execute(
            select(SetupToken).where(SetupToken.token == token)
        )
        return result.scalar_one_or_none()

    async def deactivate_unused_for_user(self, user_id: int) -> None:
        await self._db.execute(
            update(SetupToken)
            .where(
                SetupToken.user_id == user_id,
                SetupToken.is_active.is_(True),
                SetupToken.used_at.is_(None),
            )
            .values(is_active=False)
        )

    async def mark_used(self, setup_token: SetupToken, used_at: datetime) -> None:
        setup_token.used_at = used_at
        setup_token.is_active = False
        await self._db.flush()

    async def commit(self) -> None:
        await self._db.commit()
