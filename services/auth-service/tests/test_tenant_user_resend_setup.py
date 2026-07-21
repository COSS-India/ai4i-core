"""Resend set-password link for a tenant user.

Tenant users are provisioned passwordless (a SETUP / set-password email, not an
email-verification email), so onboarding resends must reissue a SETUP token via
the tenant-scoped endpoint. ``/auth/resend-verification`` no-ops for them.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import ValidationError
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.services.tenant_service import TenantService


def _service() -> TenantService:
    svc = TenantService(
        tenant_repo=MagicMock(),
        user_repo=MagicMock(),
        role_service=MagicMock(),
        verification_repo=MagicMock(),
        credentials_repo=MagicMock(),
        token_service=MagicMock(),
        email_client=MagicMock(),
    )
    # Caller is a platform admin → passes enforce_scope + _deny_moderator.
    svc._roles.get_user_roles = AsyncMock(return_value=["ADMIN"])
    svc._verifications.deactivate_all_for_user = AsyncMock()
    svc._verifications.create = AsyncMock()
    svc._users.commit = AsyncMock()
    svc._tokens.create_setup_token = MagicMock(return_value="setup-token")
    return svc


def _tenant() -> Tenant:
    return Tenant(
        id=1,
        name="Acme",
        organisation="Acme",
        email="contact@example.com",
        status=TenantStatus.ACTIVE,
    )


def _tenant_user() -> User:
    return User(
        id=uuid4(),
        email="new-user@example.com",
        username=uuid4().hex[:12],
        tenant_id=1,
        is_active=False,
    )


def _admin() -> User:
    return User(id=uuid4(), email="admin@example.com", username="admin", tenant_id=None)


class TestResendTenantUserSetupLink:
    @pytest.mark.asyncio
    async def test_reissues_setup_token_for_unactivated_user(self) -> None:
        svc = _service()
        target = _tenant_user()
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant())
        svc._users.get_by_id = AsyncMock(return_value=target)
        # No credentials yet → user has not completed setup.
        svc._credentials.get_by_user_id = AsyncMock(return_value=None)

        await svc.resend_tenant_user_setup_link(
            _admin(), 1, target.id, MagicMock()
        )

        svc._tokens.create_setup_token.assert_called_once()
        svc._verifications.deactivate_all_for_user.assert_awaited_once()
        svc._users.commit.assert_awaited_once()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "tenant_status", [TenantStatus.SUSPENDED, TenantStatus.DEACTIVATED, TenantStatus.PENDING]
    )
    async def test_rejects_when_tenant_not_active(self, tenant_status) -> None:
        svc = _service()
        target = _tenant_user()
        tenant = _tenant()
        tenant.status = tenant_status
        svc._tenants.get_by_id = AsyncMock(return_value=tenant)
        svc._users.get_by_id = AsyncMock(return_value=target)
        svc._credentials.get_by_user_id = AsyncMock(return_value=None)

        with pytest.raises(ValidationError) as exc:
            await svc.resend_tenant_user_setup_link(
                _admin(), 1, target.id, MagicMock()
            )

        assert exc.value.code == "TENANT_NOT_ACTIVE"
        svc._tokens.create_setup_token.assert_not_called()
        svc._users.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rejects_when_user_tenant_locked(self) -> None:
        svc = _service()
        target = _tenant_user()
        target.is_tenant_active = False
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant())
        svc._users.get_by_id = AsyncMock(return_value=target)
        svc._credentials.get_by_user_id = AsyncMock(return_value=None)

        with pytest.raises(ValidationError) as exc:
            await svc.resend_tenant_user_setup_link(
                _admin(), 1, target.id, MagicMock()
            )

        assert exc.value.code == "USER_SUSPENDED"
        svc._tokens.create_setup_token.assert_not_called()
        svc._users.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rejects_already_activated_user(self) -> None:
        svc = _service()
        target = _tenant_user()
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant())
        svc._users.get_by_id = AsyncMock(return_value=target)
        # Credentials exist → setup already complete.
        svc._credentials.get_by_user_id = AsyncMock(return_value=MagicMock())

        with pytest.raises(ValidationError) as exc:
            await svc.resend_tenant_user_setup_link(
                _admin(), 1, target.id, MagicMock()
            )

        assert exc.value.code == "USER_ALREADY_ACTIVATED"
        svc._users.commit.assert_not_awaited()
