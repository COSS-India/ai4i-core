"""Unit tests: tenant-scope resolution in app.routes.metering.

_resolve_tenant_scope is the single place every metering tab routes through
to turn (X-Tenant-Id / X-Tenant-Name / tenant_id query param) into the
(id, organisation-name) pair the PromQL selectors and cache keys use. Covers:
  - the guard checks the NAME (what queries actually filter on), not the id
  - an admin narrowing to an unknown tenant_id gets 404, not a silent
    platform-wide fallback
  - a transient auth-DB failure surfaces as 503, distinct from "not found"
"""
import asyncio
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
_parse_task_types = _metering_route_mod._parse_task_types
get_tenant_consumption = _metering_route_mod.get_tenant_consumption

from app.services.metering_service import MeteringService
from app.utils.metering_promql_builder import PROMETHEUS_API_PATH_LABEL


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


class TestParseTaskTypes:
    """`_parse_task_types` backs the `task_types` query param on all three
    metering tabs — AI4IDS-2716: unsupported values (e.g. "a1c") must 422
    instead of silently passing through to an empty result set."""

    def test_none_returns_none(self):
        assert _parse_task_types(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_task_types("") is None

    def test_valid_single_value(self):
        assert _parse_task_types("llm") == ["llm"]

    def test_valid_comma_separated_values(self):
        assert _parse_task_types("llm,nmt, asr ") == ["llm", "nmt", "asr"]

    def test_case_insensitive(self):
        assert _parse_task_types("LLM") == ["llm"]

    def test_language_diarization_is_a_valid_task_type(self):
        # AI4IDS-2716 review: language_diarization ships in inference_types.yaml
        # (and is part of the frontend's enabled-task-type catalog) but was
        # missing from SERVICE_BREAKDOWN_CONFIG — that gap must not 422 a
        # request for an otherwise-real task type.
        assert _parse_task_types("language_diarization") == ["language_diarization"]

    def test_unsupported_value_raises_422(self):
        with pytest.raises(HTTPException) as exc_info:
            _parse_task_types("a1c")
        assert exc_info.value.status_code == 422
        assert "a1c" in exc_info.value.detail

    def test_one_unsupported_value_among_valid_ones_still_raises_422(self):
        with pytest.raises(HTTPException) as exc_info:
            _parse_task_types("llm,a1c")
        assert exc_info.value.status_code == 422
        assert "a1c" in exc_info.value.detail


class _ConcurrencyEnforcingAuthDB:
    """Mimics AsyncSession's real constraint: a second execute() must not
    start while a previous one on this same session is still in flight —
    matching sqlalchemy.exc.InvalidRequestError's actual trigger. `id_to_name`
    is the CURRENT (post-rename) name; used to prove a serialized caller gets
    the fresh name while a racing one would silently fall back to stale
    Prometheus data instead of raising."""

    def __init__(self, id_to_name: dict):
        self._id_to_name = id_to_name
        self._in_flight = False
        self.concurrent_violations = 0

    async def execute(self, _query, _params=None):
        if self._in_flight:
            self.concurrent_violations += 1
            raise SQLAlchemyError(
                "This session is provisioning a new connection; "
                "concurrent operations are not permitted"
            )
        self._in_flight = True
        await asyncio.sleep(0)  # yield — lets a badly-serialized caller collide here
        result = MagicMock()
        result.all.return_value = list(self._id_to_name.items())
        self._in_flight = False
        return result


def _admin_request() -> SimpleNamespace:
    return SimpleNamespace(headers={"X-Permission-IDS": "1"})  # platform admin


@pytest.mark.asyncio
class TestTenantConsumptionRouteConcurrency:
    """AI4IDS-2798 regression: tenant_ranking and usage_by_tenant_service both
    now resolve tenant names via self._auth_db — a single AsyncSession, not
    safe for concurrent use. Gathering them concurrently (as this route did)
    risks a silent fallback to the stale, pre-rename Prometheus tenant label
    on whichever call loses the race — the exact bug this PR exists to fix,
    reintroduced by the fix itself."""

    def _prom_rows(self, stale_name: str):
        ranking_row = {"metric": {"tenant_id": "7", "tenant": stale_name}, "value": [0, "10"]}
        heatmap_row = {
            "metric": {"tenant_id": "7", "tenant": stale_name, PROMETHEUS_API_PATH_LABEL: "/api/v1/nmt/inference"},
            "value": [0, "10"],
        }

        async def fake_query(promql):
            if PROMETHEUS_API_PATH_LABEL in promql:
                return [heatmap_row]
            return [ranking_row]

        return fake_query

    async def test_ranking_and_heatmap_both_get_the_current_name_not_stale(self):
        """Exact scenario: Prometheus still carries the pre-rename label
        ("OLD NAME Inc"), the DB has the current name ("NEW NAME Ltd"). Both
        tenant_ranking and usage_by_tenant_service must report the CURRENT
        name — not race each other into one showing the stale one."""
        auth_db = _ConcurrencyEnforcingAuthDB({7: "NEW NAME Ltd"})
        client = MagicMock()
        client.query = AsyncMock(side_effect=self._prom_rows("OLD NAME Inc"))
        client.scalar = AsyncMock(return_value=0.0)
        svc = MeteringService(client=client, auth_db=auth_db)

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)

        response = await get_tenant_consumption(
            request=_admin_request(), window="24h", limit=10, tenant_id=None,
            task_types=None, svc=svc, redis=redis,
        )

        assert auth_db.concurrent_violations == 0
        assert response.tenant_ranking[0].tenant == "NEW NAME Ltd"
        assert response.usage_by_service[0].tenant == "NEW NAME Ltd"

    async def test_one_side_failing_does_not_take_the_other_down(self):
        """The two DB-touching calls must still degrade independently — a
        failure in tenant_ranking's name resolution must not also blank out
        usage_by_tenant_service, which succeeded on its own."""
        calls = {"n": 0}

        class _FlakyAuthDB:
            async def execute(self, _query, _params=None):
                calls["n"] += 1
                if calls["n"] == 1:
                    raise SQLAlchemyError("boom")
                result = MagicMock()
                result.all.return_value = [(7, "NEW NAME Ltd")]
                return result

        client = MagicMock()
        client.query = AsyncMock(side_effect=self._prom_rows("OLD NAME Inc"))
        client.scalar = AsyncMock(return_value=0.0)
        svc = MeteringService(client=client, auth_db=_FlakyAuthDB())

        redis = AsyncMock()
        redis.get = AsyncMock(return_value=None)

        response = await get_tenant_consumption(
            request=_admin_request(), window="24h", limit=10, tenant_id=None,
            task_types=None, svc=svc, redis=redis,
        )

        # Ranking's own resolve failed -> falls back to the raw label (still
        # a valid, non-empty response, not a 500 and not blanked to []).
        assert response.tenant_ranking[0].tenant == "OLD NAME Inc"
        # Heatmap's resolve ran second and succeeded independently.
        assert response.usage_by_service[0].tenant == "NEW NAME Ltd"
        assert response.degraded is False
