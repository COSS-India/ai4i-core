"""
Session lifecycle management.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.config import settings
from app.models.session import UserSession
from app.repositories.session_repository import SessionRepository
from app.services.cache_service import CacheService


class SessionService:
    def __init__(self, session_repo: SessionRepository, cache_service: CacheService) -> None:
        self._repo = session_repo
        self._cache = cache_service

    async def create_session(
        self,
        user_id: int,
        access_token: str,
        refresh_token: str,
        token_id: str,
        device_info: Optional[dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        expires_delta: Optional[timedelta] = None,
    ) -> UserSession:
        """Create a session and store the refresh token_id in Redis."""
        if expires_delta is None:
            expires_delta = timedelta(days=settings.refresh_token_expire_days)

        session = UserSession(
            user_id=user_id,
            session_token=access_token,
            refresh_token=refresh_token,
            token_id=token_id,
            device_info=device_info,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=datetime.now(timezone.utc) + expires_delta,
        )
        await self._repo.create(session)

        # Cache the refresh token_id in Redis
        ttl = int(expires_delta.total_seconds())
        await self._cache.store_refresh_token(token_id, ttl)

        return session

    async def invalidate_session(self, session: UserSession) -> None:
        """Invalidate a session and revoke its refresh token from Redis."""
        await self._repo.invalidate(session)
        if session.token_id:
            await self._cache.revoke_refresh_token(session.token_id)

    async def invalidate_all_for_user(
        self, user_id: int, except_token: Optional[str] = None
    ) -> int:
        """Invalidate all sessions for a user (except optionally one)."""
        return await self._repo.invalidate_all_for_user(user_id, except_token)

    async def get_session_by_refresh_token(self, refresh_token: str) -> Optional[UserSession]:
        return await self._repo.get_by_refresh_token(refresh_token)

    async def cleanup_expired(self) -> int:
        return await self._repo.cleanup_expired()

    async def commit(self) -> None:
        await self._repo.commit()
