"""Unit tests: change_password and reset_password_with_token must set the
global-logout timestamp so already-issued access tokens are rejected, not
just refresh tokens revoked in the DB.

change_password no longer tries to "preserve" a DB-stored refresh token for
the caller (the refresh table holds only one row per user, so guessing which
one was the caller's was unreliable). Instead it revokes everything, then
mints and returns a fresh token pair for the caller directly.

Also covers the boundary case for the revocation check itself: a token
whose iat equals the logout timestamp must NOT be treated as revoked,
since set_logout_timestamp now stores whole seconds (see cache_service.py)
to match JWT iat precision.
"""
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.security import PasswordHashResult
from app.core.config import settings
from app.dependencies.auth import _check_logout_revocation
from app.services.auth_service import AuthService
from app.services.cache_service import REDIS_LOGOUT_PREFIX, CacheService


def _make_auth_service(**overrides) -> AuthService:
    kwargs = dict(
        user_repo=AsyncMock(),
        role_service=AsyncMock(),
        token_service=MagicMock(),
        credentials_repo=AsyncMock(),
        refresh_token_repo=AsyncMock(),
        verification_repo=AsyncMock(),
        tenant_repo=MagicMock(),
        email_client=MagicMock(),
        cache_service=AsyncMock(),
    )
    kwargs.update(overrides)
    svc = AuthService(**kwargs)
    svc._tokens.create_access_token.return_value = "new-access-token"
    svc._tokens.create_refresh_token.return_value = "new-refresh-token"
    svc._roles.get_user_permission_ids.return_value = []
    return svc


@pytest.mark.asyncio
class TestChangePasswordRevokesSessions:
    async def test_change_password_sets_logout_timestamp(self, monkeypatch):
        user = MagicMock(id=uuid4())
        creds = MagicMock(password_hash="hash", password_salt="salt")

        svc = _make_auth_service()
        svc._credentials.get_by_user_id = AsyncMock(return_value=creds)

        monkeypatch.setattr(
            "app.services.auth_service.password_manager.verify_password_async",
            AsyncMock(side_effect=[True, False]),
        )
        monkeypatch.setattr(
            "app.services.auth_service.password_manager.hash_password_async",
            AsyncMock(return_value=PasswordHashResult(hashed="new-hash", salt="new-salt")),
        )

        result = await svc.change_password(
            user=user,
            current_password="OldPass@9999!",
            new_password="NewPass@9999!",
            confirm_password="NewPass@9999!",
        )

        svc._cache.revoke_all_sessions.assert_awaited_once_with(str(user.id))
        # The caller gets a fresh pair back directly — no dependence on
        # guessing which DB-stored refresh token belongs to them.
        assert result.access_token == "new-access-token"
        assert result.refresh_token == "new-refresh-token"
        svc._refresh_tokens.upsert.assert_awaited_once_with(user.id, "new-refresh-token")

    async def test_change_password_still_succeeds_when_redis_write_fails(self, monkeypatch):
        """A Redis blip must not turn a completed password change into a 500 —
        credentials/refresh tokens are already committed by that point."""
        user = MagicMock(id=uuid4())
        creds = MagicMock(password_hash="hash", password_salt="salt")

        svc = _make_auth_service()
        svc._credentials.get_by_user_id = AsyncMock(return_value=creds)
        svc._cache.revoke_all_sessions = AsyncMock(side_effect=ConnectionError("redis down"))

        monkeypatch.setattr(
            "app.services.auth_service.password_manager.verify_password_async",
            AsyncMock(side_effect=[True, False]),
        )
        monkeypatch.setattr(
            "app.services.auth_service.password_manager.hash_password_async",
            AsyncMock(return_value=PasswordHashResult(hashed="new-hash", salt="new-salt")),
        )

        await svc.change_password(
            user=user,
            current_password="OldPass@9999!",
            new_password="NewPass@9999!",
            confirm_password="NewPass@9999!",
        )  # must not raise


@pytest.mark.asyncio
class TestResetPasswordRevokesSessions:
    async def test_reset_password_sets_logout_timestamp(self, monkeypatch):
        user = MagicMock(id=uuid4())
        creds = MagicMock(password_hash="hash", password_salt="salt")

        svc = _make_auth_service()
        svc._resolve_verified_token = AsyncMock(return_value=(MagicMock(), user))
        svc._credentials.get_by_user_id = AsyncMock(return_value=creds)

        monkeypatch.setattr(
            "app.services.auth_service.password_manager.hash_password_async",
            AsyncMock(return_value=PasswordHashResult(hashed="new-hash", salt="new-salt")),
        )

        await svc.reset_password_with_token(
            token="valid-reset-token",
            new_password="NewPass@9999!",
            confirm_password="NewPass@9999!",
        )

        svc._cache.revoke_all_sessions.assert_awaited_once_with(str(user.id))

    async def test_reset_password_still_succeeds_when_redis_write_fails(self, monkeypatch):
        user = MagicMock(id=uuid4())
        creds = MagicMock(password_hash="hash", password_salt="salt")

        svc = _make_auth_service()
        svc._resolve_verified_token = AsyncMock(return_value=(MagicMock(), user))
        svc._credentials.get_by_user_id = AsyncMock(return_value=creds)
        svc._cache.revoke_all_sessions = AsyncMock(side_effect=ConnectionError("redis down"))

        monkeypatch.setattr(
            "app.services.auth_service.password_manager.hash_password_async",
            AsyncMock(return_value=PasswordHashResult(hashed="new-hash", salt="new-salt")),
        )

        await svc.reset_password_with_token(
            token="valid-reset-token",
            new_password="NewPass@9999!",
            confirm_password="NewPass@9999!",
        )  # must not raise


@pytest.mark.asyncio
class TestRevokeAllSessions:
    async def test_revoke_all_sessions_uses_access_token_ttl(self):
        redis = AsyncMock()
        cache = CacheService(redis)

        await cache.revoke_all_sessions("user-1")

        args, _ = redis.setex.call_args
        key, ttl, _value = args
        assert key == f"{REDIS_LOGOUT_PREFIX}user-1"
        assert ttl == settings.access_token_expire_minutes * 60


@pytest.mark.asyncio
class TestLogoutRevocationBoundary:
    async def test_token_issued_exactly_at_logout_timestamp_is_not_revoked(self):
        """set_logout_timestamp now stores whole seconds (int truncation) to
        match JWT iat precision. A token issued in the same second as the
        logout write (iat == logout_ts) must not be treated as revoked, or
        the caller's own freshly-refreshed token would be rejected."""
        redis = AsyncMock()
        cache = CacheService(redis)
        redis.get.return_value = "1700000000"

        revoked = await _check_logout_revocation(
            "user-1", issued_at=1700000000.0, cache_service=cache
        )
        assert revoked is False
