"""Unit tests: reset-password returns 401 for an invalid/expired token (AI4IDS-1771).

Regression: the automation test TestResetPassword::test_reset_password_invalid_token
was sending an incomplete payload (missing confirm_password), so Pydantic returned
422 for the missing field before token validation ever ran. The invalid-token path
was therefore untested.

With a complete payload, an invalid token raises TokenInvalidError (extends
AuthenticationError → HTTP 401). This file confirms that path and documents
the correct expected status code.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.core.exceptions import TokenInvalidError
from app.services.auth_service import AuthService


def _make_auth_service() -> AuthService:
    return AuthService(
        user_repo=MagicMock(),
        role_service=MagicMock(),
        token_service=MagicMock(),
        credentials_repo=MagicMock(),
        refresh_token_repo=MagicMock(),
        verification_repo=MagicMock(),
        tenant_repo=MagicMock(),
        email_client=MagicMock(),
        cache_service=AsyncMock(),
    )


class TestResetPassword:
    @pytest.mark.asyncio
    async def test_reset_password_invalid_token(self) -> None:
        """Complete payload + invalid token → 401, not 422 for missing field."""
        svc = _make_auth_service()
        svc._resolve_verified_token = AsyncMock(
            side_effect=TokenInvalidError("Invalid reset link.")
        )

        with pytest.raises(TokenInvalidError) as exc_info:
            await svc.reset_password_with_token(
                token="this-is-a-completely-invalid-reset-token-00000",
                new_password="NewPass@9999!",
                confirm_password="NewPass@9999!",
            )

        assert exc_info.value.status_code == 401
        assert "Invalid reset link" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_reset_password_mismatched_passwords_raises_before_token_check(self) -> None:
        """Password mismatch is caught before the token is validated."""
        svc = _make_auth_service()
        svc._resolve_verified_token = AsyncMock()

        with pytest.raises((ValueError, HTTPException)):
            await svc.reset_password_with_token(
                token="any-token",
                new_password="NewPass@9999!",
                confirm_password="DifferentPass@9999!",
            )

        svc._resolve_verified_token.assert_not_awaited()
