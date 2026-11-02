"""Tenant-user response builders expose the flags the frontend needs to render
the effective status through the tenant lifecycle cascade.

The tenant lifecycle never touches a user's own ``is_active``; it only toggles
``is_tenant_active`` (tenant lock) for every user. The frontend combines
``is_active`` + ``is_tenant_active`` + ``is_activated`` to show:
  * Active            → is_active=True,  is_tenant_active=True
  * Suspended (lock)  → is_tenant_active=False (tenant SUSPENDED/DEACTIVATED)
  * Suspended (admin) → is_active=False, is_activated=True
  * Pending Activation→ is_active=False, is_activated=False
So both flags must survive into the API payload. ``is_activated`` comes from
``users.activated_at``, not from a credentials row.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models.user import User
from app.services.tenant_service import TenantService


def _make_service() -> TenantService:
    return TenantService(
        tenant_repo=MagicMock(),
        user_repo=MagicMock(),
        role_service=MagicMock(),
        verification_repo=MagicMock(),
        credentials_repo=MagicMock(),
        token_service=MagicMock(),
        email_client=MagicMock(),
    )


_ACTIVATED_AT = datetime(2026, 10, 1, tzinfo=timezone.utc)


def _user(*, is_active: bool = True, is_tenant_active=None, activated: bool = True) -> User:
    return User(
        id=uuid4(),
        email="tenant-user@example.com",
        username=uuid4().hex[:12],
        tenant_id=1,
        is_active=is_active,
        is_tenant_active=is_tenant_active,
        activated_at=_ACTIVATED_AT if activated else None,
    )


class TestBuildTenantUserResponse:
    @pytest.mark.asyncio
    async def test_includes_tenant_lock_and_activated_flags(self) -> None:
        svc = _make_service()
        user = _user(is_active=True, is_tenant_active=False)
        svc._roles.get_roles_for_users = AsyncMock(return_value={user.id: ["USER"]})

        out = await svc.build_tenant_user_response(user)

        assert out["is_active"] is True
        assert out["is_tenant_active"] is False
        assert out["is_activated"] is True

    @pytest.mark.asyncio
    async def test_pending_activation_user_not_activated(self) -> None:
        svc = _make_service()
        user = _user(is_active=False, is_tenant_active=True, activated=False)
        svc._roles.get_roles_for_users = AsyncMock(return_value={user.id: ["USER"]})

        out = await svc.build_tenant_user_response(user)

        assert out["is_active"] is False
        assert out["is_tenant_active"] is True
        assert out["is_activated"] is False


class TestBuildTenantUserResponses:
    @pytest.mark.asyncio
    async def test_list_carries_flags_per_user(self) -> None:
        svc = _make_service()
        activated = _user(is_active=True, is_tenant_active=False)
        pending = _user(is_active=False, is_tenant_active=False, activated=False)

        svc._roles.get_roles_for_users = AsyncMock(
            return_value={activated.id: ["USER"], pending.id: ["USER"]}
        )

        out = await svc.build_tenant_user_responses([activated, pending])

        by_id = {row["user_id"]: row for row in out}
        assert by_id[str(activated.id)]["is_tenant_active"] is False
        assert by_id[str(activated.id)]["is_activated"] is True
        assert by_id[str(pending.id)]["is_tenant_active"] is False
        assert by_id[str(pending.id)]["is_activated"] is False

    @pytest.mark.asyncio
    async def test_empty_list_short_circuits(self) -> None:
        svc = _make_service()
        svc._roles.get_roles_for_users = AsyncMock()

        assert await svc.build_tenant_user_responses([]) == []
        svc._roles.get_roles_for_users.assert_not_awaited()


class TestActivationNeverReadFromCredentials:
    """A merge with #1858 resurrected ``user_ids_with_credentials`` (without
    its ``Iterable`` import), which both broke the module import and brought
    back the "has a password ⇒ activated" lookup behind the SUSPENDED bug."""

    def test_repository_has_no_credentials_based_activation_lookup(self) -> None:
        from app.repositories.credentials_repository import CredentialsRepository

        assert not hasattr(CredentialsRepository, "user_ids_with_credentials")

    @pytest.mark.asyncio
    async def test_unverified_self_signup_with_password_is_not_activated(self) -> None:
        from app.repositories.credentials_repository import CredentialsRepository

        svc = _make_service()
        # spec'd mock: any credentials lookup the builder makes must exist on
        # the real repository, and none of them may decide is_activated.
        svc._credentials = MagicMock(spec=CredentialsRepository)
        svc._credentials.get_by_user_id = AsyncMock(return_value=MagicMock())
        user = _user(is_active=False, is_tenant_active=True, activated=False)
        svc._roles.get_roles_for_users = AsyncMock(return_value={user.id: ["USER"]})

        out = await svc.build_tenant_user_response(user)

        assert out["is_active"] is False
        assert out["is_activated"] is False
