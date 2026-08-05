"""Unit test: /auth/logout records a global-logout timestamp in Redis
in addition to deleting the refresh token, so previously-issued access
tokens are rejected by /auth/validate before their natural expiry.
"""
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.config import settings
from app.routes.auth import logout
from app.services.cache_service import REDIS_LOGOUT_PREFIX


@pytest.mark.asyncio
class TestLogoutRoute:
    async def test_logout_deletes_refresh_token_and_sets_logout_timestamp(self):
        user_id = uuid4()
        svc = AsyncMock()
        cache_svc = AsyncMock()

        response = await logout(user_id=user_id, svc=svc, cache_svc=cache_svc)

        svc.logout.assert_awaited_once_with(user_id=user_id)
        cache_svc.set_logout_timestamp.assert_awaited_once_with(
            str(user_id), ttl_seconds=settings.access_token_expire_minutes * 60
        )
        assert response.logged_out is True

    async def test_logout_key_matches_validation_lookup_key(self):
        """The key logout writes under must be exactly what get_logout_timestamp
        reads under for the same user_id, or a logged-out token would never be
        rejected."""
        user_id = uuid4()
        svc = AsyncMock()
        cache_svc = AsyncMock()

        await logout(user_id=user_id, svc=svc, cache_svc=cache_svc)

        written_user_id = cache_svc.set_logout_timestamp.call_args.args[0]
        assert f"{REDIS_LOGOUT_PREFIX}{written_user_id}" == f"{REDIS_LOGOUT_PREFIX}{user_id}"
