"""Unit tests: login reuses an existing, still-valid refresh token instead of
overwriting it (AI4IDS-3793).

Previously every login unconditionally minted a new refresh token and
upserted it, which overwrote the single DB row for that user. A user logged
into N different browsers would have every other browser's refresh token
silently invalidated the moment any one of them logged in again, well
before that token had actually expired.

change_password is the one caller that must keep force-rotating the
refresh token on every call (it relies on issue_session to actually revoke
the old one, since it never deletes the DB row itself).
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.constants import TokenType
from app.core.exceptions import TokenExpiredError, TokenInvalidError
from app.core.security import PasswordHashResult
from app.models.user import User
from app.services.auth_service import AuthService

_TEST_PASS = f"test-{uuid4().hex[:12]}!"


def _make_auth_service() -> AuthService:
    svc = AuthService(
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
    svc._tokens.create_access_token.return_value = "new-access-token"
    svc._roles.get_user_permission_ids.return_value = []
    return svc


def _system_user() -> User:
    """tenant_id=None so _assert_user_tenant_active is a no-op."""
    return User(
        id=uuid4(),
        email="test-user@example.invalid",
        username=uuid4().hex[:12],
        tenant_id=None,
        is_active=True,
    )


def _wire_valid_login(svc: AuthService, user: User, monkeypatch) -> None:
    creds = MagicMock(password_hash="hash", password_salt="salt")
    svc._users.get_by_email = AsyncMock(return_value=user)
    svc._credentials.get_by_user_id = AsyncMock(return_value=creds)
    monkeypatch.setattr(
        "app.services.auth_service.password_manager.verify_password_async",
        AsyncMock(return_value=True),
    )


@pytest.mark.asyncio
class TestLoginReusesValidRefreshToken:
    async def test_reuses_existing_token_when_still_valid(self, monkeypatch):
        svc = _make_auth_service()
        user = _system_user()
        _wire_valid_login(svc, user, monkeypatch)

        existing_row = MagicMock(refresh_token="existing-refresh-token")
        svc._refresh_tokens.get_by_user_id = AsyncMock(return_value=existing_row)
        svc._tokens.validate_token = MagicMock(
            return_value=MagicMock(token_type=TokenType.REFRESH)
        )

        result = await svc.login(user.email, _TEST_PASS)

        assert result.refresh_token == "existing-refresh-token"
        svc._tokens.create_refresh_token.assert_not_called()
        svc._refresh_tokens.upsert.assert_not_called()

    async def test_mints_new_token_when_none_exists(self, monkeypatch):
        svc = _make_auth_service()
        user = _system_user()
        _wire_valid_login(svc, user, monkeypatch)

        svc._refresh_tokens.get_by_user_id = AsyncMock(return_value=None)
        svc._tokens.create_refresh_token.return_value = "brand-new-refresh-token"

        result = await svc.login(user.email, _TEST_PASS)

        assert result.refresh_token == "brand-new-refresh-token"
        svc._refresh_tokens.upsert.assert_awaited_once_with(user.id, "brand-new-refresh-token")

    async def test_mints_new_token_when_existing_one_expired(self, monkeypatch):
        svc = _make_auth_service()
        user = _system_user()
        _wire_valid_login(svc, user, monkeypatch)

        existing_row = MagicMock(refresh_token="expired-refresh-token")
        svc._refresh_tokens.get_by_user_id = AsyncMock(return_value=existing_row)
        svc._tokens.validate_token = MagicMock(side_effect=TokenExpiredError())
        svc._tokens.create_refresh_token.return_value = "rotated-refresh-token"

        result = await svc.login(user.email, _TEST_PASS)

        assert result.refresh_token == "rotated-refresh-token"
        svc._refresh_tokens.upsert.assert_awaited_once_with(user.id, "rotated-refresh-token")

    async def test_mints_new_token_when_existing_one_invalid(self, monkeypatch):
        svc = _make_auth_service()
        user = _system_user()
        _wire_valid_login(svc, user, monkeypatch)

        existing_row = MagicMock(refresh_token="corrupt-refresh-token")
        svc._refresh_tokens.get_by_user_id = AsyncMock(return_value=existing_row)
        svc._tokens.validate_token = MagicMock(side_effect=TokenInvalidError())
        svc._tokens.create_refresh_token.return_value = "rotated-refresh-token"

        result = await svc.login(user.email, _TEST_PASS)

        assert result.refresh_token == "rotated-refresh-token"
        svc._refresh_tokens.upsert.assert_awaited_once_with(user.id, "rotated-refresh-token")

    async def test_mints_new_token_when_existing_one_is_wrong_type(self, monkeypatch):
        """Defensive: a row whose decoded payload somehow isn't type=refresh
        must never be handed back out as a refresh token."""
        svc = _make_auth_service()
        user = _system_user()
        _wire_valid_login(svc, user, monkeypatch)

        existing_row = MagicMock(refresh_token="wrong-type-token")
        svc._refresh_tokens.get_by_user_id = AsyncMock(return_value=existing_row)
        svc._tokens.validate_token = MagicMock(
            return_value=MagicMock(token_type=TokenType.ACCESS)
        )
        svc._tokens.create_refresh_token.return_value = "rotated-refresh-token"

        result = await svc.login(user.email, _TEST_PASS)

        assert result.refresh_token == "rotated-refresh-token"
        svc._refresh_tokens.upsert.assert_awaited_once_with(user.id, "rotated-refresh-token")


@pytest.mark.asyncio
class TestChangePasswordStillForcesNewRefreshToken:
    async def test_change_password_rotates_even_if_existing_token_still_valid(self, monkeypatch):
        """change_password must never reuse the pre-existing refresh token —
        it never deletes the DB row itself, so reuse here would silently
        keep an old/possibly-compromised session's refresh token alive."""
        svc = _make_auth_service()
        user = MagicMock(id=uuid4())
        creds = MagicMock(password_hash="hash", password_salt="salt")
        svc._credentials.get_by_user_id = AsyncMock(return_value=creds)

        existing_row = MagicMock(refresh_token="pre-existing-refresh-token")
        svc._refresh_tokens.get_by_user_id = AsyncMock(return_value=existing_row)
        svc._tokens.validate_token = MagicMock(
            return_value=MagicMock(token_type=TokenType.REFRESH)
        )
        svc._tokens.create_refresh_token.return_value = "post-change-refresh-token"

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

        assert result.refresh_token == "post-change-refresh-token"
        svc._refresh_tokens.get_by_user_id.assert_not_called()
        svc._refresh_tokens.upsert.assert_awaited_once_with(user.id, "post-change-refresh-token")
