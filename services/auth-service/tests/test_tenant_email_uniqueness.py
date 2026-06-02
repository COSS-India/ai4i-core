"""Unit tests for email uniqueness enforcement on tenant update."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.services.tenant_service import TenantService


def _make_service() -> TenantService:
    tenant_repo = MagicMock()
    tenant_repo.get_by_id = AsyncMock()
    tenant_repo.get_by_email = AsyncMock(return_value=None)
    tenant_repo.get_by_organisation = AsyncMock(return_value=None)
    tenant_repo.update = AsyncMock()
    tenant_repo.save_and_refresh = AsyncMock()
    user_repo = MagicMock()
    user_repo.get_by_email = AsyncMock(return_value=None)
    # update_tenant calls enforce_scope first; act as a system admin so these
    # tests isolate the email-uniqueness logic (scope is covered in
    # test_tenant_update_scope.py).
    role_service = MagicMock()
    role_service.get_user_roles = AsyncMock(return_value=["ADMIN"])
    return TenantService(
        tenant_repo=tenant_repo,
        user_repo=user_repo,
        role_service=role_service,
        verification_repo=MagicMock(),
        token_service=MagicMock(),
        email_client=MagicMock(),
    )


def _tenant(id: int, email: str = "contact@tenant.com") -> Tenant:
    return Tenant(
        id=id,
        name="Contact",
        organisation=f"Org {id}",
        email=email,
        status=TenantStatus.ACTIVE,
    )


def _user(tenant_id=None) -> User:
    return User(id=uuid4(), email="oauth@gmail.com", username="oauthuser", tenant_id=tenant_id)


class TestUpdateTenantEmailUniqueness:
    @pytest.mark.asyncio
    async def test_update_to_another_tenants_email_raises_409(self) -> None:
        svc = _make_service()
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant(1, "old@tenant.com"))
        svc._tenants.get_by_email = AsyncMock(return_value=_tenant(2, "taken@other.com"))

        body = MagicMock()
        body.model_dump.return_value = {"email": "taken@other.com"}

        with pytest.raises(HTTPException) as exc_info:
            await svc.update_tenant(User(id=uuid4(), email="a@b.com", username="u"), 1, body)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "DUPLICATE_TENANT_EMAIL"

    @pytest.mark.asyncio
    async def test_update_keeping_own_email_is_allowed(self) -> None:
        """Self-exclusion: patching other fields while retaining the same email must not 409."""
        svc = _make_service()
        own = _tenant(1, "own@tenant.com")
        svc._tenants.get_by_id = AsyncMock(return_value=own)
        # Repo returns the same tenant — existing.id == tenant_id → no conflict.
        svc._tenants.get_by_email = AsyncMock(return_value=own)

        body = MagicMock()
        body.model_dump.return_value = {"email": "own@tenant.com", "contact_name": "New Name"}

        await svc.update_tenant(User(id=uuid4(), email="a@b.com", username="u"), 1, body)

        svc._tenants.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_to_oauth_user_email_raises_409(self) -> None:
        """Email used by an OAuth user (no tenant) must be rejected."""
        svc = _make_service()
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant(1, "old@tenant.com"))
        svc._tenants.get_by_email = AsyncMock(return_value=None)
        # OAuth user has tenant_id=None, which != tenant_id 1
        svc._users.get_by_email = AsyncMock(return_value=_user(tenant_id=None))

        body = MagicMock()
        body.model_dump.return_value = {"email": "oauth@gmail.com"}

        with pytest.raises(HTTPException) as exc_info:
            await svc.update_tenant(User(id=uuid4(), email="a@b.com", username="u"), 1, body)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "DUPLICATE_EMAIL"

    @pytest.mark.asyncio
    async def test_update_to_email_of_user_in_another_tenant_raises_409(self) -> None:
        svc = _make_service()
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant(1, "old@tenant.com"))
        svc._tenants.get_by_email = AsyncMock(return_value=None)
        svc._users.get_by_email = AsyncMock(return_value=_user(tenant_id=99))

        body = MagicMock()
        body.model_dump.return_value = {"email": "other@tenant99.com"}

        with pytest.raises(HTTPException) as exc_info:
            await svc.update_tenant(User(id=uuid4(), email="a@b.com", username="u"), 1, body)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "DUPLICATE_EMAIL"

    @pytest.mark.asyncio
    async def test_update_to_email_of_own_tenant_user_is_allowed(self) -> None:
        """Email belonging to a user within the same tenant must not be rejected."""
        svc = _make_service()
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant(1, "old@tenant.com"))
        svc._tenants.get_by_email = AsyncMock(return_value=None)
        # User belongs to same tenant (tenant_id=1 == tenant_id being updated)
        svc._users.get_by_email = AsyncMock(return_value=_user(tenant_id=1))

        body = MagicMock()
        body.model_dump.return_value = {"email": "admin@tenant.com"}

        await svc.update_tenant(User(id=uuid4(), email="a@b.com", username="u"), 1, body)

        svc._tenants.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_case_variant_of_another_tenants_email_raises_409(self) -> None:
        """Case-insensitive: 'USER@TENANT.COM' must conflict with 'user@tenant.com'."""
        svc = _make_service()
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant(1, "old@tenant.com"))
        svc._tenants.get_by_email = AsyncMock(return_value=_tenant(2, "user@tenant.com"))

        body = MagicMock()
        body.model_dump.return_value = {"email": "USER@TENANT.COM"}

        with pytest.raises(HTTPException) as exc_info:
            await svc.update_tenant(User(id=uuid4(), email="a@b.com", username="u"), 1, body)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "DUPLICATE_TENANT_EMAIL"
