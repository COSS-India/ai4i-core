"""Unit tests: resend-verification, forgot-password, and resend-setup-link
email handling (AI4IDS-1769).

All three endpoints accept any plausible email and always return 200 with a
generic message (anti-enumeration): unknown emails are a silent no-op.

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
    async def test_unknown_email_returns_silently(self) -> None:
        """resend_verification must return None for an unknown email — anti-enumeration."""
        from app.services.auth_service import AuthService

        svc = MagicMock(spec=AuthService)
        svc._users = MagicMock()
        svc._users.get_by_email = AsyncMock(return_value=None)

        # Call the real method bound to our mock instance
        result = await AuthService.resend_verification(svc, email="nobody@noreply.invalid")
        assert result is None

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

        svc = MagicMock()
        svc._resolve_setup_link_user = AsyncMock(return_value=None)

        result = await AuthService.resend_setup_link(
            svc, email="nobody@tenant.invalid"
        )
        assert result is None


class TestResolveSetupLinkUser:
    @pytest.mark.asyncio
    async def test_direct_user_lookup(self) -> None:
        from app.services.auth_service import AuthService

        user = MagicMock()
        svc = MagicMock()
        svc._users = MagicMock()
        svc._users.get_by_email = AsyncMock(return_value=user)

        resolved = await AuthService._resolve_setup_link_user(
            svc, email="admin@example.com"
        )
        assert resolved is user
        svc._users.get_by_email.assert_awaited_once_with("admin@example.com")

    @pytest.mark.asyncio
    async def test_masked_email_requires_tenant_id_without_auth(self) -> None:
        from app.services.auth_service import AuthService

        svc = MagicMock()
        svc._users = MagicMock()
        svc._users.get_by_email = AsyncMock(return_value=None)
        svc._tenants = MagicMock()
        svc._tenants.list_all = AsyncMock()

        resolved = await AuthService._resolve_setup_link_user(
            svc, email="a***@e***.com"
        )
        assert resolved is None
        svc._tenants.list_all.assert_not_called()

    @pytest.mark.asyncio
    async def test_masked_email_with_tenant_id_works_without_auth(self) -> None:
        from app.models.tenant import Tenant, TenantStatus
        from app.services.auth_service import AuthService
        from app.utils.masking import mask_email

        admin = MagicMock()
        tenant = Tenant(
            id=7,
            name="Contact",
            organisation="Acme",
            email="admin@example.com",
            status=TenantStatus.PENDING,
        )
        masked = mask_email(tenant.email)

        svc = MagicMock()
        svc._users = MagicMock()
        svc._users.get_by_email = AsyncMock(return_value=admin)
        svc._tenants = MagicMock()
        svc._tenants.get_by_id = AsyncMock(return_value=tenant)

        resolved = await AuthService._resolve_masked_setup_user_by_tenant_id(
            svc, masked, 7
        )
        assert resolved is admin
        svc._tenants.get_by_id.assert_awaited_once_with(7)

    @pytest.mark.asyncio
    async def test_masked_email_resolves_by_tenant_id(self) -> None:
        from app.models.tenant import Tenant, TenantStatus
        from app.services.auth_service import AuthService
        from app.utils.masking import mask_email

        admin = MagicMock()
        caller = MagicMock()
        tenant = Tenant(
            id=7,
            name="Contact",
            organisation="Acme",
            email="admin@example.com",
            status=TenantStatus.PENDING,
        )
        masked = mask_email(tenant.email)

        svc = MagicMock()
        svc._users = MagicMock()
        svc._users.get_by_email = AsyncMock(return_value=admin)
        svc._tenants = MagicMock()
        svc._tenants.get_by_id = AsyncMock(return_value=tenant)
        svc._caller_may_access_tenant_for_setup_resend = AsyncMock(return_value=True)

        resolved = await AuthService._resolve_masked_setup_user_by_tenant_id(
            svc, masked, 7, caller
        )
        assert resolved is admin
        svc._tenants.get_by_id.assert_awaited_once_with(7)

    @pytest.mark.asyncio
    async def test_masked_email_platform_staff_scans_pending_tenants(self) -> None:
        from app.models.tenant import Tenant, TenantStatus
        from app.services.auth_service import AuthService
        from app.utils.masking import mask_email

        admin = MagicMock()
        caller = MagicMock()
        tenant = Tenant(
            id=7,
            name="Contact",
            organisation="Acme",
            email="admin@example.com",
            status=TenantStatus.PENDING,
        )
        masked = mask_email(tenant.email)

        svc = MagicMock()
        svc._users = MagicMock()
        svc._users.get_by_email = AsyncMock(return_value=admin)
        svc._tenants = MagicMock()
        svc._tenants.list_all = AsyncMock(return_value=[tenant])

        resolved = await AuthService._resolve_masked_setup_user_by_scan(
            svc, masked, caller
        )
        assert resolved is admin
        svc._tenants.list_all.assert_awaited_once_with(
            status=TenantStatus.PENDING, offset=0, limit=100
        )

    @pytest.mark.asyncio
    async def test_masked_email_tenant_admin_uses_own_tenant_only(self) -> None:
        from app.models.tenant import Tenant, TenantStatus
        from app.services.auth_service import AuthService
        from app.utils.masking import mask_email

        admin = MagicMock()
        caller = MagicMock()
        caller.tenant_id = 7
        tenant = Tenant(
            id=7,
            name="Contact",
            organisation="Acme",
            email="admin@example.com",
            status=TenantStatus.PENDING,
        )
        masked = mask_email(tenant.email)

        svc = MagicMock()
        svc._users = MagicMock()
        svc._users.get_by_email = AsyncMock(return_value=None)
        svc._is_platform_staff = AsyncMock(return_value=False)
        svc._resolve_masked_setup_user_by_tenant_id = AsyncMock(return_value=admin)

        resolved = await AuthService._resolve_setup_link_user(
            svc, email=masked, caller=caller
        )
        assert resolved is admin
        svc._resolve_masked_setup_user_by_tenant_id.assert_awaited_once_with(
            masked, 7, caller
        )

    @pytest.mark.asyncio
    async def test_masked_email_no_match_is_silent(self) -> None:
        from app.services.auth_service import AuthService

        caller = MagicMock()
        svc = MagicMock()
        svc._users = MagicMock()
        svc._users.get_by_email = AsyncMock(return_value=None)
        svc._is_platform_staff = AsyncMock(return_value=True)
        svc._resolve_masked_setup_user_by_scan = AsyncMock(return_value=None)

        resolved = await AuthService._resolve_setup_link_user(
            svc, email="z***@n***.invalid", caller=caller
        )
        assert resolved is None
