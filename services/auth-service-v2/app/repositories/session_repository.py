"""
UserSession table queries.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import UserSession


class SessionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, session: UserSession) -> UserSession:
        self._db.add(session)
        await self._db.flush()
        return session

    async def get_active_by_token(self, session_token: str) -> Optional[UserSession]:
        result = await self._db.execute(
            select(UserSession).where(
                UserSession.session_token == session_token,
                UserSession.is_active == True,  # noqa: E712
                UserSession.expires_at > datetime.now(timezone.utc),
            )
        )
        return result.scalar_one_or_none()

    async def get_by_token_id(self, token_id: str) -> Optional[UserSession]:
        result = await self._db.execute(
            select(UserSession).where(UserSession.token_id == token_id)
        )
        return result.scalar_one_or_none()

    async def get_by_refresh_token(self, refresh_token: str) -> Optional[UserSession]:
        result = await self._db.execute(
            select(UserSession).where(
                UserSession.refresh_token == refresh_token,
                UserSession.is_active == True,  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def invalidate(self, session: UserSession) -> None:
        session.is_active = False
        await self._db.flush()

    async def invalidate_all_for_user(
        self, user_id: int, except_token: Optional[str] = None
    ) -> list[UserSession]:
        query = select(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.is_active == True,  # noqa: E712
        )
        if except_token:
            query = query.where(UserSession.session_token != except_token)

        result = await self._db.execute(query)
        sessions = result.scalars().all()
        for s in sessions:
            s.is_active = False
        await self._db.flush()
        return sessions

    async def invalidate_all_for_users(self, user_ids: list[int]) -> list[UserSession]:
        """Batch invalidate active sessions for multiple users and return affected sessions."""
        if not user_ids:
            return []

        result = await self._db.execute(
            select(UserSession).where(
                UserSession.user_id.in_(user_ids),
                UserSession.is_active == True,  # noqa: E712
            )
        )
        sessions = result.scalars().all()
        for s in sessions:
            s.is_active = False
        await self._db.flush()
        return sessions

    async def cleanup_expired(self) -> int:
        result = await self._db.execute(
            select(UserSession).where(
                UserSession.expires_at < datetime.now(timezone.utc),
                UserSession.is_active == True,  # noqa: E712
            )
        )
        sessions = result.scalars().all()
        for s in sessions:
            s.is_active = False
        await self._db.flush()
        return len(sessions)

    async def commit(self) -> None:
        await self._db.commit()
