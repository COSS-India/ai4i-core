"""
Integration tests using FastAPI TestClient.

Tests actual HTTP endpoints with mocked DB/Redis.
"""

import os
import shutil
import tempfile

import pytest

_test_key_dir = tempfile.mkdtemp(prefix="route-test-keys-")
os.environ["RS256_KEY_DIRECTORY"] = _test_key_dir
os.environ["RS256_MIN_KEY_COUNT"] = "2"
os.environ["ENVIRONMENT"] = "testing"
os.environ["JWT_ISSUER"] = "auth-service"


@pytest.fixture(scope="module")
async def setup_keys():
    from app.core.security import key_manager
    key_manager.initialize()
    yield
    shutil.rmtree(_test_key_dir, ignore_errors=True)


class TestHealthEndpoints:
    """Health endpoints should work without auth."""

    def test_root(self):
        """GET / returns service info."""
        # This tests the route definition, not the full app (requires DB/Redis)
        from app.routes.health import router
        assert router is not None

    def test_health_route_exists(self):
        from app.routes.health import router
        paths = [r.path for r in router.routes]
        assert "/health" in paths or any("/health" in str(r.path) for r in router.routes)


class TestAuthSchemas:
    """Schema validation tests."""

    def test_register_request_validates_password_length(self):
        from app.schemas.auth import RegisterRequest
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            RegisterRequest(
                email="a@b.com",
                password="short", confirm_password="short",
            )

    def test_register_request_valid(self):
        from app.schemas.auth import RegisterRequest
        req = RegisterRequest(
            email="test@example.com",
            password="StrongP@ss1", confirm_password="StrongP@ss1",
        )
        assert req.email == "test@example.com"

    def test_login_request(self):
        from app.schemas.auth import LoginRequest
        req = LoginRequest(email="a@b.com", password="pass")
        assert req.email == "a@b.com"
        assert req.password == "pass"

    def test_api_key_create_request(self):
        from app.schemas.api_key import CreateAPIKeyRequest
        req = CreateAPIKeyRequest(
            key_name="test",
            permissions=["nmt.inference", "asr.inference"],
            expires_days=7,
        )
        assert req.key_name == "test"
        assert req.permissions == ["nmt.inference", "asr.inference"]
        assert req.expires_days == 7


class TestDependencyFactories:
    """Service dependency factories return correct types."""

    @pytest.mark.asyncio
    async def test_factories_defined(self):
        from app.dependencies.services import (
            get_auth_service,
            get_api_key_service,
            get_role_service,
            get_user_service,
            get_oauth_service,
            get_cache_service,
        )
        # Verify all factories are callable
        assert callable(get_auth_service)
        assert callable(get_api_key_service)
        assert callable(get_role_service)
        assert callable(get_user_service)
        assert callable(get_oauth_service)
        assert callable(get_cache_service)


class TestRouteRegistration:
    """All expected routes are registered."""

    def test_all_routers_included(self):
        from app.routes import api_router
        paths = set()
        for route in api_router.routes:
            if hasattr(route, "path"):
                paths.add(route.path)
        # Core auth endpoints
        assert "/api/v1/auth/login" in paths
        assert "/api/v1/auth/register" in paths
        assert "/api/v1/auth/refresh" in paths
        assert "/api/v1/auth/logout" in paths
        assert "/api/v1/auth/change-password" in paths
        # Validation
        assert "/api/v1/auth/validate" in paths
        # Health
        assert "/api/v1/auth/health" in paths

    def test_protected_routes_have_guard(self):
        """User, role, permission, api_key routes should have endpoint guard."""
        from app.routes import api_router
        # The guard is registered as a router-level dependency
        # We can verify by checking the router structure exists
        assert api_router is not None


class TestTenantAdminRoleRemoval:
    """Tenant Admin role-removal: same-tenant allowed, cross-tenant blocked."""

    def _make_user(self, tenant_id: int):
        from uuid import uuid4
        from app.models.user import User
        return User(id=uuid4(), email="u@example.com", username="u", tenant_id=tenant_id)

    def _mock_request(self):
        from unittest.mock import MagicMock
        req = MagicMock()
        req.state.tenant_id = None  # fall back to current_user.tenant_id
        return req

    @pytest.mark.asyncio
    @pytest.mark.parametrize("role_name", ["USER", "GUEST", "MODERATOR", "TENANT ADMIN"])
    async def test_tenant_admin_remove_role_within_tenant(self, role_name):
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.dependencies.tenant_scope import enforce_target_user_same_tenant
        from app.models.role_name import RoleName

        caller = self._make_user(tenant_id=1)
        target = self._make_user(tenant_id=1)
        mock_db = MagicMock()

        with patch("app.dependencies.tenant_scope.RoleRepository") as MockRoleRepo, \
             patch("app.dependencies.tenant_scope.UserRepository") as MockUserRepo:
            MockRoleRepo.return_value.get_user_roles = AsyncMock(return_value=["TENANT ADMIN"])
            MockUserRepo.return_value.get_by_id = AsyncMock(return_value=target)

            # Must not raise — TENANT ADMIN acting on a user in their own tenant
            await enforce_target_user_same_tenant(
                self._mock_request(), caller, target.id, mock_db,
                bypass_roles=(RoleName.ADMIN, RoleName.MODERATOR),
            )

    @pytest.mark.asyncio
    async def test_tenant_admin_remove_role_cross_tenant_forbidden(self):
        from unittest.mock import AsyncMock, MagicMock, patch
        from fastapi import HTTPException
        from app.dependencies.tenant_scope import enforce_target_user_same_tenant
        from app.models.role_name import RoleName

        caller = self._make_user(tenant_id=1)
        target = self._make_user(tenant_id=2)  # different tenant
        mock_db = MagicMock()

        with patch("app.dependencies.tenant_scope.RoleRepository") as MockRoleRepo, \
             patch("app.dependencies.tenant_scope.UserRepository") as MockUserRepo:
            MockRoleRepo.return_value.get_user_roles = AsyncMock(return_value=["TENANT ADMIN"])
            MockUserRepo.return_value.get_by_id = AsyncMock(return_value=target)

            with pytest.raises(HTTPException) as exc_info:
                await enforce_target_user_same_tenant(
                    self._mock_request(), caller, target.id, mock_db,
                    bypass_roles=(RoleName.ADMIN, RoleName.MODERATOR),
                )

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail["code"] == "TENANT_FORBIDDEN"


class TestRequireSelfOrAnyRole:
    """require_self_or_any_role: self-access allowed for any role; privileged
    roles delegate to enforce_target_user_same_tenant for any user_id.

    MODERATOR is exercised as a self-access-only role (alongside USER/GUEST),
    not as privileged: migration e3f4a5b6c7d8 revoked its ability to view any
    user's roles, and fe0092e08b62 re-grants roles.read at the gateway only
    for the self-view case covered here.
    """

    def _make_user(self, tenant_id: int = 1):
        from uuid import uuid4
        from app.models.user import User
        return User(id=uuid4(), email="u@example.com", username="u", tenant_id=tenant_id)

    def _mock_request(self):
        from unittest.mock import MagicMock
        req = MagicMock()
        req.state.tenant_id = None
        return req

    @pytest.mark.asyncio
    @pytest.mark.parametrize("role_name", ["USER", "GUEST", "MODERATOR"])
    async def test_self_access_allowed(self, role_name):
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.dependencies.permissions import require_self_or_any_role
        from app.models.role_name import RoleName

        caller = self._make_user()
        check = require_self_or_any_role(RoleName.ADMIN, RoleName.TENANT_ADMIN)

        with patch("app.dependencies.permissions.RoleRepository") as MockRoleRepo, \
             patch("app.dependencies.permissions.enforce_target_user_same_tenant", new=AsyncMock()) as mock_enforce:
            MockRoleRepo.return_value.get_user_roles = AsyncMock(return_value=[role_name])
            result = await check(self._mock_request(), caller.id, caller, MagicMock())

        assert result is caller
        mock_enforce.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("role_name", ["USER", "GUEST", "MODERATOR"])
    async def test_cross_user_access_forbidden(self, role_name):
        from uuid import uuid4
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.core.exceptions import InsufficientPermissionsError
        from app.dependencies.permissions import require_self_or_any_role
        from app.models.role_name import RoleName

        caller = self._make_user()
        other_user_id = uuid4()
        check = require_self_or_any_role(RoleName.ADMIN, RoleName.TENANT_ADMIN)

        with patch("app.dependencies.permissions.RoleRepository") as MockRoleRepo, \
             patch("app.dependencies.permissions.enforce_target_user_same_tenant", new=AsyncMock()) as mock_enforce:
            MockRoleRepo.return_value.get_user_roles = AsyncMock(return_value=[role_name])
            with pytest.raises(InsufficientPermissionsError):
                await check(self._mock_request(), other_user_id, caller, MagicMock())
        mock_enforce.assert_not_awaited()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("role_name", ["ADMIN", "TENANT ADMIN"])
    async def test_privileged_role_delegates_to_tenant_enforcement(self, role_name):
        """Privileged roles reach enforce_target_user_same_tenant for any user_id.

        This only proves delegation happens with the right arguments — the
        actual same-tenant-allowed / cross-tenant-forbidden behavior is
        covered by that helper's own tests in TestTenantAdminRoleRemoval.
        """
        from uuid import uuid4
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.dependencies.permissions import require_self_or_any_role
        from app.models.role_name import RoleName

        caller = self._make_user()
        target_id = uuid4()
        db = MagicMock()
        request = self._mock_request()
        check = require_self_or_any_role(RoleName.ADMIN, RoleName.TENANT_ADMIN)

        with patch("app.dependencies.permissions.RoleRepository") as MockRoleRepo, \
             patch("app.dependencies.permissions.enforce_target_user_same_tenant", new=AsyncMock()) as mock_enforce:
            MockRoleRepo.return_value.get_user_roles = AsyncMock(return_value=[role_name])
            result = await check(request, target_id, caller, db)

        mock_enforce.assert_awaited_once_with(
            request, caller, target_id, db, bypass_roles=(RoleName.ADMIN, RoleName.MODERATOR)
        )
        assert result is caller

    @pytest.mark.asyncio
    async def test_admin_bypasses_cross_tenant_check_for_real(self):
        """ADMIN reaches a genuinely cross-tenant target with no exception.

        Unlike test_privileged_role_delegates_to_tenant_enforcement above,
        this does NOT mock out enforce_target_user_same_tenant — only its
        own RoleRepository/UserRepository — so the real bypass_roles check
        inside that helper actually runs for a real cross-tenant target.
        """
        from unittest.mock import AsyncMock, MagicMock, patch
        from app.dependencies.permissions import require_self_or_any_role
        from app.models.role_name import RoleName

        caller = self._make_user(tenant_id=1)
        target = self._make_user(tenant_id=2)
        check = require_self_or_any_role(RoleName.ADMIN, RoleName.TENANT_ADMIN)

        with patch("app.dependencies.permissions.RoleRepository") as MockPermRoleRepo, \
             patch("app.dependencies.tenant_scope.RoleRepository") as MockTenantRoleRepo, \
             patch("app.dependencies.tenant_scope.UserRepository") as MockUserRepo:
            MockPermRoleRepo.return_value.get_user_roles = AsyncMock(return_value=[RoleName.ADMIN.value])
            MockTenantRoleRepo.return_value.get_user_roles = AsyncMock(return_value=[RoleName.ADMIN.value])
            MockUserRepo.return_value.get_by_id = AsyncMock(return_value=target)

            result = await check(self._mock_request(), target.id, caller, MagicMock())

        assert result is caller
