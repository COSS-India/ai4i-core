"""Unit tests: tenant-scope resolution in app.routes.metering.

_resolve_tenant_scope is the single place every metering tab routes through
to turn (X-Tenant-Id / X-Tenant-Name / tenant_id query param) into the
(id, organisation-name) pair the PromQL selectors and cache keys use. Covers:
  - the guard checks the NAME (what queries actually filter on), not the id
  - an admin narrowing to an unknown tenant_id gets 404, not a silent
    platform-wide fallback
  - a transient auth-DB failure surfaces as 503, distinct from "not found"
"""
import importlib.util
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

# app/routes/__init__.py eagerly imports every route module plus
# ai4i_core.bootstrap.versioning, which this suite's conftest doesn't stub —
# load metering.py directly by file path instead (same technique as
# test_service_rbac_filtering.py).
_spec = importlib.util.spec_from_file_location(
    "app.routes.metering", "app/routes/metering.py"
)
_metering_route_mod = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.metering"] = _metering_route_mod
_spec.loader.exec_module(_metering_route_mod)

_OrgLookupError = _metering_route_mod._OrgLookupError
_partition_results = _metering_route_mod._partition_results
_resolve_org = _metering_route_mod._resolve_org
_resolve_tenant_scope = _metering_route_mod._resolve_tenant_scope

from app.services.metering_service import MeteringService


def _svc(auth_db=None) -> MeteringService:
    return MeteringService(client=MagicMock(), auth_db=auth_db)


def _request(tenant_id: str = None, tenant_name: str = None) -> SimpleNamespace:
    headers = {}
    if tenant_id is not None:
        headers["X-Tenant-Id"] = tenant_id
    if tenant_name is not None:
        headers["X-Tenant-Name"] = tenant_name
    return SimpleNamespace(headers=headers)


@pytest.mark.asyncio
class TestResolveTenantScopeNonAdmin:
    async def test_scopes_to_callers_own_tenant_name(self):
        request = _request(tenant_id="7", tenant_name="Acme Corp")
        scope_tenant, scope_tenant_name = await _resolve_tenant_scope(
            request, _svc(), None, False
        )
        assert scope_tenant == "7"
        assert scope_tenant_name == "Acme Corp"

    async def test_missing_tenant_name_raises_403_even_with_id_present(self):
        """The guard checks the NAME (what queries actually filter on), not
        the id — a caller with X-Tenant-Id but no X-Tenant-Name must still be
        refused, not fall through to an unscoped query."""
        request = _request(tenant_id="7", tenant_name=None)
        with pytest.raises(HTTPException) as exc_info:
            await _resolve_tenant_scope(request, _svc(), None, False)
        assert exc_info.value.status_code == 403

    async def test_missing_both_headers_raises_403(self):
        request = _request()
        with pytest.raises(HTTPException) as exc_info:
            await _resolve_tenant_scope(request, _svc(), None, False)
        assert exc_info.value.status_code == 403

    async def test_tenant_id_query_param_ignored_for_non_admin(self):
        """A non-admin can't widen/narrow scope via the tenant_id query param
        — only their own gateway-injected headers apply."""
        request = _request(tenant_id="7", tenant_name="Acme Corp")
        scope_tenant, scope_tenant_name = await _resolve_tenant_scope(
            request, _svc(), 999, False
        )
        assert scope_tenant == "7"
        assert scope_tenant_name == "Acme Corp"


@pytest.mark.asyncio
class TestResolveTenantScopeAdmin:
    async def test_no_tenant_id_is_platform_wide(self):
        request = _request()
        scope_tenant, scope_tenant_name = await _resolve_tenant_scope(
            request, _svc(), None, True
        )
        assert scope_tenant is None
        assert scope_tenant_name is None

    async def test_narrows_to_resolved_organisation_name(self):
        auth_db = AsyncMock()
        result = MagicMock()
        result.scalar.return_value = "Acme Corp"
        auth_db.execute = AsyncMock(return_value=result)
        request = _request()

        scope_tenant, scope_tenant_name = await _resolve_tenant_scope(
            request, _svc(auth_db=auth_db), 7, True
        )
        assert scope_tenant == "7"
        assert scope_tenant_name == "Acme Corp"

    async def test_unknown_tenant_id_raises_404_not_platform_wide(self):
        """Before this fix, an unresolvable tenant_id silently fell through to
        tenant=None (platform-wide) while Scope.tenant_id still reported the
        requested id — wrong numbers presented as scoped."""
        auth_db = AsyncMock()
        result = MagicMock()
        result.scalar.return_value = None  # clean query, no such tenant
        auth_db.execute = AsyncMock(return_value=result)
        request = _request()

        with pytest.raises(HTTPException) as exc_info:
            await _resolve_tenant_scope(request, _svc(auth_db=auth_db), 999, True)
        assert exc_info.value.status_code == 404

    async def test_auth_db_error_raises_503_not_404(self):
        """A transient DB failure must not be presented as 'no such tenant'."""
        auth_db = AsyncMock()
        auth_db.execute = AsyncMock(side_effect=SQLAlchemyError("connection lost"))
        request = _request()

        with pytest.raises(HTTPException) as exc_info:
            await _resolve_tenant_scope(request, _svc(auth_db=auth_db), 7, True)
        assert exc_info.value.status_code == 503


@pytest.mark.asyncio
class TestResolveOrg:
    async def test_returns_none_when_auth_db_not_configured(self):
        assert await _resolve_org(_svc(auth_db=None), "7") is None

    async def test_returns_none_for_empty_tenant_id_without_querying(self):
        auth_db = AsyncMock()
        assert await _resolve_org(_svc(auth_db=auth_db), "") is None
        auth_db.execute.assert_not_called()

    async def test_returns_organisation_on_success(self):
        auth_db = AsyncMock()
        result = MagicMock()
        result.scalar.return_value = "Acme Corp"
        auth_db.execute = AsyncMock(return_value=result)
        assert await _resolve_org(_svc(auth_db=auth_db), "7") == "Acme Corp"

    async def test_raises_org_lookup_error_on_db_failure_instead_of_swallowing(self):
        """Previously caught broad Exception and returned None — indistinguishable
        from a clean "tenant not found" query result."""
        auth_db = AsyncMock()
        auth_db.execute = AsyncMock(side_effect=SQLAlchemyError("down"))
        with pytest.raises(_OrgLookupError):
            await _resolve_org(_svc(auth_db=auth_db), "7")


class TestPartitionResults:
    def test_all_ok_returns_values_unchanged(self):
        values, degraded = _partition_results([1, "two", {"three": 3}])
        assert values == [1, "two", {"three": 3}]
        assert degraded is False

    def test_exception_becomes_none_and_flags_degraded(self):
        values, degraded = _partition_results([1, ValueError("boom"), 3])
        assert values == [1, None, 3]
        assert degraded is True

    def test_empty_input(self):
        values, degraded = _partition_results([])
        assert values == []
        assert degraded is False
