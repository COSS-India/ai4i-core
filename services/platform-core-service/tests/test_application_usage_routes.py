"""Unit tests: _authorize_tenant in app.routes.application_usage.

This is the actual cross-institution security boundary for the Metering
Dashboard's Applications tab: an Adopter Admin may view any Institution's
Applications, an Institution Admin (TENANT ADMIN) may only view their own.
Covers:
  - admin passes regardless of X-Tenant-Id / requested tenant_id
  - tenant admin without X-Tenant-Id gets 403
  - tenant admin naming another institution's tenant_id gets 403
  - tenant admin naming their OWN tenant_id passes
  - a caller with neither role gets 403 before the tenant check even runs
"""
from __future__ import annotations

import importlib.util
import sys
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

# app/routes/__init__.py eagerly imports every route module plus
# ai4i_core.bootstrap.versioning, which this suite's conftest doesn't stub —
# load application_usage.py directly by file path instead (same technique as
# test_service_rbac_filtering.py / test_metering_routes.py).
_spec = importlib.util.spec_from_file_location(
    "app.routes.application_usage", "app/routes/application_usage.py"
)
_application_usage_route_mod = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.application_usage"] = _application_usage_route_mod
_spec.loader.exec_module(_application_usage_route_mod)

_authorize_tenant = _application_usage_route_mod._authorize_tenant

from app.core.exceptions import InsufficientPermissionsError

ROLE_ADMIN = 1
ROLE_TENANT_ADMIN = 5


def _make_request(permission_ids: str = "", tenant_id: str | None = None) -> MagicMock:
    request = MagicMock()
    headers = {"X-Permission-IDS": permission_ids}
    if tenant_id is not None:
        headers["X-Tenant-Id"] = tenant_id
    request.headers = headers
    return request


class TestAuthorizeTenant:
    def test_admin_passes_regardless_of_requested_tenant(self):
        request = _make_request(permission_ids=str(ROLE_ADMIN))

        # No X-Tenant-Id at all, requesting an arbitrary institution — admin
        # is platform-wide, this must not raise.
        _authorize_tenant(request, tenant_id="999")

    def test_tenant_admin_without_x_tenant_id_header_gets_403(self):
        request = _make_request(permission_ids=str(ROLE_TENANT_ADMIN))

        with pytest.raises(HTTPException) as exc_info:
            _authorize_tenant(request, tenant_id="2")
        assert exc_info.value.status_code == 403

    def test_tenant_admin_naming_another_institutions_tenant_id_gets_403(self):
        """The actual cross-institution isolation this comment was written
        about: a Tenant Admin scoped to institution 2 must not be able to
        read institution 3's Applications by simply passing tenant_id=3."""
        request = _make_request(permission_ids=str(ROLE_TENANT_ADMIN), tenant_id="2")

        with pytest.raises(InsufficientPermissionsError):
            _authorize_tenant(request, tenant_id="3")

    def test_tenant_admin_naming_their_own_tenant_id_passes(self):
        request = _make_request(permission_ids=str(ROLE_TENANT_ADMIN), tenant_id="2")

        _authorize_tenant(request, tenant_id="2")

    def test_caller_with_neither_role_gets_403_before_tenant_check(self):
        """A caller with no admin/tenant-admin permission at all must be
        rejected by _require_usage_access itself — before _is_admin or the
        X-Tenant-Id comparison ever run."""
        request = _make_request(permission_ids="")

        with pytest.raises(InsufficientPermissionsError):
            _authorize_tenant(request, tenant_id="2")
