"""
Session lifecycle management — Redis only (no DB table).

Token revocation is tracked via Redis:
- refresh:{token_id} → "1" with TTL (existence = valid)
- user_tokens:{user_id} → SET of active token_ids (for bulk revocation)
"""

import logging

from app.core.config import settings
from app.services.cache_service import CacheService

logger = logging.getLogger(__name__)


class SessionService:
    def __init__(self, cache_service: CacheService) -> None:
        self._cache = cache_service

    async def create_session(
        self,
        user_id: int,
        token_id: str,
    ) -> None:
        """Track a refresh token_id in Redis for revocation."""
        ttl = settings.refresh_token_expire_days * 86400
        await self._cache.store_refresh_token(token_id, ttl)
        await self._cache.track_user_token(user_id, token_id)

    async def invalidate_by_token_id(self, user_id: int, token_id: str) -> None:
        """Revoke a single refresh token."""
        await self._cache.revoke_refresh_token(token_id)
        await self._cache.remove_user_token(user_id, token_id)

    async def is_refresh_token_active(self, token_id: str) -> bool:
        """Check if a refresh token is still active. Redis only."""
        return await self._cache.is_refresh_token_valid(token_id)
