"""Traces search by caller tags (OpenAI `user` / `metadata`) — AI4IDS-3266.

Scenario that failed before this change: a tenant wants every trace for their
end user `customer-8812` (or metadata `session_id=s-77`). The Logs Dashboard
search box only filters the 15 rows already loaded on the current page, and
/telemetry/traces/search had no parameter for these fields, so a match on any
other page could not be found at all. The search must run in OpenSearch over
all matching traces, still scoped to the caller's own tenant.

`user`/`metadata_key`+`metadata_value` were originally exact-match only (a
`term` query on the `.keyword` subfield). They were later changed to
partial/wildcard matching (same shape as `application`/`method`/`model`/`url`)
so callers can search by a substring instead of needing the full value.
metadata is the one exception: metadata_kv stores "key=value" strings for
many different keys, so only the value half is wildcarded — the key is
anchored exactly, otherwise a search for key "env" would also match an
unrelated key like "dev_env" that happens to contain the same substring.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

_TELEMETRY_ROUTE_PATH = Path(__file__).resolve().parents[1] / "app" / "routes" / "telemetry.py"
_spec = importlib.util.spec_from_file_location("app.routes.telemetry", _TELEMETRY_ROUTE_PATH)
_telemetry = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.telemetry"] = _telemetry
_spec.loader.exec_module(_telemetry)

search_traces_opensearch = _telemetry.search_traces_opensearch

TENANT_ADMIN = "5"
ADMIN = "1"


def _request(permission_ids: str = TENANT_ADMIN, tenant_id: str = "181") -> MagicMock:
    request = MagicMock()
    request.headers = {"X-Permission-IDS": permission_ids, "X-Tenant-Id": tenant_id}
    return request


def _client(matching_trace_ids):
    """Fake OpenSearch: records the Step 1/2 filter query and returns one
    tagged trace per id, with the tags on all three spans."""
    client = MagicMock()
    client.filter_queries = []

    def search_traces(**kwargs):
        aggs = kwargs.get("aggs") or {}
        if "trace_count" in aggs:
            client.filter_queries.append(kwargs["query"])
            return {
                "aggregations": {"trace_count": {"value": len(matching_trace_ids)}},
                "hits": {"hits": [{"_source": {"context": {"trace_id": t}}} for t in matching_trace_ids]},
            }
        if "trace_ids" in aggs:
            return {"aggregations": {"trace_ids": {"buckets": [
                {"key": {"trace_id": t}} for t in matching_trace_ids
            ]}}}
        should = kwargs["query"]["bool"]["should"]
        hits = []
        for clause in should:
            tid = clause["match_phrase"]["context.trace_id"]
            for name in ("request", "model", "ai-inference"):
                hits.append({"_source": {
                    "@timestamp": "2026-10-07T09:00:00Z",
                    "name": name,
                    "context": {"trace_id": tid},
                    "attributes": {
                        "tenantId": "181", "status": "success", "task_type": "llm",
                        "enduser.id": "customer-8812", "metadata_kv": ["session_id=s-77"],
                    },
                    "service_name": "ai4x-inference",
                }})
        return {"hits": {"hits": hits}}

    client.search_traces.side_effect = search_traces
    return client


_BASE_FIELDS = (
    "task_types", "status_filter", "tenant_id", "start_date", "end_date",
    "q", "log_status", "status_code", "service_id",
)
_SPAN_FIELDS = (
    "user", "metadata_key", "metadata_value", "method", "model",
    "error", "service", "url", "application",
)
_PAGING_FIELDS = ("page", "page_size", "sort_by", "sort_order")


def _search(client, request=None, **params):
    """Build base/span/paging dependency objects and call the route function
    directly — search_traces_opensearch takes these (not flat kwargs) since
    the _TraceBaseFilters/_TraceSpanFilters/_TracePaginationQuery refactor."""
    defaults = dict(
        task_types=None, status_filter=None, tenant_id=None,
        start_date=None, end_date=None, q=None, log_status=None,
        status_code=None, service_id=None,
        user=None, metadata_key=None, metadata_value=None,
        method=None, model=None, error=None, service=None, url=None, application=None,
        page=1, page_size=15, sort_by=None, sort_order=None,
        columns=None,
    )
    merged = {**defaults, **params}
    columns = merged.pop("columns")
    base = _telemetry._TraceBaseFilters(**{k: merged[k] for k in _BASE_FIELDS})
    span = _telemetry._TraceSpanFilters(**{k: merged[k] for k in _SPAN_FIELDS})
    paging = _telemetry._TracePaginationQuery(**{k: merged[k] for k in _PAGING_FIELDS})
    return asyncio.run(search_traces_opensearch(
        request=request or _request(),
        opensearch_client=client,
        base=base, span=span, paging=paging, columns=columns,
    ))


def _clauses(client):
    query = client.filter_queries[0]
    return query["bool"]["must"]


def _contains(attribute, value):
    """The clause a partial/wildcard tag search must send: a wildcard on the
    .keyword subfield (values <= the keyword cap) ORed with a match_phrase on
    the analysed text field (values over the cap, never written to .keyword)."""
    field = f"attributes.{attribute}"
    return {
        "bool": {
            "should": [
                {"wildcard": {f"{field}.keyword": {"value": f"*{value}*", "case_insensitive": True}}},
                {"match_phrase": {field: value}},
            ],
            "minimum_should_match": 1,
        }
    }


def _metadata_contains(key, value):
    """The clause a metadata key/value search must send: unlike other tag
    filters, the key is anchored (not wildcarded) so a search for key="env"
    can't also match an unrelated key like "dev_env" that merely contains
    the same substring — only the value half is a contains-match."""
    return {
        "wildcard": {
            "attributes.metadata_kv.keyword": {
                "value": f"{key}=*{value}*", "case_insensitive": True,
            }
        }
    }


# ── The exact ticket scenario ────────────────────────────────────────────────

def test_search_by_user_filters_in_opensearch_across_all_pages():
    """20 matching traces, page size 15: the filter must be in the OpenSearch
    query, so `total` counts all 20 — not just whatever page is on screen."""
    trace_ids = [f"t{i}" for i in range(20)]
    client = _client(trace_ids)

    response = _search(client, user="customer-8812")

    clauses = _clauses(client)
    assert _contains("enduser.id", "customer-8812") in clauses
    assert response.total == 20
    assert response.aggregations.total == 20


def test_search_by_metadata_key_and_value():
    client = _client(["t1"])

    _search(client, metadata_key="session_id", metadata_value="s-77")

    assert _metadata_contains("session_id", "s-77") in _clauses(client)


def test_tag_search_stays_scoped_to_the_callers_tenant():
    """A tenant admin searching by user must never see another tenant's
    traces: the tenant clause is ANDed with the tag clause."""
    client = _client(["t1"])

    _search(client, request=_request(TENANT_ADMIN, "181"), user="customer-8812", tenant_id="999")

    clauses = _clauses(client)
    assert {"match_phrase": {"attributes.tenantId": "181"}} in clauses
    assert {"match_phrase": {"attributes.tenantId": "999"}} not in clauses
    assert _contains("enduser.id", "customer-8812") in clauses


def test_user_and_metadata_filters_combine_with_and():
    client = _client(["t1"])

    _search(client, user="customer-8812", metadata_key="session_id", metadata_value="s-77",
            task_types="llm")

    clauses = _clauses(client)
    assert _contains("enduser.id", "customer-8812") in clauses
    assert _metadata_contains("session_id", "s-77") in clauses
    assert {"match_phrase": {"attributes.task_type": "llm"}} in clauses


def test_no_tag_params_adds_no_tag_clauses():
    """Existing callers that don't pass the new params are unaffected."""
    client = _client(["t1"])

    _search(client, task_types="llm")

    flat = str(_clauses(client))
    assert "enduser.id" not in flat and "metadata_kv" not in flat


# ── Partial/wildcard matching ────────────────────────────────────────────────

def test_value_over_keyword_cap_falls_back_to_match_phrase():
    """Metadata values may be up to 512 chars, but `.keyword` only indexes
    up to 256 — a wildcard query against .keyword would silently find
    nothing, so values over the cap fall back to a plain match_phrase
    (same fallback shape as the old exact-match implementation)."""
    long_value = "v" * 300
    client = _client(["t1"])

    _search(client, metadata_key="note", metadata_value=long_value)

    assert {"match_phrase": {"attributes.metadata_kv": "note=" + long_value}} in _clauses(client)


def test_pair_crossing_keyword_cap_falls_back_even_when_value_alone_fits():
    """The cap applies to the stored entry "key=value", not the value alone:
    10 + 1 + 250 = 261 chars is past it, so wildcard on .keyword would miss."""
    client = _client(["t1"])

    _search(client, metadata_key="k" * 10, metadata_value="v" * 250)

    entry = "k" * 10 + "=" + "v" * 250
    assert {"match_phrase": {"attributes.metadata_kv": entry}} in _clauses(client)


def test_value_at_keyword_cap_still_uses_wildcard_match():
    value = "v" * 256
    client = _client(["t1"])

    _search(client, user=value)

    assert _contains("enduser.id", value) in _clauses(client)


@pytest.mark.parametrize("typed", ["shesna", "SHESNA", "sHeSnA"])
def test_search_ignores_case_of_the_typed_value(typed):
    """Stored `Shesna`, searched in another case: must still match. The
    wildcard clause sets case_insensitive, and match_phrase reads the
    analysed field (already lowercased), so this holds for both branches.
    The value is sent as typed — OpenSearch does the case folding, so it is
    never lowercased into a different string."""
    client = _client(["t1"])

    _search(client, user=typed, metadata_key="session", metadata_value=typed)

    clauses = _clauses(client)
    assert _contains("enduser.id", typed) in clauses
    assert _metadata_contains("session", typed) in clauses


def test_search_is_partial_not_exact():
    """A short typed value must produce a wildcard/contains clause (not a bare
    `term` query), so a caller searching "SHES" can find a stored "SHESNA"."""
    client = _client(["t1"])

    _search(client, user="SHES")

    clause = _clauses(client)[-1]
    assert _contains("enduser.id", "SHES") == clause
    should = clause["bool"]["should"]
    wildcard_value = should[0]["wildcard"]["attributes.enduser.id.keyword"]["value"]
    assert wildcard_value == "*SHES*", "must wrap the typed value for a contains match, not exact"


# ── Bad input ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("params", [
    {"metadata_key": "session_id"},
    {"metadata_value": "s-77"},
])
def test_metadata_key_and_value_must_come_together(params):
    client = _client(["t1"])

    with pytest.raises(HTTPException) as exc:
        _search(client, **params)

    assert exc.value.status_code == 400
    client.search_traces.assert_not_called()


def _http_client(opensearch_client):
    app = FastAPI()
    app.include_router(_telemetry.router)
    app.dependency_overrides[_telemetry._get_opensearch_client] = lambda: opensearch_client
    return TestClient(app)


def test_http_query_params_reach_opensearch():
    """Through FastAPI: the Annotated params are parsed from the query string."""
    client = _client(["t1"])

    response = _http_client(client).get(
        "/telemetry/traces/search",
        params={"user": "customer-8812", "metadata_key": "session_id", "metadata_value": "s-77"},
        headers={"X-Permission-IDS": TENANT_ADMIN, "X-Tenant-Id": "181"},
    )

    assert response.status_code == 200, response.text
    clauses = _clauses(client)
    assert _contains("enduser.id", "customer-8812") in clauses
    assert _metadata_contains("session_id", "s-77") in clauses


@pytest.mark.parametrize("params", [
    {"user": "u" * 257},
    {"metadata_key": "k" * 65, "metadata_value": "v"},
    {"metadata_key": "", "metadata_value": "v"},
    {"metadata_key": "k", "metadata_value": "v" * 513},
    {"metadata_key": "a=b", "metadata_value": "c"},
])
def test_http_rejects_values_beyond_the_ingest_limits(params):
    """Nothing longer than the ingest rules allow can exist in a span."""
    client = _client(["t1"])

    response = _http_client(client).get(
        "/telemetry/traces/search", params=params,
        headers={"X-Permission-IDS": TENANT_ADMIN, "X-Tenant-Id": "181"},
    )

    assert response.status_code == 422, response.text
    client.search_traces.assert_not_called()
