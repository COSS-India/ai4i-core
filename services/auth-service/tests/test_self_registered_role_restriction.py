"""Self-registered users (email/password signup, Google OAuth) can only hold
the USER role. Any attempt to grant them another role — via
``POST /auth/roles/assign`` or the tenant-user PATCH — is rejected with 422
``SELF_REGISTERED_ROLE_RESTRICTED``. Admin-provisioned users
(``creation_type=tenant``) are unaffected."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.constants import RoleName
from app.core.exceptions import AppError
from app.models.tenant import Tenant, TenantStatus
from app.models.user import CreationType, User
from app.schemas.tenant import TenantUserRole, TenantUserUpdate
from app.services.role_service import RoleService
from app.services.tenant_service import TenantService

SELF_REGISTERED = [CreationType.DEFAULT, CreationType.GOOGLE, None]
NON_USER_ROLES = [RoleName.ADMIN, RoleName.MODERATOR, RoleName.TENANT_ADMIN, RoleName.GUEST]


def _user(creation_type, tenant_id: int = 1) -> User:
    return User(
        id=uuid4(),
        email="test-user@example.invalid",
        username=uuid4().hex[:12],
        tenant_id=tenant_id,
        is_active=True,
        creation_type=creation_type,
    )


def _make_role_service(target: User | None) -> RoleService:
    role_repo = MagicMock()
    role_repo._db = MagicMock()
    role_repo._db.execute = AsyncMock()
    role_repo.commit = AsyncMock()
    role_repo.get_role_by_name = AsyncMock(
        side_effect=lambda name: MagicMock(id=7, name=name)
    )
    role_repo.get_user_role_record = AsyncMock(return_value=None)
    role_repo.assign_role = AsyncMock()
    user_repo = MagicMock()
    user_repo.get_by_id = AsyncMock(return_value=target)
    tenant_repo = MagicMock()
    tenant_repo.get_by_id = AsyncMock(return_value=None)
    return RoleService(role_repo, user_repo, tenant_repo)


class TestRoleServiceAssignRole:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("creation_type", SELF_REGISTERED)
    @pytest.mark.parametrize("role", NON_USER_ROLES)
    async def test_non_user_role_rejected_for_self_registered(self, creation_type, role) -> None:
        target = _user(creation_type)
        svc = _make_role_service(target)

        with pytest.raises(AppError) as exc_info:
            await svc.assign_role(target.id, role, created_by=uuid4())

        assert exc_info.value.status_code == 422
        assert exc_info.value.code == "SELF_REGISTERED_ROLE_RESTRICTED"
        svc._roles.assign_role.assert_not_awaited()
        svc._roles.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_admin_rejection_happens_before_roster_lock(self) -> None:
        target = _user(CreationType.GOOGLE)
        svc = _make_role_service(target)

        with pytest.raises(AppError):
            await svc.assign_role(target.id, RoleName.ADMIN)

        svc._roles._db.execute.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("creation_type", SELF_REGISTERED)
    async def test_user_role_still_assignable_to_self_registered(self, creation_type) -> None:
        # Registration and OAuth signup assign USER through this same method.
        target = _user(creation_type)
        svc = _make_role_service(target)

        await svc.assign_role(target.id, RoleName.USER)

        svc._roles.assign_role.assert_awaited_once()
        svc._users.get_by_id.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("role", NON_USER_ROLES)
    async def test_tenant_created_user_can_receive_any_role(self, role) -> None:
        target = _user(CreationType.TENANT)
        svc = _make_role_service(target)

        await svc.assign_role(target.id, role)

        svc._roles.assign_role.assert_awaited_once()


class TestAssignRoleRoute:
    """The exact reported scenario over HTTP: a platform ADMIN tries to make a
    Google-signup user a MODERATOR via ``POST /auth/roles/assign``."""

    @staticmethod
    def _client(target: User):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.core.database import get_db
        from app.dependencies.auth import get_current_user
        from app.dependencies.services import get_role_service
        from app.routes.role import router

        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        svc = _make_role_service(target)
        caller = _user(CreationType.TENANT)
        app.dependency_overrides[get_current_user] = lambda: caller
        app.dependency_overrides[get_db] = lambda: MagicMock()
        app.dependency_overrides[get_role_service] = lambda: svc
        return TestClient(app), svc

    @pytest.mark.parametrize("creation_type", [CreationType.GOOGLE, CreationType.DEFAULT])
    def test_admin_cannot_make_self_registered_user_moderator(self, creation_type) -> None:
        target = _user(creation_type)
        client, svc = self._client(target)
        caller_roles = MagicMock()
        caller_roles.return_value.get_user_roles = AsyncMock(return_value=[RoleName.ADMIN.value])

        with patch("app.dependencies.permissions.RoleRepository", caller_roles), \
                patch("app.dependencies.tenant_scope.RoleRepository", caller_roles):
            resp = client.post(
                "/api/v1/auth/roles/assign",
                json={"user_id": str(target.id), "role_name": RoleName.MODERATOR.value},
            )

        assert resp.status_code == 422
        assert "self-registered users can only hold the 'USER' role" in resp.json()["detail"]
        svc._roles.assign_role.assert_not_awaited()

    def test_admin_can_make_tenant_created_user_moderator(self) -> None:
        target = _user(CreationType.TENANT)
        client, svc = self._client(target)
        caller_roles = MagicMock()
        caller_roles.return_value.get_user_roles = AsyncMock(return_value=[RoleName.ADMIN.value])

        with patch("app.dependencies.permissions.RoleRepository", caller_roles), \
                patch("app.dependencies.tenant_scope.RoleRepository", caller_roles):
            resp = client.post(
                "/api/v1/auth/roles/assign",
                json={"user_id": str(target.id), "role_name": RoleName.MODERATOR.value},
            )

        assert resp.status_code == 200
        svc._roles.assign_role.assert_awaited_once()


class TestUpdateTenantUserRole:
    """Second grant path: PATCH /tenants/{id}/users/{uid} with ``role``. A
    self-registered user can sit in a real tenant (registration accepts a
    tenant_id), so TENANT_ADMIN is otherwise reachable there."""

    @staticmethod
    def _service(target: User) -> TenantService:
        role_service = _make_role_service(target)
        user_repo = MagicMock()
        user_repo.update = AsyncMock()
        user_repo.save_and_refresh = AsyncMock()
        svc = TenantService(
            tenant_repo=MagicMock(),
            user_repo=user_repo,
            role_service=role_service,
            verification_repo=MagicMock(),
            credentials_repo=MagicMock(),
            token_service=MagicMock(),
            email_client=MagicMock(),
        )
        svc.enforce_scope = AsyncMock()
        svc._deny_moderator = AsyncMock()
        svc._load_tenant_or_404 = AsyncMock(
            return_value=Tenant(
                id=2,
                name="Acme",
                organisation="Acme",
                email="test-contact@example.invalid",
                status=TenantStatus.ACTIVE,
            )
        )
        svc._load_tenant_user_or_404 = AsyncMock(return_value=target)
        return svc

    @pytest.mark.asyncio
    async def test_self_registered_user_cannot_be_made_tenant_admin(self) -> None:
        target = _user(CreationType.DEFAULT, tenant_id=2)
        svc = self._service(target)

        with pytest.raises(AppError) as exc_info:
            await svc.update_tenant_user(
                _user(CreationType.TENANT), 2, target.id,
                TenantUserUpdate(role=TenantUserRole.TENANT_ADMIN),
            )

        assert exc_info.value.code == "SELF_REGISTERED_ROLE_RESTRICTED"
        svc._roles._roles.assign_role.assert_not_awaited()
        svc._users.save_and_refresh.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_self_registered_user_patch_with_user_role_succeeds(self) -> None:
        target = _user(CreationType.GOOGLE, tenant_id=2)
        svc = self._service(target)

        await svc.update_tenant_user(
            _user(CreationType.TENANT), 2, target.id,
            TenantUserUpdate(role=TenantUserRole.USER),
        )

        svc._users.save_and_refresh.assert_awaited_once()
