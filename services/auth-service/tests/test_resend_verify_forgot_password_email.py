"""Unit tests: resend-verification, forgot-password, and resend-setup-link
email handling (AI4IDS-1769).

forgot-password and resend-setup-link accept any plausible email and always
return 200 (anti-enumeration). resend-verification rejects unknown emails
with 404 instead of falsely claiming a link was sent.

Regression: all three endpoints returned 422 when the email used a reserved TLD
(.invalid, RFC 2606) because EmailStr's underlying library hardcodes a
special-use domain reject-list. The schema was changed to a loose validator
that only checks basic syntax (has @, has dot-domain), so reserved TLDs
reach business logic and get the silent 200 no-op.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.auth import (
    ForgotPasswordRequest,
    ResendSetupLinkRequest,
    ResendVerificationRequest,
)


class TestResendVerificationSchema:
    def test_accepts_reserved_tld(self) -> None:
        body = ResendVerificationRequest(email="does.not.exist.xyz@noreply.invalid")
        assert body.email == "does.not.exist.xyz@noreply.invalid"

    def test_accepts_standard_email(self) -> None:
        body = ResendVerificationRequest(email="unknown@example.com")
        assert body.email == "unknown@example.com"

    def test_strips_and_lowercases(self) -> None:
        body = ResendVerificationRequest(email="  User@Example.COM  ")
        assert body.email == "user@example.com"

    def test_rejects_missing_at(self) -> None:
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            ResendVerificationRequest(email="notanemail")

    def test_rejects_missing_domain_dot(self) -> None:
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            ResendVerificationRequest(email="user@nodot")


class TestForgotPasswordSchema:
    def test_accepts_reserved_tld(self) -> None:
        body = ForgotPasswordRequest(email="does.not.exist.xyz@noreply.invalid")
        assert body.email == "does.not.exist.xyz@noreply.invalid"

    def test_accepts_standard_email(self) -> None:
        body = ForgotPasswordRequest(email="unknown@example.com")
        assert body.email == "unknown@example.com"

    def test_strips_and_lowercases(self) -> None:
        body = ForgotPasswordRequest(email="  User@Example.COM  ")
        assert body.email == "user@example.com"

    def test_rejects_missing_at(self) -> None:
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            ForgotPasswordRequest(email="notanemail")


class TestResendSetupLinkSchema:
    def test_accepts_reserved_tld(self) -> None:
        body = ResendSetupLinkRequest(email="admin@tenant.invalid")
        assert body.email == "admin@tenant.invalid"

    def test_accepts_standard_email(self) -> None:
        body = ResendSetupLinkRequest(email="admin@example.com")
        assert body.email == "admin@example.com"

    def test_strips_and_lowercases(self) -> None:
        body = ResendSetupLinkRequest(email="  Admin@Example.COM  ")
        assert body.email == "admin@example.com"

    def test_rejects_missing_at(self) -> None:
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            ResendSetupLinkRequest(email="notanemail")


class TestResendVerificationSilentNoOp:
    @pytest.mark.asyncio
    async def test_unknown_email_raises_not_found(self) -> None:
        """resend_verification must reject an unknown email with 404."""
        from app.core.exceptions import UserNotFoundError
        from app.services.auth_service import AuthService

        svc = MagicMock(spec=AuthService)
        svc._users = MagicMock()
        svc._users.get_by_email = AsyncMock(return_value=None)
        svc._credentials = MagicMock()
        svc._verifications = MagicMock()

        # Call the real method bound to our mock instance
        with pytest.raises(UserNotFoundError):
            await AuthService.resend_verification(svc, email="nobody@noreply.invalid")

    @pytest.mark.asyncio
    async def test_active_user_returns_silently(self) -> None:
        """resend_verification must also be a no-op for an already-active user."""
        from app.services.auth_service import AuthService

        active_user = MagicMock()
        active_user.is_active = True

        svc = MagicMock(spec=AuthService)
        svc._users = MagicMock()
        svc._users.get_by_email = AsyncMock(return_value=active_user)

        result = await AuthService.resend_verification(svc, email="active@example.com")
        assert result is None


class TestForgotPasswordSilentNoOp:
    @pytest.mark.asyncio
    async def test_unknown_email_returns_silently(self) -> None:
        """request_password_reset must return None for an unknown email — anti-enumeration."""
        from app.services.auth_service import AuthService

        svc = MagicMock(spec=AuthService)
        svc._users = MagicMock()
        svc._users.get_by_email = AsyncMock(return_value=None)

        result = await AuthService.request_password_reset(svc, email="nobody@noreply.invalid")
        assert result is None

    @pytest.mark.asyncio
    async def test_inactive_user_returns_silently(self) -> None:
        """request_password_reset must be a no-op for an inactive user."""
        from app.services.auth_service import AuthService

        inactive_user = MagicMock()
        inactive_user.is_active = False

        svc = MagicMock(spec=AuthService)
        svc._users = MagicMock()
        svc._users.get_by_email = AsyncMock(return_value=inactive_user)

        result = await AuthService.request_password_reset(svc, email="inactive@example.com")
        assert result is None


class TestResendSetupLinkSilentNoOp:
    @pytest.mark.asyncio
    async def test_unknown_email_returns_silently(self) -> None:
        """resend_setup_link must return None for an unknown email — anti-enumeration."""
        from app.services.auth_service import AuthService

        svc = MagicMock(spec=AuthService)
        svc._users = MagicMock()
        svc._users.get_by_email = AsyncMock(return_value=None)

        result = await AuthService.resend_setup_link(svc, email="nobody@tenant.invalid")
        assert result is None
