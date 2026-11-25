"""Logs Dashboard: the application column shows the name, and the application
filter matches names (resolved to exact app_id values)."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from asyncpg.exceptions import InvalidPasswordError
from fastapi import HTTPException
from sqlalchemy.exc import OperationalError

_APP = Path(__file__).resolve().parents[1] / "app"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_load("app.schemas.telemetry", _APP / "schemas" / "telemetry.py")
_svc = _load("app.services.telemetry_service", _APP / "services" / "telemetry_service.py")
_lookup = _load("app.repositories.application_lookup", _APP / "repositories" / "application_lookup.py")
_route = _load("app.routes.telemetry", _APP / "routes" / "telemetry.py")


def _session(rows: list) -> MagicMock:
    session = MagicMock()
    session.execute = AsyncMock(return_value=rows)
    return session


# ── application_lookup ───────────────────────────────────────────────────────

def test_find_ids_scopes_to_tenant_and_escapes_like_wildcards():
    session = _session([SimpleNamespace(id=3), SimpleNamespace(id=12)])

    ids = asyncio.run(_lookup.find_application_ids_by_name(session, "50%_off", "7"))

    assert ids == ["3", "12"]
    sql, params = session.execute.call_args.args
    assert "tenant_id = :tenant_id" in str(sql)
    assert params == {"pattern": "%50\\%\\_off%", "tenant_id": 7}


def test_find_ids_without_tenant_searches_all_tenants():
    session = _session([])

    asyncio.run(_lookup.find_application_ids_by_name(session, "app", None))

    sql, params = session.execute.call_args.args
    assert "tenant_id" not in str(sql)
    assert params == {"pattern": "%app%"}


@pytest.mark.parametrize("tenant_id", ["abc", "²"])
def test_find_ids_non_numeric_tenant_matches_nothing(tenant_id):
    """'²'.isdigit() is True but int('²') raises — must not reach int()."""
    session = _session([])

    assert asyncio.run(_lookup.find_application_ids_by_name(session, "app", tenant_id)) == []
    session.execute.assert_not_called()


def test_names_by_id_skips_non_numeric_ids_and_empty_input():
    session = _session([SimpleNamespace(id=6, name="Chat Bot")])

    assert asyncio.run(_lookup.application_names_by_id(session, {"6", "x"})) == {"6": "Chat Bot"}
    assert session.execute.call_args.args[1] == {"ids": [6]}
    assert asyncio.run(_lookup.application_names_by_id(_session([]), set())) == {}


# ── telemetry_service ────────────────────────────────────────────────────────

def test_application_ids_filter_is_exact_terms_on_app_id():
    clauses, _ = _svc._build_search_filter_clauses(
        [], None, None, None, None, None, None, [], False, None,
        _svc._SpanFilterParams(application_ids=["6", "8"]),
    )

    assert {"terms": {"attributes.app_id.keyword": ["6", "8"]}} in clauses


def test_search_traces_empty_application_ids_matches_nothing_without_querying():
    """[] means no application matched, not "no filter" — every caller gets that."""
    client = MagicMock()

    result = asyncio.run(_svc.search_traces(
        client, selected_columns=frozenset({"application"}), tenant_filter="7", is_admin=False,
        filters=_svc.TraceFilterParams(application_ids=[]),
        pagination=_svc.PaginationParams(page=1, page_size=15),
    ))

    assert result == _svc.empty_search_result()
    client.search_traces.assert_not_called()


# ── route ────────────────────────────────────────────────────────────────────

def _call_route(
    monkeypatch, *, application=None, columns="application", auth_db=MagicMock(), rows=None,
    find_ids=None, names=None,
):
    search = AsyncMock(return_value={
        "data": rows if rows is not None else [],
        "total": 0, "agg_total": 0, "by_level": {}, "by_task": {}, "is_partial": False,
    })
    find_ids = find_ids or AsyncMock(return_value=["3"])
    names = names or AsyncMock(return_value={"6": "Chat Bot"})
    monkeypatch.setattr(_route, "search_traces", search)
    monkeypatch.setattr(_route, "find_application_ids_by_name", find_ids)
    monkeypatch.setattr(_route, "application_names_by_id", names)

    request = MagicMock()
    request.headers = {"X-Permission-IDS": "5", "X-Tenant-Id": "7"}
    span = _route._TraceSpanFilters(
        user=None, metadata_key=None, metadata_value=None, method=None, model=None,
        error=None, service=None, url=None, application=application,
    )
    base = _route._TraceBaseFilters(
        task_types=None, status_filter=None, tenant_id=None, start_date=None, end_date=None,
        q=None, log_status=None, status_code=None, service_id=None,
    )
    paging = _route._TracePaginationQuery(page=1, page_size=15, sort_by=None, sort_order=None)
    response = asyncio.run(_route.search_traces_opensearch(
        request=request, opensearch_client=MagicMock(), base=base, span=span,
        paging=paging, columns=columns, auth_db=auth_db,
    ))
    return response, search, find_ids


def test_route_resolves_name_filter_within_caller_tenant(monkeypatch):
    auth_db = MagicMock()

    _, search, find_ids = _call_route(monkeypatch, application="bot", auth_db=auth_db)

    find_ids.assert_awaited_once_with(auth_db, "bot", "7")
    assert search.call_args.kwargs["filters"].application_ids == ["3"]


def test_route_name_matching_no_application_passes_empty_ids(monkeypatch):
    _, search, _ = _call_route(monkeypatch, application="zzz", find_ids=AsyncMock(return_value=[]))

    assert search.call_args.kwargs["filters"].application_ids == []


@pytest.mark.parametrize(("value", "expected"), [("9078", ["3", "9078"]), ("007", ["3", "7"]), ("3", ["3"])])
def test_route_numeric_filter_also_matches_the_exact_id(monkeypatch, value, expected):
    _, search, _ = _call_route(monkeypatch, application=value)

    assert search.call_args.kwargs["filters"].application_ids == expected


def test_route_adds_names_and_keeps_application_ids(monkeypatch):
    rows = [
        {"trace_id": "t1", "application": "6"},
        {"trace_id": "t2", "application": "99"},
        {"trace_id": "t3", "application": None},
    ]

    response, _, _ = _call_route(monkeypatch, rows=rows)

    assert [r["application"] for r in response.data] == ["6", "99", None]
    assert [r["application_name"] for r in response.data] == ["Chat Bot", None, None]


def test_route_name_filter_without_auth_db_is_503(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        _call_route(monkeypatch, application="bot", auth_db=None)

    assert exc.value.status_code == 503


# Connect-time failures reach the route unwrapped by SQLAlchemy (asyncpg 0.x,
# SQLAlchemy 2.0); query-time failures arrive as SQLAlchemyError.
_AUTH_DB_FAILURES = [
    ConnectionRefusedError("Connect call failed ('10.0.0.5', 5432)"),
    InvalidPasswordError("password authentication failed for user \"auth\""),
    OperationalError("SELECT 1", {}, Exception("server closed the connection")),
]


@pytest.mark.parametrize("error", _AUTH_DB_FAILURES, ids=type)
def test_route_name_filter_db_error_is_503_not_500(monkeypatch, error):
    with pytest.raises(HTTPException) as exc:
        _call_route(monkeypatch, application="bot", find_ids=AsyncMock(side_effect=error))

    assert exc.value.status_code == 503
    assert exc.value.detail == "Application lookup unavailable"


@pytest.mark.parametrize("error", _AUTH_DB_FAILURES, ids=type)
def test_route_name_lookup_db_error_keeps_ids(monkeypatch, error):
    """Names are display-only: a lookup failure must not fail the log search."""
    failing = AsyncMock(side_effect=error)

    response, _, _ = _call_route(
        monkeypatch, rows=[{"trace_id": "t1", "application": "6"}], names=failing,
    )

    assert response.data[0]["application"] == "6"
    assert response.data[0]["application_name"] is None


def test_route_without_auth_db_keeps_ids(monkeypatch):
    response, _, _ = _call_route(monkeypatch, rows=[{"trace_id": "t1", "application": "6"}], auth_db=None)

    assert response.data[0]["application"] == "6"
    assert response.data[0]["application_name"] is None
