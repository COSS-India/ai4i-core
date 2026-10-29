"""Self-registered users waiting on email verification are Pending Activation.

Regression: the tenant-user list derived ``is_activated`` from a credentials
row. /auth/register stores the password before the email is verified, so a
fresh self-signup came back ``is_active=False, is_activated=True`` and the UI
rendered it SUSPENDED (admin-created users have no password until setup, so
they correctly showed Pending Activation). ``is_activated`` now comes from
``users.activated_at``, stamped the first time the account becomes active.

The same mix-up let an admin-suspended self-registered user (inactive, has a
password) request a verification link and re-activate themselves.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.exceptions import TokenInvalidError
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.services.auth_service import AuthService
from app.services.tenant_service import TenantService

PASSWORD = "Str0ng!Passw0rd"


def _auth_svc() -> AuthService:
    svc = AuthService(
        user_repo=AsyncMock(),
        role_service=AsyncMock(),
        token_service=MagicMock(),
        credentials_repo=AsyncMock(),
        refresh_token_repo=AsyncMock(),
        verification_repo=AsyncMock(),
        tenant_repo=AsyncMock(),
        email_client=MagicMock(),
        cache_service=AsyncMock(),
    )
    svc._tokens.create_verify_token.return_value = "verify-token"
    return svc


def _tenant_svc() -> TenantService:
    svc = TenantService(
        tenant_repo=MagicMock(),
        user_repo=MagicMock(),
        role_service=MagicMock(),
        verification_repo=MagicMock(),
        credentials_repo=MagicMock(),
        token_service=MagicMock(),
        email_client=MagicMock(),
    )
    svc._roles.get_roles_for_users = AsyncMock(
        side_effect=lambda ids: {i: ["USER"] for i in ids}
    )
    return svc


async def _self_register(svc: AuthService) -> User:
    """Run the real /auth/register service path with a mocked DB."""
    svc._users.email_exists = AsyncMock(return_value=False)
    svc._users.list_usernames_in_collision_family = AsyncMock(return_value=[])
    # Stand in for the INSERT flush, which is what assigns the primary key.
    svc._users.create = AsyncMock(side_effect=lambda u: setattr(u, "id", uuid4()))
    return await svc.register(
        email="arunagiriperumal+example1@example.invalid",
        password=PASSWORD,
        confirm_password=PASSWORD,
    )


def _suspended_self_signup() -> User:
    return User(
        id=uuid4(),
        email="suspended@example.invalid",
        username="suspended",
        tenant_id=1,
        is_active=False,
        activated_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
    )


class TestSelfSignupListedAsPendingActivation:
    @pytest.mark.asyncio
    async def test_unverified_self_signup_is_not_activated(self) -> None:
        auth = _auth_svc()
        user = await _self_register(auth)

        # register() stored a password: the old credentials-based check
        # would have reported this user as activated.
        auth._credentials.create.assert_awaited_once()

        row = await _tenant_svc().build_tenant_user_response(user)

        # Frontend: !is_active && !is_activated → Pending Activation.
        assert row["is_active"] is False
        assert row["is_activated"] is False

    @pytest.mark.asyncio
    async def test_verified_then_suspended_self_signup_is_suspended(self) -> None:
        auth = _auth_svc()
        user = await _self_register(auth)
        auth._resolve_verified_token = AsyncMock(return_value=(MagicMock(), user))
        auth._assert_user_tenant_onboarding = AsyncMock()

        await auth.verify_email_token("verify-token")
        assert user.is_active is True
        assert user.activated_at is not None

        user.is_active = False  # admin Suspend
        row = await _tenant_svc().build_tenant_user_response(user)

        # Frontend: !is_active && is_activated → Suspended.
        assert row["is_active"] is False
        assert row["is_activated"] is True


class TestSuspendedSelfSignupCannotReactivate:
    @pytest.mark.asyncio
    async def test_resend_verification_is_a_no_op(self) -> None:
        auth = _auth_svc()
        user = _suspended_self_signup()
        auth._users.get_by_email = AsyncMock(return_value=user)
        auth._credentials.get_by_user_id = AsyncMock(return_value=MagicMock())

        await auth.resend_verification(user.email, background_tasks=MagicMock())

        auth._tokens.create_verify_token.assert_not_called()
        auth._users.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_resend_verification_still_serves_unverified_signup(self) -> None:
        auth = _auth_svc()
        user = await _self_register(auth)
        auth._tokens.create_verify_token.reset_mock()
        auth._users.commit.reset_mock()
        auth._users.get_by_email = AsyncMock(return_value=user)
        auth._credentials.get_by_user_id = AsyncMock(return_value=MagicMock())

        await auth.resend_verification(user.email, background_tasks=MagicMock())

        auth._tokens.create_verify_token.assert_called_once()
        auth._users.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_verify_link_does_not_reactivate(self) -> None:
        auth = _auth_svc()
        user = _suspended_self_signup()
        auth._resolve_verified_token = AsyncMock(return_value=(MagicMock(), user))

        with pytest.raises(TokenInvalidError):
            await auth.verify_email_token("verify-token")

        assert user.is_active is False
        auth._users.commit.assert_not_awaited()


class TestAdminActivationStampsActivatedAt:
    def _svc(self, target: User) -> TenantService:
        svc = _tenant_svc()
        svc.enforce_scope = AsyncMock()
        svc._deny_moderator = AsyncMock()
        svc._tenants.get_by_id = AsyncMock(
            return_value=Tenant(id=1, name="Acme", organisation="Acme",
                                email="c@example.invalid", status=TenantStatus.ACTIVE)
        )
        svc._load_tenant_user_or_404 = AsyncMock(return_value=target)
        svc._users.update = AsyncMock()
        svc._users.save_and_refresh = AsyncMock()
        return svc

    @pytest.mark.asyncio
    async def test_activating_never_activated_user_stamps_it(self) -> None:
        target = User(id=uuid4(), email="p@example.invalid", username="p",
                      tenant_id=1, is_active=False)
        svc = self._svc(target)
        body = MagicMock(is_active=True)

        await svc.update_tenant_user_status(MagicMock(id=uuid4()), 1, target.id, body)

        payload = svc._users.update.await_args.args[1]
        assert payload["is_active"] is True
        assert payload["activated_at"] is not None

    @pytest.mark.asyncio
    async def test_reactivating_keeps_original_timestamp(self) -> None:
        target = _suspended_self_signup()
        svc = self._svc(target)
        body = MagicMock(is_active=True)

        await svc.update_tenant_user_status(MagicMock(id=uuid4()), 1, target.id, body)

        assert "activated_at" not in svc._users.update.await_args.args[1]


class TestMarkActivated:
    def test_first_activation_stamps_and_later_ones_keep_it(self) -> None:
        user = User(id=uuid4(), email="u@example.invalid", username="u", is_active=False)

        user.mark_activated()
        first = user.activated_at
        assert user.is_active is True and first is not None

        user.is_active = False
        user.mark_activated()
        assert user.activated_at == first
