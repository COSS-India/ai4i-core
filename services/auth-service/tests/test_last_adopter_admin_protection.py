"""Unit tests: suspend/delete is rejected for the sole active Adopter Admin
(MODERATOR) in the Default Organisation, and allowed once another exists.
"""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.config import settings
from app.core.constants import RoleName
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.services.tenant_service import TenantService


def _make_service() -> TenantService:
    tenant_repo = MagicMock()
    tenant_repo.get_by_id = AsyncMock()
    tenant_repo._db = MagicMock()
    tenant_repo._db.execute = AsyncMock()
    user_repo = MagicMock()
    user_repo.save_and_refresh = AsyncMock()
    user_repo.update = AsyncMock()
    user_repo.commit = AsyncMock()
    role_service = MagicMock()
    role_service.get_user_roles = AsyncMock(return_value=[])
    role_service.count_moderators_in_tenant = AsyncMock(return_value=1)
    return TenantService(
        tenant_repo=tenant_repo,
        user_repo=user_repo,
        role_service=role_service,
        verification_repo=MagicMock(),
        credentials_repo=MagicMock(),
        token_service=MagicMock(),
        email_client=MagicMock(),
    )


def _admin() -> User:
    return User(id=uuid4(), email="test-admin@example.invalid", username=uuid4().hex[:12])


def _adopter_admin() -> User:
    return User(id=uuid4(), email="test-adopter-admin@example.invalid", username=uuid4().hex[:12], tenant_id=1)


def _default_tenant() -> Tenant:
    return Tenant(
        id=1,
        name="Default Admin",
        organisation=settings.default_tenant_org,
        email="test-default-contact@example.invalid",
        status=TenantStatus.ACTIVE,
    )


def _other_tenant() -> Tenant:
    return Tenant(id=2, name="Acme", organisation="Acme", email="test-acme@example.invalid",
                  status=TenantStatus.ACTIVE)


class TestSuspendSoleAdopterAdmin:
    @pytest.mark.asyncio
    async def test_suspend_rejected_when_sole_adopter_admin(self) -> None:
        svc = _make_service()
        svc.enforce_scope = AsyncMock()
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.ADMIN.value])
        svc._tenants.get_by_id = AsyncMock(return_value=_default_tenant())
        target = _adopter_admin()
        svc._load_tenant_user_or_404 = AsyncMock(return_value=target)
        svc._roles.count_moderators_in_tenant = AsyncMock(return_value=1)

        async def get_user_roles(user_id):
            return [RoleName.MODERATOR.value] if user_id == target.id else [RoleName.ADMIN.value]

        svc._roles.get_user_roles = AsyncMock(side_effect=get_user_roles)

        body = MagicMock()
        body.is_active = False

        with pytest.raises(HTTPException) as exc_info:
            await svc.update_tenant_user_status(_admin(), 1, target.id, body)

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["code"] == "LAST_ADOPTER_ADMIN"
        assert exc_info.value.detail["message"] == (
            "Cannot suspend the only Admin in the Default Organization. "
            "Promote another user to Admin first."
        )
        svc._users.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_suspend_allowed_when_another_adopter_admin_exists(self) -> None:
        svc = _make_service()
        svc.enforce_scope = AsyncMock()
        svc._tenants.get_by_id = AsyncMock(return_value=_default_tenant())
        target = _adopter_admin()
        svc._load_tenant_user_or_404 = AsyncMock(return_value=target)
        svc._roles.count_moderators_in_tenant = AsyncMock(return_value=2)

        async def get_user_roles(user_id):
            return [RoleName.MODERATOR.value] if user_id == target.id else [RoleName.ADMIN.value]

        svc._roles.get_user_roles = AsyncMock(side_effect=get_user_roles)

        body = MagicMock()
        body.is_active = False

        await svc.update_tenant_user_status(_admin(), 1, target.id, body)

        svc._users.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_suspend_not_blocked_outside_default_organisation(self) -> None:
        svc = _make_service()
        svc.enforce_scope = AsyncMock()
        svc._tenants.get_by_id = AsyncMock(return_value=_other_tenant())
        target = _adopter_admin()
        svc._load_tenant_user_or_404 = AsyncMock(return_value=target)
        svc._roles.count_moderators_in_tenant = AsyncMock(return_value=1)

        async def get_user_roles(user_id):
            return [RoleName.MODERATOR.value] if user_id == target.id else [RoleName.ADMIN.value]

        svc._roles.get_user_roles = AsyncMock(side_effect=get_user_roles)

        body = MagicMock()
        body.is_active = False

        await svc.update_tenant_user_status(_admin(), 2, target.id, body)

        svc._users.update.assert_awaited_once()
        svc._roles.count_moderators_in_tenant.assert_not_called()


class TestDeleteSoleAdopterAdmin:
    @pytest.mark.asyncio
    async def test_delete_rejected_when_sole_adopter_admin(self) -> None:
        svc = _make_service()
        svc.enforce_scope = AsyncMock()
        svc._tenants.get_by_id = AsyncMock(return_value=_default_tenant())
        target = _adopter_admin()
        svc._load_tenant_user_or_404 = AsyncMock(return_value=target)
        svc._roles.count_moderators_in_tenant = AsyncMock(return_value=1)

        async def get_user_roles(user_id):
            return [RoleName.MODERATOR.value] if user_id == target.id else [RoleName.ADMIN.value]

        svc._roles.get_user_roles = AsyncMock(side_effect=get_user_roles)

        with pytest.raises(HTTPException) as exc_info:
            await svc.delete_tenant_user(_admin(), 1, target.id, MagicMock())

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["code"] == "LAST_ADOPTER_ADMIN"
        assert exc_info.value.detail["message"] == (
            "Cannot delete the only Admin in the Default Organization. "
            "Promote another user to Admin first."
        )
        svc._users.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_allowed_when_another_adopter_admin_exists(self) -> None:
        svc = _make_service()
        svc.enforce_scope = AsyncMock()
        svc._tenants.get_by_id = AsyncMock(return_value=_default_tenant())
        target = _adopter_admin()
        svc._load_tenant_user_or_404 = AsyncMock(return_value=target)
        svc._roles.count_moderators_in_tenant = AsyncMock(return_value=2)
        svc._users.update = AsyncMock()
        svc._users.commit = AsyncMock()

        async def get_user_roles(user_id):
            return [RoleName.MODERATOR.value] if user_id == target.id else [RoleName.ADMIN.value]

        svc._roles.get_user_roles = AsyncMock(side_effect=get_user_roles)

        await svc.delete_tenant_user(_admin(), 1, target.id, MagicMock())

        svc._users.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_not_blocked_when_target_is_not_adopter_admin(self) -> None:
        svc = _make_service()
        svc.enforce_scope = AsyncMock()
        svc._tenants.get_by_id = AsyncMock(return_value=_default_tenant())
        target = _adopter_admin()
        svc._load_tenant_user_or_404 = AsyncMock(return_value=target)
        svc._roles.get_user_roles = AsyncMock(return_value=[RoleName.USER.value])
        svc._roles.count_moderators_in_tenant = AsyncMock(return_value=0)
        svc._users.update = AsyncMock()
        svc._users.commit = AsyncMock()

        await svc.delete_tenant_user(_admin(), 1, target.id, MagicMock())

        svc._users.update.assert_awaited_once()
        svc._roles.count_moderators_in_tenant.assert_not_called()
