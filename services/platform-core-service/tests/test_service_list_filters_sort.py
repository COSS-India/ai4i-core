"""Server-side filters/sort for the service list: compiled SQL + route validation."""
from __future__ import annotations

import importlib.util
import inspect
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Annotated
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.dialects import postgresql

from app.models.model_management.model import Model
from app.models.model_management.service import Service
from app.repositories.model_management.service_repository import (
    _MODEL_JOIN,
    ServiceListFilters,
    _apply_list_filters,
    _list_order_by,
)
from app.schemas.model_management.service_columns import SERVICE_LIST_COLUMNS, SORTABLE_KEYS

_spec = importlib.util.spec_from_file_location("app.routes.service", "app/routes/service.py")
_route = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.service"] = _route
_spec.loader.exec_module(_route)
list_services = _route.list_services
ServiceListFilterParams = _route.ServiceListFilterParams
ServiceListSortParams = _route.ServiceListSortParams


def _sql(stmt) -> str:
    sql = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    return sql.replace("%%", "%")  # psycopg2 paramstyle doubles literal percents


def _where(filters: ServiceListFilters, count: bool = False) -> str:
    base = select(func.count(Service.id)).select_from(Service) if count else select(Service, Model)
    sql = _sql(_apply_list_filters(base.join(Model, _MODEL_JOIN), filters))
    return sql[sql.index("WHERE"):]


def _order(sort_by, order="asc") -> str:
    stmt = select(Service, Model).join(Model, _MODEL_JOIN).order_by(*_list_order_by(sort_by, order))
    sql = _sql(stmt)
    return sql[sql.index("ORDER BY"):]


class TestFilters:
    def test_text_filters_are_ilike_contains(self):
        w = _where(ServiceListFilters(name="asr", service_id="abc", model_name="whisper"))
        assert "mm_services.name ILIKE '%asr%'" in w
        assert "mm_services.service_id ILIKE '%abc%'" in w
        assert "mm_models.name ILIKE '%whisper%'" in w

    def test_wildcards_escaped(self):
        w = _where(ServiceListFilters(name="50%_off"))
        # LIKE escape char is a backslash; the postgres literal renderer doubles it.
        assert "'%50\\\\%\\\\_off%'" in w
        assert "ESCAPE" in w

    def test_tier_ids_overlap(self):
        w = _where(ServiceListFilters(tier_ids=["t1", "t2"]))
        assert "&&" in w and "ARRAY['t1', 't2']" in w

    def test_date_ranges_inclusive(self):
        w = _where(ServiceListFilters(
            created_from=date(2026, 1, 1), created_to=date(2026, 1, 31),
            published_from=date(2026, 2, 1), published_to=date(2026, 2, 2),
        ))
        assert "mm_services.created_at >= '2026-01-01 00:00:00+00:00'" in w
        assert "mm_services.created_at < '2026-02-01 00:00:00+00:00'" in w
        assert "mm_services.published_at >= '2026-02-01 00:00:00+00:00'" in w
        assert "mm_services.published_at < '2026-02-03 00:00:00+00:00'" in w

    def test_legacy_filters(self):
        w = _where(ServiceListFilters(task_types=["ASR"], is_published=True, created_by="u1"))
        assert "'asr'" in w and "is_published = true" in w and "created_by = 'u1'" in w

    def test_list_and_count_share_where(self):
        f = ServiceListFilters(
            task_types=["asr"], is_published=False, name="x", model_name="m",
            tier_ids=["t"], created_from=date(2026, 1, 1), published_to=date(2026, 3, 1),
        )
        assert _where(f) == _where(f, count=True)


class TestSort:
    EXPECTED = {
        "name": "mm_services.name",
        "service_id": "mm_services.service_id",
        "model_name": "mm_models.name",
        "task_type": "lower(mm_models.task ->> 'type')",
        "tier": "min(tiers.name)",
        "status": "mm_services.is_published",
        "created_at": "mm_services.created_at",
        "published_at": "mm_services.published_at",
        "input_price": "mm_services.cost_per_unit",
        "output_price": "mm_services.output_cost_per_unit",
        "cached_input_price": "mm_services.cached_input_cost_per_unit",
    }

    def test_covers_all_sortable_keys(self):
        assert set(self.EXPECTED) == set(SORTABLE_KEYS)

    @pytest.mark.parametrize("key", sorted(EXPECTED))
    @pytest.mark.parametrize("order", ["asc", "desc"])
    def test_sort_key(self, key, order):
        o = _order(key, order)
        assert self.EXPECTED[key] in o
        assert f"{order.upper()} NULLS LAST" in o
        assert o.rstrip().endswith("mm_services.id")

    def test_tier_subquery_is_correlated_any(self):
        o = _order("tier")
        assert "CAST(tiers.id AS VARCHAR) = ANY (mm_services.tier_ids)" in o

    def test_default_order(self):
        o = _order(None)
        assert "mm_services.is_published DESC, mm_services.created_at DESC, mm_services.id" in o


def _req(ids):
    r = MagicMock()
    r.headers = {"X-Permission-IDS": ids}
    return r


async def _call(ids, **over):
    svc = MagicMock()
    svc.list_services = AsyncMock(return_value=([], 0))
    filter_keys = set(inspect.signature(ServiceListFilterParams.__init__).parameters) - {"self"}
    paging_keys = set(inspect.signature(ServiceListSortParams.__init__).parameters) - {"self"}
    assert set(over) <= filter_keys | paging_keys, "unknown route override"
    await list_services(
        request=_req(ids), response=MagicMock(headers={}), svc=svc, db=MagicMock(),
        filters=ServiceListFilterParams(**{k: v for k, v in over.items() if k in filter_keys}),
        paging=ServiceListSortParams(**{k: v for k, v in over.items() if k in paging_keys}),
    )
    return svc


class TestRoute:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("over", [
        {"sort_by": "bogus"},
        {"sort_order": "sideways"},
        {"created_from": date(2026, 2, 1), "created_to": date(2026, 1, 1)},
        {"published_from": date(2026, 2, 1), "published_to": date(2026, 1, 1)},
    ])
    async def test_422_for_bad_params(self, over):
        with pytest.raises(_route.ValidationError) as e:
            await _call("1", **over)
        assert type(e.value).__name__ == "_ValidationError"  # conftest stub; real class is 422

    @pytest.mark.asyncio
    @pytest.mark.parametrize("over", [
        {"sort_by": "input_price"},
        {"sort_by": "tier"},
        {"created_from": date(2026, 1, 1)},
        {"published_to": date(2026, 1, 1)},
    ])
    async def test_non_admin_admin_only_is_422(self, over):
        with pytest.raises(_route.ValidationError) as e:
            await _call("50", **over)
        assert type(e.value).__name__ == "_ValidationError"  # conftest stub; real class is 422

    @pytest.mark.asyncio
    async def test_non_admin_tier_ids_returns_published_only(self):
        # The Application fallback picker: never a service the validator rejects.
        svc = await _call("50", tier_ids="t1", is_published=False)
        assert svc.list_services.call_args.kwargs["is_published"] is True
        svc = await _call("1", tier_ids="t1", is_published=False)
        assert svc.list_services.call_args.kwargs["is_published"] is False

    @pytest.mark.asyncio
    async def test_admin_can_use_admin_only(self):
        svc = await _call("1", sort_by="input_price", tier_ids="a,b", created_from=date(2026, 1, 1))
        kw = svc.list_services.call_args.kwargs
        assert kw["filters"].tier_ids == ["a", "b"]
        assert kw["sort_by"] == "input_price"

    @pytest.mark.asyncio
    async def test_non_admin_allowed_filters(self, monkeypatch):
        monkeypatch.setattr(_route.inference_type_cache, "get_all", AsyncMock(return_value=[{"name": "asr"}]))
        svc = await _call(
            "50", name="n", model_name="m", service_id="s", task_types="asr",
            is_published=True, sort_by="name", sort_order="desc",
        )
        kw = svc.list_services.call_args.kwargs
        f = kw["filters"]
        assert (f.name, f.model_name, f.service_id) == ("n", "m", "s")
        assert kw["task_types"] == ["asr"] and kw["is_published"] is True
        assert kw["sort_by"] == "name" and kw["sort_order"] == "desc"

    @pytest.mark.asyncio
    async def test_blank_sort_by_means_default_order(self):
        svc = await _call("50", sort_by="")
        assert svc.list_services.call_args.kwargs["sort_by"] is None

    @pytest.mark.asyncio
    async def test_tier_ids_are_lowercased(self):
        svc = await _call("1", tier_ids=" A1B2 ,c3d4")
        assert svc.list_services.call_args.kwargs["filters"].tier_ids == ["a1b2", "c3d4"]


class TestRouteHelpers:
    def test_every_catalogue_filter_param_is_a_route_param(self):
        params = ServiceListFilterParams()
        for col in SERVICE_LIST_COLUMNS:
            for p in col.filter_params:
                assert hasattr(params, p), f"{col.id}: {p} missing from ServiceListFilterParams"

    def test_admin_only_check_follows_the_catalogue(self, monkeypatch):
        # Marking another filter admin-only in the catalogue is enough to deny it.
        monkeypatch.setattr(_route, "ADMIN_ONLY_FILTER_PARAMS", frozenset({"name", "tier_ids"}))
        with pytest.raises(_route.ValidationError):
            _route._reject_admin_only_filters(ServiceListFilterParams(name="asr"), is_admin=False)
        _route._reject_admin_only_filters(ServiceListFilterParams(name="asr"), is_admin=True)
        _route._reject_admin_only_filters(ServiceListFilterParams(model_name="m"), is_admin=False)

    def test_tier_ids_is_open_to_non_admins(self):
        # The Application fallback picker filters by the Institution's Tier.
        assert "tier_ids" in _route.ADMIN_ONLY_FILTER_PARAMS
        _route._reject_admin_only_filters(ServiceListFilterParams(tier_ids="t1"), is_admin=False)

    def test_split_csv(self):
        assert _route._split_csv(" A1 ,, b2,") == ["a1", "b2"]
        assert _route._split_csv(None) == []
        assert _route._split_csv("") == []

    def test_validate_date_ranges_ok_and_bad(self):
        ok = ServiceListFilterParams(created_from=date(2026, 1, 1), created_to=date(2026, 1, 1))
        _route._validate_date_ranges(ok)
        bad = ServiceListFilterParams(published_from=date(2026, 2, 1), published_to=date(2026, 1, 1))
        with pytest.raises(Exception) as exc:
            _route._validate_date_ranges(bad)
        assert exc.value.code == "INVALID_DATE_RANGE"


class TestDatetimeRangeBounds:
    """Date-range filters accept a date (whole UTC day) or a datetime (exact
    instant), so the UI can send the bounds of the day it displays locally."""

    IST = timezone(timedelta(hours=5, minutes=30))

    def test_ist_day_bounds_reach_sql_unchanged(self):
        w = _where(ServiceListFilters(
            created_from=datetime(2026, 1, 5, tzinfo=self.IST),
            created_to=datetime(2026, 1, 6, tzinfo=self.IST),
        ))
        assert "mm_services.created_at >= '2026-01-05 00:00:00+05:30'" in w
        assert "mm_services.created_at < '2026-01-06 00:00:00+05:30'" in w

    def test_naive_datetime_is_utc(self):
        w = _where(ServiceListFilters(published_from=datetime(2026, 1, 5, 10, 0)))
        assert "mm_services.published_at >= '2026-01-05 10:00:00+00:00'" in w

    def _parse(self, raw):
        app = FastAPI()

        @app.get("/probe")
        def probe(filters: Annotated[ServiceListFilterParams, Depends()]):
            v = filters.created_from
            return {"type": type(v).__name__, "iso": v.isoformat()}

        return TestClient(app).get("/probe", params={"created_from": raw})

    def test_plain_date_stays_a_date(self):
        assert self._parse("2026-01-05").json() == {"type": "date", "iso": "2026-01-05"}

    def test_datetime_keeps_its_offset(self):
        r = self._parse("2026-01-05T00:00:00+05:30").json()
        assert r == {"type": "datetime", "iso": "2026-01-05T00:00:00+05:30"}

    def test_utc_z_suffix(self):
        assert self._parse("2026-01-05T18:30:00Z").json()["iso"] == "2026-01-05T18:30:00+00:00"

    def test_garbage_is_422(self):
        assert self._parse("not-a-date").status_code == 422
        assert self._parse("2026-13-05").status_code == 422

    def test_mixed_date_and_datetime_range_validates(self):
        ok = ServiceListFilterParams(
            created_from=date(2026, 1, 5), created_to=datetime(2026, 1, 5, 12, tzinfo=self.IST)
        )
        _route._validate_date_ranges(ok)
        bad = ServiceListFilterParams(
            created_from=datetime(2026, 1, 6, tzinfo=self.IST), created_to=date(2026, 1, 4)
        )
        with pytest.raises(_route.ValidationError):
            _route._validate_date_ranges(bad)

    def test_empty_datetime_range_is_rejected(self):
        t = datetime(2026, 1, 5, tzinfo=self.IST)
        with pytest.raises(_route.ValidationError):
            _route._validate_date_ranges(ServiceListFilterParams(published_from=t, published_to=t))
