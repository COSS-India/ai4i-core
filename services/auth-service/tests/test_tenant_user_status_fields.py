"""Tenant-user response builders expose the flags the frontend needs to render
the effective status through the tenant lifecycle cascade.

The tenant lifecycle never touches a user's own ``is_active``; it only toggles
``is_tenant_active`` (tenant lock) for every user. The frontend combines
``is_active`` + ``is_tenant_active`` + ``is_activated`` to show:
  * Active            → is_active=True,  is_tenant_active=True
  * Suspended (lock)  → is_tenant_active=False (tenant SUSPENDED/DEACTIVATED)
  * Suspended (admin) → is_active=False, is_activated=True
  * Pending Activation→ is_active=False, is_activated=False
So both flags must survive into the API payload.
"""

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


def _user(*, is_active: bool = True, is_tenant_active=None) -> User:
    return User(
        id=uuid4(),
        email="tenant-user@example.com",
        username=uuid4().hex[:12],
        tenant_id=1,
        is_active=is_active,
        is_tenant_active=is_tenant_active,
    )


class TestBuildTenantUserResponse:
    @pytest.mark.asyncio
    async def test_includes_tenant_lock_and_activated_flags(self) -> None:
        svc = _make_service()
        svc._roles.get_user_roles = AsyncMock(return_value=["USER"])
        svc._credentials.has_credentials = AsyncMock(return_value=True)

        out = await svc.build_tenant_user_response(
            _user(is_active=True, is_tenant_active=False)
        )

        assert out["is_active"] is True
        assert out["is_tenant_active"] is False
        assert out["is_activated"] is True

    @pytest.mark.asyncio
    async def test_pending_activation_user_not_activated(self) -> None:
        svc = _make_service()
        svc._roles.get_user_roles = AsyncMock(return_value=["USER"])
        svc._credentials.has_credentials = AsyncMock(return_value=False)

        out = await svc.build_tenant_user_response(
            _user(is_active=False, is_tenant_active=True)
        )

        assert out["is_active"] is False
        assert out["is_tenant_active"] is True
        assert out["is_activated"] is False


class TestBuildTenantUserResponses:
    @pytest.mark.asyncio
    async def test_list_carries_flags_per_user(self) -> None:
        svc = _make_service()
        activated = _user(is_active=True, is_tenant_active=False)
        pending = _user(is_active=False, is_tenant_active=False)

        svc._roles.get_roles_for_users = AsyncMock(
            return_value={activated.id: ["USER"], pending.id: ["USER"]}
        )
        # Only the first user has completed setup.
        svc._credentials.user_ids_with_credentials = AsyncMock(
            return_value={activated.id}
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
        svc._credentials.user_ids_with_credentials = AsyncMock()

        assert await svc.build_tenant_user_responses([]) == []
        svc._credentials.user_ids_with_credentials.assert_not_awaited()
