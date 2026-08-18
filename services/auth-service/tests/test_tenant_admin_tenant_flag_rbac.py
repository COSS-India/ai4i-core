"""Unit tests: PATCH tenant-user status accepts only ``is_active``.

``is_tenant_active`` is no longer part of this endpoint's contract — it is
managed exclusively by the tenant status API (PATCH /tenants/{id}/status),
which syncs the flag for all tenant users on SUSPENDED/DEACTIVATED/ACTIVE.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.config import RoleName
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.schemas.tenant import TenantUserStatusUpdate
from app.services.tenant_service import TenantService


def _make_service() -> TenantService:
    tenant_repo = MagicMock()
    user_repo = MagicMock()
    user_repo.save_and_refresh = AsyncMock()
    role_service = MagicMock()
    role_service.get_user_roles = AsyncMock(return_value=[])
    return TenantService(
        tenant_repo=tenant_repo,
        user_repo=user_repo,
        role_service=role_service,
        verification_repo=MagicMock(),
        credentials_repo=MagicMock(),
        token_service=MagicMock(),
        email_client=MagicMock(),
    )


def _tenant_admin() -> User:
    return User(id=uuid4(), email="test-tenant-admin@example.invalid", username=uuid4().hex[:12], tenant_id=1)


def _active_tenant() -> Tenant:
    return Tenant(id=1, name="Acme", organisation="Acme", email="test-contact@example.invalid",
                  status=TenantStatus.ACTIVE)


def _target_user() -> User:
    return User(id=uuid4(), email="test-target-user@example.invalid", username=uuid4().hex[:12],
                tenant_id=1, is_active=True, is_tenant_active=True)


class TestTenantUserStatusUpdateSchema:
    def test_is_active_is_required(self) -> None:
        with pytest.raises(ValidationError):
            TenantUserStatusUpdate()

    def test_is_tenant_active_is_not_a_field(self) -> None:
        body = TenantUserStatusUpdate.model_validate(
            {"is_active": True, "is_tenant_active": False}
        )
        assert "is_tenant_active" not in body.model_fields_set
        assert not hasattr(body, "is_tenant_active")

    def test_is_tenant_active_alone_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TenantUserStatusUpdate.model_validate({"is_tenant_active": False})


class TestUpdateTenantUserStatus:
    @pytest.mark.asyncio
    async def test_updates_only_is_active(self) -> None:
        target = _target_user()
        svc = _make_service()
        svc.enforce_scope = AsyncMock()
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.TENANT_ADMIN.value])
        svc._tenants.get_by_id = AsyncMock(return_value=_active_tenant())
        svc._users.get_by_id = AsyncMock(return_value=target)
        svc._users.update = AsyncMock()
        svc._users.save_and_refresh = AsyncMock()

        caller = _tenant_admin()
        body = TenantUserStatusUpdate(is_active=False)
        await svc.update_tenant_user_status(caller, 1, target.id, body)

        svc._users.update.assert_awaited_once_with(
            target, {"is_active": False, "updated_by": caller.id}
        )
