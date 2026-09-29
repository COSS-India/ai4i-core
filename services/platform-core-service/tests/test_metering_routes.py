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
import json
import sys
from datetime import datetime, timezone
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
_parse_from_to = _metering_route_mod._parse_from_to
get_tenant_consumption = _metering_route_mod.get_tenant_consumption
get_overview = _metering_route_mod.get_overview
get_model_consumption = _metering_route_mod.get_model_consumption

from app.services.metering_service import MeteringService
from app.utils.metering_promql_builder import PROMETHEUS_API_PATH_LABEL, AbsoluteRange


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
        # AI4IDS-2716 review: language_diarization ships in the inference-type catalogue
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


# ── Custom from/to range ─────────────────────────────────────────────────────

# 17:30 IST on 2026-09-29.
_NOW = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)


def _utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


@pytest.fixture
def frozen_now(monkeypatch):
    class _Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return _NOW if tz is not None else _NOW.replace(tzinfo=None)

    monkeypatch.setattr(_metering_route_mod, "datetime", _Frozen)
    return _NOW


@pytest.mark.usefixtures("frozen_now")
class TestParseFromTo:
    def _assert_422(self, from_, to, detail_part):
        with pytest.raises(HTTPException) as exc_info:
            _parse_from_to(from_, to)
        assert exc_info.value.status_code == 422
        assert detail_part in exc_info.value.detail

    def test_neither_returns_none(self):
        assert _parse_from_to(None, None) is None

    def test_only_from_raises_422(self):
        self._assert_422("2026-09-20", None, "together")

    def test_only_to_raises_422(self):
        self._assert_422(None, "2026-09-20", "together")

    def test_malformed_raises_422(self):
        self._assert_422("20-09-2026", "2026-09-22", "`from`")
        self._assert_422("2026-09-20", "yesterday", "`to`")

    def test_to_before_from_raises_422(self):
        self._assert_422("2026-09-22T00:00:00", "2026-09-20T00:00:00", "earlier")

    def test_equal_datetimes_raise_422(self):
        self._assert_422("2026-09-20T10:00:00", "2026-09-20T10:00:00", "earlier")

    def test_future_to_raises_422(self):
        self._assert_422("2026-09-20T00:00:00", "2026-09-30T00:00:00+05:30", "future")

    def test_future_date_only_to_raises_422(self):
        self._assert_422("2026-09-20", "2026-09-30", "future")

    def test_to_within_clock_skew_tolerance_is_clamped_to_now(self):
        r = _parse_from_to("2026-09-20T00:00:00Z", "2026-09-29T12:00:30Z")
        assert r.end == _NOW

    def test_naive_datetimes_are_read_as_ist(self):
        r = _parse_from_to("2026-09-20T00:00:00", "2026-09-21T00:00:00")
        assert r == AbsoluteRange(start=_utc(2026, 9, 19, 18, 30), end=_utc(2026, 9, 20, 18, 30))

    def test_explicit_offsets_are_kept(self):
        r = _parse_from_to("2026-09-20T00:00:00Z", "2026-09-21T06:00:00+05:30")
        assert r == AbsoluteRange(start=_utc(2026, 9, 20), end=_utc(2026, 9, 21, 0, 30))

    def test_date_only_to_covers_the_whole_day(self):
        r = _parse_from_to("2026-09-20", "2026-09-22")
        assert r == AbsoluteRange(start=_utc(2026, 9, 19, 18, 30), end=_utc(2026, 9, 22, 18, 30))

    def test_same_date_is_a_one_day_range(self):
        r = _parse_from_to("2026-09-20", "2026-09-20")
        assert (r.end - r.start).total_seconds() == 86_400

    def test_date_only_today_is_capped_at_now(self):
        r = _parse_from_to("2026-09-28", "2026-09-29")
        assert r.end == _NOW

    # With a 15-day retention, now-15d is 2026-09-14T17:30 IST, so the
    # earliest accepted `from` is the next IST midnight: 2026-09-15 IST
    # (2026-09-14T18:30Z).
    def test_from_past_retention_raises_422(self, monkeypatch):
        monkeypatch.setattr(_metering_route_mod.settings, "prometheus_retention_days", 15)
        self._assert_422("2026-09-14T18:29:59Z", "2026-09-20T00:00:00Z", "on or after")

    def test_from_at_retention_floor_is_accepted(self, monkeypatch):
        monkeypatch.setattr(_metering_route_mod.settings, "prometheus_retention_days", 15)
        r = _parse_from_to("2026-09-14T18:30:00Z", "2026-09-20T00:00:00Z")
        assert r.start == _utc(2026, 9, 14, 18, 30)

    def test_earliest_calendar_day_is_accepted(self, monkeypatch):
        """The first whole IST day inside retention is selectable; the day
        before it (partly past retention) is not."""
        monkeypatch.setattr(_metering_route_mod.settings, "prometheus_retention_days", 15)
        assert _parse_from_to("2026-09-15", "2026-09-20").start == _utc(2026, 9, 14, 18, 30)
        self._assert_422("2026-09-14", "2026-09-20", "on or after")

    def test_earliest_from_is_an_ist_midnight(self, monkeypatch):
        monkeypatch.setattr(_metering_route_mod.settings, "prometheus_retention_days", 15)
        assert _metering_route_mod._earliest_from(_NOW) == _utc(2026, 9, 14, 18, 30)

    def test_unencoded_plus_offset_is_accepted(self):
        """`+05:30` sent without URL-encoding arrives as ` 05:30`."""
        r = _parse_from_to("2026-09-20T00:00:00 05:30", "2026-09-21T00:00:00 05:30")
        assert r == AbsoluteRange(start=_utc(2026, 9, 19, 18, 30), end=_utc(2026, 9, 20, 18, 30))

    def test_space_separated_datetime_is_not_date_only(self):
        r = _parse_from_to("2026-09-20 00:00", "2026-09-21 00:00")
        assert r.end == _utc(2026, 9, 20, 18, 30)

    def test_from_inside_current_cache_bucket_is_not_emptied(self, monkeypatch):
        """Flooring `to` to the cache TTL would put it before `from`; the
        exact now is used instead of a misleading 422."""
        monkeypatch.setattr(_metering_route_mod, "_CACHE_TTL", 3600)
        r = _parse_from_to("2026-09-29T11:59:00Z", "2026-09-29T12:00:00Z")
        assert r == AbsoluteRange(start=_utc(2026, 9, 29, 11, 59), end=_NOW)


class TestFloorToCacheTtl:
    def test_open_end_is_floored_to_the_ttl_bucket(self, monkeypatch):
        monkeypatch.setattr(_metering_route_mod, "_CACHE_TTL", 60)
        floor = _metering_route_mod._floor_to_cache_ttl
        assert floor(_utc(2026, 9, 29, 12, 0, 59)) == _utc(2026, 9, 29, 12, 0, 0)
        assert floor(_utc(2026, 9, 29, 12, 1, 0)) == _utc(2026, 9, 29, 12, 1, 0)

    def test_zero_ttl_does_not_divide_by_zero(self, monkeypatch):
        monkeypatch.setattr(_metering_route_mod, "_CACHE_TTL", 0)
        assert _metering_route_mod._floor_to_cache_ttl(_utc(2026, 9, 29, 12, 0, 5)) == _utc(2026, 9, 29, 12, 0, 5)


def test_requests_ending_now_within_one_ttl_share_a_range(monkeypatch):
    """Two "until today" requests seconds apart must map to the same range,
    so they share a cache key instead of each bypassing the cache."""
    monkeypatch.setattr(_metering_route_mod, "_CACHE_TTL", 60)
    def _frozen_at(fixed: datetime):
        class _Frozen(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed
        return _Frozen

    ranges = []
    for second in (5, 50):
        monkeypatch.setattr(_metering_route_mod, "datetime", _frozen_at(_utc(2026, 9, 29, 12, 0, second)))
        ranges.append(_parse_from_to("2026-09-28", "2026-09-29"))
    assert ranges[0] == ranges[1]
    assert ranges[0].end == _utc(2026, 9, 29, 12, 0, 0)


class _FakeUsageRepo:
    """Stands in for UsageRepository in the route module; records the
    tenant_id it was asked about."""
    calls: list = []
    result = None
    error: Exception = None

    def __init__(self, db):
        self._db = db

    async def get_first_usage_at(self, tenant_id):
        _FakeUsageRepo.calls.append(tenant_id)
        if _FakeUsageRepo.error:
            raise _FakeUsageRepo.error
        return _FakeUsageRepo.result


@pytest.fixture
def fake_usage_repo(monkeypatch):
    _FakeUsageRepo.calls = []
    _FakeUsageRepo.result = None
    _FakeUsageRepo.error = None
    monkeypatch.setattr(_metering_route_mod, "UsageRepository", _FakeUsageRepo)
    return _FakeUsageRepo


def _overview_svc() -> MagicMock:
    svc = MagicMock()
    svc._auth_db = None
    svc.overview_tenant_data = AsyncMock(return_value=(None, {"24h": None, "7d": None, "30d": None}))
    svc.request_total = AsyncMock(return_value=None)
    svc.request_volume_chart = AsyncMock(return_value=None)
    svc.usage_concentration = AsyncMock(return_value=None)
    svc.model_usage_growth_pct = AsyncMock(return_value=None)
    svc.first_request_at = AsyncMock(return_value=None)
    return svc


def _empty_redis() -> AsyncMock:
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    return redis


def _set_keys(redis: AsyncMock) -> list[str]:
    return [c.args[0] for c in redis.set.call_args_list]


def _overview_keys(redis: AsyncMock) -> list[str]:
    return [k for k in _set_keys(redis) if k.startswith("metering:overview:")]


def _tenant_admin_request() -> SimpleNamespace:
    return SimpleNamespace(headers={
        "X-Permission-IDS": "5", "X-Tenant-Id": "7", "X-Tenant-Name": "Acme Corp",
    })


async def _call_overview(svc, request=None, db=None, redis=None, **params):
    kwargs = dict(window="24h", from_=None, to=None, limit=10, tenant_id=None, task_types=None)
    kwargs.update(params)
    return await get_overview(
        request=request or _admin_request(), svc=svc, redis=redis or _empty_redis(),
        db=db or AsyncMock(), **kwargs,
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("frozen_now", "fake_usage_repo")
class TestOverviewCustomRange:
    async def test_from_to_overrides_window(self):
        svc = _overview_svc()
        redis = _empty_redis()
        response = await _call_overview(svc, redis=redis, window="7d", from_="2026-09-20", to="2026-09-22")

        expected = AbsoluteRange(start=_utc(2026, 9, 19, 18, 30), end=_utc(2026, 9, 22, 18, 30))
        assert svc.request_total.call_args.kwargs["time_range"] == expected
        assert svc.request_volume_chart.call_args.args[0] == expected
        assert svc.usage_concentration.call_args.kwargs["time_range"] == expected

        # The cached payload (what a later hit returns) uses the `from` key.
        dumped = json.loads(redis.set.call_args.args[1])["scope"]
        assert dumped["window"] == "custom"
        assert dumped["from"] == "2026-09-19T18:30:00Z"
        assert dumped["to"] == "2026-09-22T18:30:00Z"
        cache_key = redis.set.call_args.args[0]
        assert ":custom:" in cache_key and ":7d:" not in cache_key

    async def test_window_only_is_unchanged(self):
        svc = _overview_svc()
        response = await _call_overview(svc, window="7d")
        assert svc.request_total.call_args.kwargs["time_range"] == "7d"
        assert response.scope.window == "7d"
        assert response.scope.from_ is None and response.scope.to is None

    async def test_cached_payload_round_trips_from_and_to(self):
        """What _cache_set stores must validate back with from/to intact —
        a cached hit is returned through the same response_model."""
        redis = _empty_redis()
        response = await _call_overview(_overview_svc(), redis=redis, from_="2026-09-20", to="2026-09-22")
        restored = type(response).model_validate(json.loads(redis.set.call_args.args[1]))
        assert restored.scope.from_ == "2026-09-19T18:30:00Z"
        assert restored.scope.to == "2026-09-22T18:30:00Z"

    async def test_invalid_range_raises_422_before_querying(self):
        svc = _overview_svc()
        with pytest.raises(HTTPException) as exc_info:
            await _call_overview(svc, from_="2026-09-20")
        assert exc_info.value.status_code == 422
        svc.request_total.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.usefixtures("frozen_now")
class TestOverviewFirstUsageAt:
    async def test_admin_platform_wide_gets_min_across_tenants(self, fake_usage_repo):
        fake_usage_repo.result = _utc(2026, 3, 4, 5, 6, 7)
        response = await _call_overview(_overview_svc())
        assert fake_usage_repo.calls == [None]
        assert response.first_usage_at == "2026-03-04T05:06:07Z"

    async def test_tenant_scoped_caller_gets_their_own_value(self, fake_usage_repo):
        fake_usage_repo.result = _utc(2026, 5, 1)
        response = await _call_overview(_overview_svc(), request=_tenant_admin_request())
        assert fake_usage_repo.calls == ["7"]
        assert response.first_usage_at == "2026-05-01T00:00:00Z"

    async def test_no_usage_is_none(self, fake_usage_repo):
        response = await _call_overview(_overview_svc())
        assert response.first_usage_at is None

    async def test_repository_error_is_none_not_500(self, fake_usage_repo):
        fake_usage_repo.error = SQLAlchemyError("db down")
        db = AsyncMock()
        response = await _call_overview(_overview_svc(), db=db)
        assert response.first_usage_at is None
        assert response.degraded is False
        db.rollback.assert_awaited_once()

    async def test_repository_error_is_not_cached(self, fake_usage_repo):
        fake_usage_repo.error = SQLAlchemyError("db down")
        redis = _empty_redis()
        await _call_overview(_overview_svc(), redis=redis)
        assert _overview_keys(redis) == []

    async def test_successful_lookup_is_cached(self, fake_usage_repo):
        fake_usage_repo.result = _utc(2026, 3, 4)
        redis = _empty_redis()
        await _call_overview(_overview_svc(), redis=redis)
        assert len(_overview_keys(redis)) == 1


@pytest.mark.asyncio
@pytest.mark.usefixtures("frozen_now")
class TestOverviewFirstUsageAtHybrid:
    """first_usage_at is the earlier of quota_usage (billed only, outlives
    retention) and the metering source's first request (untiered too, within
    retention)."""

    def _svc(self, first_request=None, error=None) -> MagicMock:
        svc = _overview_svc()
        svc.first_request_at = AsyncMock(return_value=first_request, side_effect=error)
        return svc

    async def test_untiered_traffic_before_first_billed_usage_wins(self, fake_usage_repo):
        fake_usage_repo.result = _utc(2026, 8, 10)
        response = await _call_overview(self._svc(_utc(2026, 7, 2, 9, 30)))
        assert response.first_usage_at == "2026-07-02T09:30:00Z"

    async def test_billed_usage_older_than_retention_wins(self, fake_usage_repo):
        fake_usage_repo.result = _utc(2025, 11, 1)
        response = await _call_overview(self._svc(_utc(2026, 7, 2)))
        assert response.first_usage_at == "2025-11-01T00:00:00Z"

    async def test_metering_only(self, fake_usage_repo):
        response = await _call_overview(self._svc(_utc(2026, 7, 2)))
        assert response.first_usage_at == "2026-07-02T00:00:00Z"

    async def test_neither_is_none(self, fake_usage_repo):
        response = await _call_overview(self._svc())
        assert response.first_usage_at is None

    async def test_name_only_scope_skips_the_quota_lookup(self, fake_usage_repo):
        """A tenant admin with X-Tenant-Name but no X-Tenant-Id: quota_usage
        is keyed by id, so get_first_usage_at(None) would return the
        platform-wide MIN. Only the name-filtered metering lookup runs."""
        fake_usage_repo.result = _utc(2025, 1, 1)  # another tenant's usage
        svc = self._svc(_utc(2026, 7, 2))
        request = SimpleNamespace(headers={"X-Permission-IDS": "5", "X-Tenant-Name": "Acme Corp"})
        response = await _call_overview(svc, request=request)
        assert fake_usage_repo.calls == []
        svc.first_request_at.assert_awaited_once_with("Acme Corp", None)
        assert response.first_usage_at == "2026-07-02T00:00:00Z"

    async def test_metering_lookup_is_scoped_to_the_callers_tenant(self, fake_usage_repo):
        svc = self._svc()
        await _call_overview(svc, request=_tenant_admin_request())
        svc.first_request_at.assert_awaited_once_with("Acme Corp", "7")

    async def test_metering_error_falls_back_to_quota_and_is_retried_next_miss(self, fake_usage_repo):
        """Not cached under its own key, so the next overview miss retries it.
        The overview itself is still cached, so a struggling Prometheus isn't
        hit again on every load."""
        fake_usage_repo.result = _utc(2026, 8, 10)
        redis = _empty_redis()
        response = await _call_overview(self._svc(error=RuntimeError("prometheus down")), redis=redis)
        assert response.first_usage_at == "2026-08-10T00:00:00Z"
        assert response.degraded is False
        assert not any(k.startswith("metering:first-usage:") for k in _set_keys(redis))
        assert len(_overview_keys(redis)) == 1

    async def test_cache_key_is_v4(self, fake_usage_repo):
        redis = _empty_redis()
        await _call_overview(self._svc(), redis=redis)
        assert _overview_keys(redis)[0].startswith("metering:overview:v4:")


def _redis_with(entries: dict) -> AsyncMock:
    """Redis mock whose get() serves `entries` (key -> JSON-able dict)."""
    redis = AsyncMock()
    redis.get = AsyncMock(side_effect=lambda key: json.dumps(entries[key]) if key in entries else None)
    return redis


@pytest.mark.asyncio
@pytest.mark.usefixtures("frozen_now")
class TestFirstRequestAtCache:
    """first_request_at is a full-retention subquery that only moves when a
    tenant sends its first request, so it's cached per tenant scope under
    its own key and TTL, independent of the overview's window/task-type/
    role/limit key."""

    def _svc(self, first_request=None) -> MagicMock:
        svc = _overview_svc()
        svc.first_request_at = AsyncMock(return_value=first_request)
        return svc

    async def test_cache_hit_skips_the_query(self, fake_usage_repo):
        svc = self._svc()
        redis = _redis_with({"metering:first-usage:v2:all": {"first_request_at": "2026-07-02T09:00:00Z"}})
        response = await _call_overview(svc, redis=redis)
        svc.first_request_at.assert_not_called()
        assert response.first_usage_at == "2026-07-02T09:00:00Z"

    async def test_none_result_is_not_cached(self, fake_usage_repo):
        """No API-key requests yet: caching that None would keep
        first_usage_at null for up to an hour after the tenant's first
        request (quota_usage has nothing either for untiered keys)."""
        redis = _empty_redis()
        await _call_overview(self._svc(None), redis=redis)
        assert not any(k.startswith("metering:first-usage:") for k in _set_keys(redis))

    async def test_first_request_after_a_none_shows_on_the_next_miss(self, fake_usage_repo):
        svc = self._svc(None)
        redis = _empty_redis()
        await _call_overview(svc, redis=redis)
        svc.first_request_at = AsyncMock(return_value=_utc(2026, 9, 29, 10))
        response = await _call_overview(svc, redis=redis)
        svc.first_request_at.assert_awaited_once()
        assert response.first_usage_at == "2026-09-29T10:00:00Z"

    async def test_miss_stores_value_with_long_ttl(self, fake_usage_repo):
        redis = _empty_redis()
        await _call_overview(self._svc(_utc(2026, 7, 2, 9)), redis=redis)
        call = next(c for c in redis.set.call_args_list if c.args[0] == "metering:first-usage:v2:all")
        assert json.loads(call.args[1]) == {"first_request_at": "2026-07-02T09:00:00Z"}
        assert call.kwargs["ex"] == _metering_route_mod._FIRST_USAGE_CACHE_TTL
        assert _metering_route_mod._FIRST_USAGE_CACHE_TTL >= 3600

    async def test_shared_across_windows_and_task_types(self, fake_usage_repo):
        svc = self._svc()
        redis = _redis_with({"metering:first-usage:v2:all": {"first_request_at": "2026-07-02T09:00:00Z"}})
        await _call_overview(svc, redis=redis, window="7d", task_types="llm")
        await _call_overview(svc, redis=redis, from_="2026-09-20", to="2026-09-22")
        svc.first_request_at.assert_not_called()

    async def test_tenant_scoped_key(self, fake_usage_repo):
        redis = _empty_redis()
        await _call_overview(self._svc(_utc(2026, 7, 2)), redis=redis, request=_tenant_admin_request())
        assert "metering:first-usage:v2:7:Acme Corp" in _set_keys(redis)

    def test_name_only_scope_does_not_share_the_platform_wide_key(self):
        key = _metering_route_mod._first_usage_cache_key
        assert key(None, None) == "metering:first-usage:v2:all"
        assert key(None, "Acme Corp") != key(None, None)


@pytest.mark.asyncio
@pytest.mark.usefixtures("frozen_now", "fake_usage_repo")
class TestOverviewEarliestFrom:
    async def test_response_carries_retention_floor(self, monkeypatch):
        monkeypatch.setattr(_metering_route_mod.settings, "prometheus_retention_days", 15)
        response = await _call_overview(_overview_svc())
        assert response.earliest_from == "2026-09-14T18:30:00Z"

    async def test_cache_hit_gets_a_fresh_value(self, monkeypatch):
        """earliest_from moves at IST midnight, so a cached payload's copy
        is replaced rather than served stale."""
        monkeypatch.setattr(_metering_route_mod.settings, "prometheus_retention_days", 15)
        redis = AsyncMock()
        redis.get = AsyncMock(return_value=json.dumps({"earliest_from": "stale", "degraded": False}))
        response = await _call_overview(_overview_svc(), redis=redis)
        assert response["earliest_from"] == "2026-09-14T18:30:00Z"


@pytest.mark.asyncio
@pytest.mark.usefixtures("frozen_now")
class TestModelConsumptionCustomRange:
    def _svc(self) -> MagicMock:
        svc = MagicMock()
        svc._auth_db = None
        svc.model_breakdown = AsyncMock(return_value=None)
        svc.registry_model_count = AsyncMock(return_value=None)
        return svc

    async def _call(self, svc, **params):
        kwargs = dict(window="24h", from_=None, to=None, tenant_id=None, limit=10, task_types=None)
        kwargs.update(params)
        return await get_model_consumption(
            request=_admin_request(), svc=svc, redis=_empty_redis(), **kwargs,
        )

    async def test_from_to_overrides_window(self):
        svc = self._svc()
        response = await self._call(svc, window="30d", from_="2026-09-20T00:00:00Z", to="2026-09-21T00:00:00Z")
        assert svc.model_breakdown.call_args.kwargs["time_range"] == AbsoluteRange(
            start=_utc(2026, 9, 20), end=_utc(2026, 9, 21),
        )
        assert response.scope.window == "custom"
        assert response.scope.from_ == "2026-09-20T00:00:00Z"

    async def test_window_only_is_unchanged(self):
        svc = self._svc()
        response = await self._call(svc, window="30d")
        assert svc.model_breakdown.call_args.kwargs["time_range"] == "30d"
        assert response.scope.window == "30d"
