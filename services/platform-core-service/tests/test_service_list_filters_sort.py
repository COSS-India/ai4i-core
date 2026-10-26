"""Server-side filters/sort for the service list: compiled SQL + route validation."""
from __future__ import annotations

import importlib.util
import sys
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
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
from app.schemas.model_management.service_columns import SORTABLE_KEYS

_spec = importlib.util.spec_from_file_location("app.routes.service", "app/routes/service.py")
_route = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.service"] = _route
_spec.loader.exec_module(_route)
list_services = _route.list_services


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
    kw = dict(
        request=_req(ids), response=MagicMock(headers={}), task_types=None, is_published=None,
        created_by=None, name=None, service_id=None, model_name=None, tier_ids=None,
        created_from=None, created_to=None, published_from=None, published_to=None,
        sort_by=None, sort_order="asc", offset=0, limit=None, svc=svc, db=MagicMock(),
    )
    kw.update(over)
    await list_services(**kw)
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
        {"tier_ids": "abc"},
        {"created_from": date(2026, 1, 1)},
        {"published_to": date(2026, 1, 1)},
    ])
    async def test_non_admin_admin_only_is_422(self, over):
        with pytest.raises(_route.ValidationError) as e:
            await _call("50", **over)
        assert type(e.value).__name__ == "_ValidationError"  # conftest stub; real class is 422

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
