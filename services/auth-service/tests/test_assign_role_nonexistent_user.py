"""POST /auth/roles/assign with a user_id that does not exist must return 404.

The bug: a platform ADMIN bypasses ``enforce_target_user_same_tenant`` — the
only place that 404s on a missing user — and ``RoleService.assign_role``
skipped its user lookup for role USER. The ``user_role`` insert then hit the
``user_role_user_id_fkey`` FK, and the IntegrityError surfaced as a 500
INTERNAL_ERROR (503 through the gateway on staging).
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.constants import RoleName
from app.core.database import get_db
from app.core.exceptions import EntityNotFoundError, register_exception_handlers
from app.dependencies.services import get_role_service
from app.routes import role as role_routes
from app.services.role_service import RoleService

NIL_USER_ID = "00000000-0000-0000-0000-000000000000"


def _role_service() -> RoleService:
    role_repo = MagicMock()
    role_repo._db = MagicMock()
    role_repo._db.execute = AsyncMock()
    role_repo.commit = AsyncMock()
    role_repo.get_role_by_name = AsyncMock(
        side_effect=lambda name: MagicMock(id=7, name=name)
    )
    role_repo.get_user_role_record = AsyncMock(return_value=None)
    # What Postgres does for a user_id that is not in users.
    role_repo.assign_role = AsyncMock(
        side_effect=IntegrityError(
            "INSERT INTO user_role", {}, Exception("user_role_user_id_fkey")
        )
    )
    user_repo = MagicMock()
    user_repo.get_by_id = AsyncMock(return_value=None)
    tenant_repo = MagicMock()
    tenant_repo.get_by_id = AsyncMock(return_value=None)
    return RoleService(role_repo, user_repo, tenant_repo)


def _client(svc: RoleService) -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(role_routes.router)
    route = next(
        r for r in role_routes.router.routes
        if r.path == "/auth/roles/assign" and "POST" in r.methods
    )
    role_dep = next(d.call for d in route.dependant.dependencies if d.name == "admin")
    app.dependency_overrides[role_dep] = lambda: MagicMock(id=uuid4(), tenant_id=1)
    app.dependency_overrides[get_role_service] = lambda: svc
    app.dependency_overrides[get_db] = lambda: MagicMock()
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def platform_admin_caller():
    """The caller holds ADMIN, so the route's tenant-scope check returns early."""
    with patch("app.dependencies.tenant_scope.RoleRepository") as repo_cls:
        repo_cls.return_value.get_user_roles = AsyncMock(return_value=["ADMIN"])
        yield


class TestAssignRoleNonexistentUserRoute:
    @pytest.mark.parametrize(
        "role_name",
        [RoleName.USER, RoleName.ADMIN, RoleName.MODERATOR, RoleName.GUEST],
    )
    def test_admin_assign_to_nonexistent_user_returns_404(
        self, platform_admin_caller, role_name
    ) -> None:
        svc = _role_service()

        response = _client(svc).post(
            "/auth/roles/assign",
            json={"user_id": NIL_USER_ID, "role_name": role_name.value},
        )

        assert response.status_code == 404, response.text
        assert NIL_USER_ID in response.text
        svc._roles.assign_role.assert_not_awaited()
        svc._roles.commit.assert_not_awaited()


class TestRoleServiceAssignRoleNonexistentUser:
    @pytest.mark.asyncio
    async def test_user_role_checks_user_exists_before_insert(self) -> None:
        svc = _role_service()

        with pytest.raises(EntityNotFoundError) as exc_info:
            await svc.assign_role(UUID(NIL_USER_ID), RoleName.USER)

        assert exc_info.value.status_code == 404
        svc._users.get_by_id.assert_awaited_once_with(UUID(NIL_USER_ID))
        svc._roles.assign_role.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unknown_role_still_reported_before_unknown_user(self) -> None:
        svc = _role_service()
        svc._roles.get_role_by_name = AsyncMock(return_value=None)

        with pytest.raises(EntityNotFoundError) as exc_info:
            await svc.assign_role(UUID(NIL_USER_ID), "NO_SUCH_ROLE")

        assert "Role" in exc_info.value.message
        svc._users.get_by_id.assert_not_awaited()
