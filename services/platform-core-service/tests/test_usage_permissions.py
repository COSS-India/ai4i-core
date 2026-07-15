"""Verifies MODERATOR can no longer reach the PPU usage dashboard endpoints.

app/routes/__init__.py pulls in ai4i_core.bootstrap.versioning (not stubbed in
conftest), so app/routes/usage.py is loaded directly via importlib — same
pattern as tests/test_pii_management.py — instead of `from app.routes import
usage`.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from unittest.mock import MagicMock

import pytest
from ai4i_core.exceptions import InsufficientPermissionsError


def _load_usage_module():
    sys.modules["app.core.database"].get_auth_db_optional = MagicMock()

    pkg = types.ModuleType("app.routes")
    pkg.__path__ = ["app/routes"]
    sys.modules["app.routes"] = pkg

    spec = importlib.util.spec_from_file_location("app.routes.usage", "app/routes/usage.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["app.routes.usage"] = mod
    spec.loader.exec_module(mod)
    return mod


usage = _load_usage_module()

ROLE_ADMIN = 1
ROLE_MODERATOR = 2
ROLE_TENANT_ADMIN = 5


def _request(permission_ids: str = "", tenant_id: str | None = None):
    headers = {"X-Permission-IDS": permission_ids}
    if tenant_id is not None:
        headers["X-Tenant-Id"] = tenant_id
    return MagicMock(headers=headers)


class TestRequireAdmin:
    """Gates /usage-summary and /usage-tenants."""

    def test_moderator_rejected(self):
        with pytest.raises(InsufficientPermissionsError):
            usage._require_admin(_request(str(ROLE_MODERATOR)))

    def test_admin_allowed(self):
        usage._require_admin(_request(str(ROLE_ADMIN)))  # no raise

    def test_tenant_admin_rejected(self):
        with pytest.raises(InsufficientPermissionsError):
            usage._require_admin(_request(str(ROLE_TENANT_ADMIN)))

    def test_no_roles_rejected(self):
        with pytest.raises(InsufficientPermissionsError):
            usage._require_admin(_request(""))


class TestRequireUsageAccess:
    """Gates /usage-tenant."""

    def test_moderator_rejected(self):
        with pytest.raises(InsufficientPermissionsError):
            usage._require_usage_access(_request(str(ROLE_MODERATOR)))

    def test_admin_allowed(self):
        usage._require_usage_access(_request(str(ROLE_ADMIN)))  # no raise

    def test_tenant_admin_allowed(self):
        usage._require_usage_access(_request(str(ROLE_TENANT_ADMIN)))  # no raise


class TestIsAdmin:
    def test_moderator_is_not_admin(self):
        assert usage._is_admin(_request(str(ROLE_MODERATOR))) is False

    def test_admin_is_admin(self):
        assert usage._is_admin(_request(str(ROLE_ADMIN))) is True
