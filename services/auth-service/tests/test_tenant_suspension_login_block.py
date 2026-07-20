"""Unit tests: is_tenant_active=False blocks login and token refresh (AI4IDS-1761).

Setting a user's is_tenant_active to False via
PATCH /tenants/{tenant_id}/users/{user_id}/status must block both login and
token refresh. The is_active=False (user-level) check is independent and fires
first on the login path.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

# Placeholder credential for mocked-auth unit tests — not a real password.
_TEST_PASS = f"test-{uuid4().hex[:12]}!"

from app.core.constants import TokenType
from app.core.exceptions import AuthorizationError, UserInactiveError
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
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
    )


def _active_tenant() -> Tenant:
    return _tenant_with_status(TenantStatus.ACTIVE)


def _tenant_with_status(status: TenantStatus) -> Tenant:
    return Tenant(
        id=1,
        name="Acme",
        organisation="Acme",
        email="test-contact@example.invalid",
        status=status,
    )


def _tenant_user(*, is_tenant_active) -> User:
    return User(
        id=uuid4(),
        email="test-tenant-user@example.invalid",
        username=uuid4().hex[:12],
        tenant_id=1,
        is_active=True,
        is_tenant_active=is_tenant_active,
    )


def _system_user() -> User:
    return User(
        id=uuid4(),
        email="test-system-admin@example.invalid",
        username=uuid4().hex[:12],
        tenant_id=None,
        is_active=True,
    )


class TestAssertUserTenantActive:
    @pytest.mark.asyncio
    async def test_system_user_bypasses_check(self) -> None:
        """System users (tenant_id=None) are not subject to the tenant-active check."""
        svc = _make_auth_service()
        await svc._assert_user_tenant_active(_system_user())
        svc._tenants.get_by_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_blocked_when_is_tenant_active_false_and_tenant_active(self) -> None:
        """A per-user lock (tenant itself still ACTIVE) must raise TENANT_SUSPENDED."""
        svc = _make_auth_service()
        svc._tenants.get_by_id = AsyncMock(return_value=_active_tenant())
        with pytest.raises(AuthorizationError) as exc_info:
            await svc._assert_user_tenant_active(_tenant_user(is_tenant_active=False))
        assert exc_info.value.code == "TENANT_SUSPENDED"

    @pytest.mark.asyncio
    async def test_blocked_when_tenant_deactivated_reports_deactivated_message(self) -> None:
        """A tenant-wide DEACTIVATED lock must not be reported as 'suspended'."""
        svc = _make_auth_service()
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant_with_status(TenantStatus.DEACTIVATED))
        with pytest.raises(AuthorizationError) as exc_info:
            await svc._assert_user_tenant_active(_tenant_user(is_tenant_active=False))
        assert exc_info.value.code == "TENANT_INACTIVE"
        assert "deactivated" in exc_info.value.message.lower()
        assert "suspended" not in exc_info.value.message.lower()

    @pytest.mark.asyncio
    async def test_blocked_when_tenant_suspended_reports_suspended_message(self) -> None:
        svc = _make_auth_service()
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant_with_status(TenantStatus.SUSPENDED))
        with pytest.raises(AuthorizationError) as exc_info:
            await svc._assert_user_tenant_active(_tenant_user(is_tenant_active=False))
        assert exc_info.value.code == "TENANT_SUSPENDED"

    @pytest.mark.asyncio
    async def test_none_passes_through_to_tenant_status_check(self) -> None:
        """None (legacy default) is treated as allowed and falls through to the tenant-status check."""
        svc = _make_auth_service()
        svc._tenants.get_by_id = AsyncMock(return_value=_active_tenant())
        await svc._assert_user_tenant_active(_tenant_user(is_tenant_active=None))
        svc._tenants.get_by_id.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_true_passes_through_to_tenant_status_check(self) -> None:
        svc = _make_auth_service()
        svc._tenants.get_by_id = AsyncMock(return_value=_active_tenant())
        await svc._assert_user_tenant_active(_tenant_user(is_tenant_active=True))
        svc._tenants.get_by_id.assert_awaited_once()


class TestLoginBlockedByTenantSuspension:
    @pytest.mark.asyncio
    async def test_login_blocked_when_is_tenant_active_false(self) -> None:
        """A tenant user with is_tenant_active=False must not receive a JWT."""
        svc = _make_auth_service()
        svc._users.get_by_email = AsyncMock(return_value=_tenant_user(is_tenant_active=False))
        svc._tenants.get_by_id = AsyncMock(return_value=_active_tenant())

        with pytest.raises(AuthorizationError) as exc_info:
            await svc.login("test-tenant-user@example.invalid", _TEST_PASS)

        assert exc_info.value.code == "TENANT_SUSPENDED"
        svc._credentials.get_by_user_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_inactive_user_blocked_before_tenant_check(self) -> None:
        """is_active=False raises UserInactiveError independently of is_tenant_active."""
        svc = _make_auth_service()
        user = _tenant_user(is_tenant_active=True)
        user.is_active = False
        svc._users.get_by_email = AsyncMock(return_value=user)

        with pytest.raises(UserInactiveError):
            await svc.login("test-tenant-user@example.invalid", _TEST_PASS)

        svc._credentials.get_by_user_id.assert_not_called()


class TestRefreshBlockedByTenantSuspension:
    @pytest.mark.asyncio
    async def test_refresh_blocked_when_is_tenant_active_false(self) -> None:
        """Token refresh must be denied if the user's tenant access was suspended since login."""
        svc = _make_auth_service()
        user_id = uuid4()

        mock_payload = MagicMock()
        mock_payload.token_type = TokenType.REFRESH
        mock_payload.sub = str(user_id)
        svc._tokens.validate_token = MagicMock(return_value=mock_payload)
        svc._refresh_tokens.get_by_token = AsyncMock(return_value=MagicMock())
        svc._users.is_active = AsyncMock(return_value=True)
        svc._users.get_by_id = AsyncMock(return_value=_tenant_user(is_tenant_active=False))
        svc._tenants.get_by_id = AsyncMock(return_value=_active_tenant())

        with pytest.raises(AuthorizationError) as exc_info:
            await svc.refresh_token("fake-refresh-token")

        assert exc_info.value.code == "TENANT_SUSPENDED"
