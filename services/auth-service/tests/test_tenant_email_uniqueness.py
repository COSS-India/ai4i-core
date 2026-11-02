"""Unit tests for email uniqueness enforcement on tenant update.

A typed email change is only accepted while the tenant is PENDING (correcting
the contact before activation); other tenants change their contact via
``contact_user_id`` (see test_tenant_contact_change.py).
"""

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
    tenant_repo.commit = AsyncMock()
    tenant_repo.refresh = AsyncMock()
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
        credentials_repo=MagicMock(),
        token_service=MagicMock(),
        email_client=MagicMock(),
    )


def _tenant(id: int, email: str = "contact@tenant.com", status=TenantStatus.PENDING) -> Tenant:
    return Tenant(
        id=id,
        name="Contact",
        organisation=f"Org {id}",
        email=email,
        status=status,
    )


def _user(tenant_id=None, email: str = "test-oauth-user@example.invalid") -> User:
    return User(id=uuid4(), email=email, username=uuid4().hex[:12], tenant_id=tenant_id)


def _acting_admin() -> User:
    return User(id=uuid4(), email="test-acting-admin@example.invalid", username=uuid4().hex[:12])


def _with_contact(svc: TenantService, holder=None) -> None:
    """PENDING tenant 1's contact owns old@tenant.com; ``holder`` owns any other address."""
    contact = _user(tenant_id=1, email="old@tenant.com")
    svc._users.get_by_email = AsyncMock(
        side_effect=lambda e: contact if e == "old@tenant.com" else holder
    )


def _body(**fields) -> MagicMock:
    body = MagicMock()
    body.model_dump.return_value = fields
    return body


class TestUpdateTenantEmailUniqueness:
    @pytest.mark.asyncio
    async def test_update_to_another_tenants_email_raises_409(self) -> None:
        svc = _make_service()
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant(1, "old@tenant.com"))
        svc._tenants.get_by_email = AsyncMock(return_value=_tenant(2, "taken@other.com"))
        _with_contact(svc)

        with pytest.raises(HTTPException) as exc_info:
            await svc.update_tenant(_acting_admin(), 1, _body(email="taken@other.com"))

        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "DUPLICATE_TENANT_EMAIL"

    @pytest.mark.asyncio
    async def test_update_keeping_own_email_is_allowed(self) -> None:
        """Self-exclusion: patching other fields while retaining the same email must not 409."""
        svc = _make_service()
        own = _tenant(1, "own@tenant.com", status=TenantStatus.ACTIVE)
        svc._tenants.get_by_id = AsyncMock(return_value=own)
        # Repo returns the same tenant — existing.id == tenant_id → no conflict.
        svc._tenants.get_by_email = AsyncMock(return_value=own)

        await svc.update_tenant(
            _acting_admin(), 1, _body(email="own@tenant.com", contact_name="New Name")
        )

        svc._tenants.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_to_oauth_user_email_raises_409(self) -> None:
        """Email used by an OAuth user (no tenant) must be rejected."""
        svc = _make_service()
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant(1, "old@tenant.com"))
        # OAuth user has tenant_id=None, which != tenant_id 1
        _with_contact(svc, holder=_user(tenant_id=None))

        with pytest.raises(HTTPException) as exc_info:
            await svc.update_tenant(_acting_admin(), 1, _body(email="test-oauth-user@example.invalid"))

        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "DUPLICATE_EMAIL"

    @pytest.mark.asyncio
    async def test_update_to_email_of_user_in_another_tenant_raises_409(self) -> None:
        svc = _make_service()
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant(1, "old@tenant.com"))
        _with_contact(svc, holder=_user(tenant_id=99))

        with pytest.raises(HTTPException) as exc_info:
            await svc.update_tenant(_acting_admin(), 1, _body(email="other@tenant99.com"))

        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "DUPLICATE_EMAIL"

    @pytest.mark.asyncio
    async def test_update_to_email_of_own_tenant_user_raises_409(self) -> None:
        """The contact's users.email will follow — any other holder, even
        same-tenant, would break the users.email UNIQUE constraint."""
        svc = _make_service()
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant(1, "old@tenant.com"))
        _with_contact(svc, holder=_user(tenant_id=1, email="member@tenant.com"))

        with pytest.raises(HTTPException) as exc_info:
            await svc.update_tenant(_acting_admin(), 1, _body(email="member@tenant.com"))

        assert exc_info.value.code == "DUPLICATE_EMAIL"
        svc._tenants.update.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_case_variant_of_another_tenants_email_raises_409(self) -> None:
        """Case-insensitive: 'USER@TENANT.COM' must conflict with 'user@tenant.com'."""
        svc = _make_service()
        svc._tenants.get_by_id = AsyncMock(return_value=_tenant(1, "old@tenant.com"))
        svc._tenants.get_by_email = AsyncMock(return_value=_tenant(2, "user@tenant.com"))
        _with_contact(svc)

        with pytest.raises(HTTPException) as exc_info:
            await svc.update_tenant(_acting_admin(), 1, _body(email="USER@TENANT.COM"))

        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "DUPLICATE_TENANT_EMAIL"

    @pytest.mark.asyncio
    async def test_typed_email_change_on_active_tenant_rejected(self) -> None:
        """Non-PENDING tenants change their contact via contact_user_id only."""
        svc = _make_service()
        svc._tenants.get_by_id = AsyncMock(
            return_value=_tenant(1, "old@tenant.com", status=TenantStatus.ACTIVE)
        )

        with pytest.raises(HTTPException) as exc_info:
            await svc.update_tenant(_acting_admin(), 1, _body(email="new@tenant.com"))

        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "TENANT_EMAIL_EDIT_NOT_ALLOWED"
        svc._tenants.update.assert_not_awaited()
