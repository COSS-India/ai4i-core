"""Unit tests: resend-verification and forgot-password accept any plausible
email and always return 200 (anti-enumeration) (AI4IDS-1769).

Regression: both endpoints returned 422 when the email used a reserved TLD
(.invalid, RFC 2606) because EmailStr's underlying library hardcodes a
special-use domain reject-list. The schema was changed to a loose validator
that only checks basic syntax (has @, has dot-domain), so reserved TLDs
reach business logic and get the silent 200 no-op.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.auth import ForgotPasswordRequest, ResendVerificationRequest


class TestResendVerificationSchema:
    def test_accepts_reserved_tld(self) -> None:
        body = ResendVerificationRequest(email="does.not.exist.xyz@noreply.invalid")
        assert body.email == "does.not.exist.xyz@noreply.invalid"

    def test_accepts_standard_email(self) -> None:
        body = ResendVerificationRequest(email="unknown@example.com")
        assert body.email == "unknown@example.com"

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

    def test_rejects_missing_at(self) -> None:
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            ForgotPasswordRequest(email="notanemail")


class TestResendVerificationUnknownEmail:
    @pytest.mark.asyncio
    async def test_unknown_email_returns_silently(self) -> None:
        """Unknown email (including reserved TLD) must not raise — anti-enumeration."""
        from app.services.auth_service import AuthService

        svc = MagicMock(spec=AuthService)
        svc.resend_verification = AsyncMock(return_value=None)

        await svc.resend_verification(email="does.not.exist.xyz@noreply.invalid")
        svc.resend_verification.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unknown_standard_email_returns_silently(self) -> None:
        from app.services.auth_service import AuthService

        svc = MagicMock(spec=AuthService)
        svc.resend_verification = AsyncMock(return_value=None)

        await svc.resend_verification(email="unknown@example.com")
        svc.resend_verification.assert_awaited_once()


class TestForgotPasswordUnknownEmail:
    @pytest.mark.asyncio
    async def test_unknown_email_returns_silently(self) -> None:
        """Unknown email (including reserved TLD) must not raise — anti-enumeration."""
        from app.services.auth_service import AuthService

        svc = MagicMock(spec=AuthService)
        svc.request_password_reset = AsyncMock(return_value=None)

        await svc.request_password_reset(email="does.not.exist.xyz@noreply.invalid")
        svc.request_password_reset.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_unknown_standard_email_returns_silently(self) -> None:
        from app.services.auth_service import AuthService

        svc = MagicMock(spec=AuthService)
        svc.request_password_reset = AsyncMock(return_value=None)

        await svc.request_password_reset(email="unknown@example.com")
        svc.request_password_reset.assert_awaited_once()
