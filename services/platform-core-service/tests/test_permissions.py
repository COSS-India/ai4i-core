"""Unit tests: app.core.permissions.authorize_own_tenant_or_admin.

This is the shared tenant-ownership boundary for the PPU usage dashboard
(/pay-per-use/usage-tenant) and the Metering Dashboard's Applications tab
(/pay-per-use/usage-application*) — previously each route module carried its
own copy of _is_admin/_require_usage_access/_caller_tenant_id/the tenant
comparison, so a rule change (new role, different tenant-context source) had
to land in both files and one could silently drift from the other. Moved here
so there is exactly one implementation.

Covers both the behavior itself and — the actual regression this refactor
guards against — that both route modules import and call the SAME function
object, not two copies that merely look alike today.
"""
from __future__ import annotations

import importlib.util
import sys
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.core.exceptions import InsufficientPermissionsError
from app.core.permissions import authorize_own_tenant_or_admin

ROLE_ADMIN = 1
ROLE_TENANT_ADMIN = 5


def _make_request(permission_ids: str = "", tenant_id: str | None = None) -> MagicMock:
    request = MagicMock()
    headers = {"X-Permission-IDS": permission_ids}
    if tenant_id is not None:
        headers["X-Tenant-Id"] = tenant_id
    request.headers = headers
    return request


class TestAuthorizeOwnTenantOrAdmin:
    def test_admin_passes_regardless_of_requested_tenant(self):
        request = _make_request(permission_ids=str(ROLE_ADMIN))

        authorize_own_tenant_or_admin(request, tenant_id="999")

    def test_tenant_admin_without_x_tenant_id_header_gets_403(self):
        request = _make_request(permission_ids=str(ROLE_TENANT_ADMIN))

        with pytest.raises(HTTPException) as exc_info:
            authorize_own_tenant_or_admin(request, tenant_id="2")
        assert exc_info.value.status_code == 403

    def test_tenant_admin_naming_another_institutions_tenant_id_gets_403(self):
        request = _make_request(permission_ids=str(ROLE_TENANT_ADMIN), tenant_id="2")

        with pytest.raises(InsufficientPermissionsError):
            authorize_own_tenant_or_admin(request, tenant_id="3")

    def test_tenant_admin_naming_their_own_tenant_id_passes(self):
        request = _make_request(permission_ids=str(ROLE_TENANT_ADMIN), tenant_id="2")

        authorize_own_tenant_or_admin(request, tenant_id="2")

    def test_caller_with_neither_role_gets_403_before_tenant_check(self):
        request = _make_request(permission_ids="")

        with pytest.raises(InsufficientPermissionsError):
            authorize_own_tenant_or_admin(request, tenant_id="2")


class TestNoDuplicateImplementations:
    """The actual bug this refactor fixes: usage.py and application_usage.py
    each defined their own _is_admin/_require_usage_access/_caller_tenant_id/
    tenant-comparison, so a rule change made in one file silently would not
    apply to the other. Asserting `is` (identity), not just equal behavior,
    is what would catch a future regression where someone reintroduces a
    second copy instead of importing the shared one."""

    @staticmethod
    def _load_route_module(name: str, path: str):
        # app/routes/__init__.py eagerly imports every route module plus
        # ai4i_core.bootstrap.versioning, which this suite's conftest doesn't
        # stub — load the module directly by file path instead (same
        # technique test_application_usage_routes.py already uses).
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module

    def test_usage_route_uses_the_shared_function(self):
        usage_mod = self._load_route_module("app.routes.usage", "app/routes/usage.py")

        assert usage_mod._authorize_tenant is authorize_own_tenant_or_admin

    def test_application_usage_route_uses_the_shared_function(self):
        application_usage_mod = self._load_route_module(
            "app.routes.application_usage", "app/routes/application_usage.py"
        )

        assert application_usage_mod._authorize_tenant is authorize_own_tenant_or_admin
