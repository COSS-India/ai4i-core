"""Traces search by caller tags (OpenAI `user` / `metadata`) — AI4IDS-3266.

Scenario that failed before this change: a tenant wants every trace for their
end user `customer-8812` (or metadata `session_id=s-77`). The Logs Dashboard
search box only filters the 15 rows already loaded on the current page, and
/telemetry/traces/search had no parameter for these fields, so a match on any
other page could not be found at all. The search must run in OpenSearch over
all matching traces, still scoped to the caller's own tenant.
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
                        "enduser.id": "customer-8812", "metadata.session_id": "s-77",
                    },
                    "service_name": "ai4x-inference",
                }})
        return {"hits": {"hits": hits}}

    client.search_traces.side_effect = search_traces
    return client


def _search(client, request=None, **params):
    base = dict(
        task_types=None, status_filter=None, tenant_id=None,
        start_date=None, end_date=None, page=1, page_size=15,
    )
    return asyncio.run(search_traces_opensearch(
        request=request or _request(), opensearch_client=client, **{**base, **params},
    ))


def _clauses(client):
    query = client.filter_queries[0]
    return query["bool"]["must"]


# ── The exact ticket scenario ────────────────────────────────────────────────

def test_search_by_user_filters_in_opensearch_across_all_pages():
    """20 matching traces, page size 15: the filter must be in the OpenSearch
    query, so `total` counts all 20 — not just whatever page is on screen."""
    trace_ids = [f"t{i}" for i in range(20)]
    client = _client(trace_ids)

    response = _search(client, user="customer-8812")

    clauses = _clauses(client)
    assert {"term": {"attributes.enduser.id.keyword": "customer-8812"}} in clauses
    assert response.total == 20
    assert response.aggregations.total == 20


def test_search_by_metadata_key_and_value():
    client = _client(["t1"])

    _search(client, metadata_key="session_id", metadata_value="s-77")

    assert {"term": {"attributes.metadata.session_id.keyword": "s-77"}} in _clauses(client)


def test_tag_search_stays_scoped_to_the_callers_tenant():
    """A tenant admin searching by user must never see another tenant's
    traces: the tenant clause is ANDed with the tag clause."""
    client = _client(["t1"])

    _search(client, request=_request(TENANT_ADMIN, "181"), user="customer-8812", tenant_id="999")

    clauses = _clauses(client)
    assert {"match_phrase": {"attributes.tenantId": "181"}} in clauses
    assert {"match_phrase": {"attributes.tenantId": "999"}} not in clauses
    assert {"term": {"attributes.enduser.id.keyword": "customer-8812"}} in clauses


def test_user_and_metadata_filters_combine_with_and():
    client = _client(["t1"])

    _search(client, user="customer-8812", metadata_key="session_id", metadata_value="s-77",
            task_types="llm")

    clauses = _clauses(client)
    assert {"term": {"attributes.enduser.id.keyword": "customer-8812"}} in clauses
    assert {"term": {"attributes.metadata.session_id.keyword": "s-77"}} in clauses
    assert {"match_phrase": {"attributes.task_type": "llm"}} in clauses


def test_no_tag_params_adds_no_tag_clauses():
    """Existing callers that don't pass the new params are unaffected."""
    client = _client(["t1"])

    _search(client, task_types="llm")

    flat = str(_clauses(client))
    assert "enduser.id" not in flat and "metadata." not in flat


# ── Exactness ────────────────────────────────────────────────────────────────

def test_value_over_keyword_cap_falls_back_to_match_phrase():
    """Metadata values may be up to 512 chars, but `.keyword` only indexes
    up to 256 — a term query would silently find nothing."""
    long_value = "v" * 300
    client = _client(["t1"])

    _search(client, metadata_key="note", metadata_value=long_value)

    assert {"match_phrase": {"attributes.metadata.note": long_value}} in _clauses(client)


def test_value_at_keyword_cap_still_uses_exact_term():
    value = "v" * 256
    client = _client(["t1"])

    _search(client, user=value)

    assert {"term": {"attributes.enduser.id.keyword": value}} in _clauses(client)


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
    assert {"term": {"attributes.enduser.id.keyword": "customer-8812"}} in clauses
    assert {"term": {"attributes.metadata.session_id.keyword": "s-77"}} in clauses


@pytest.mark.parametrize("params", [
    {"user": "u" * 257},
    {"metadata_key": "k" * 65, "metadata_value": "v"},
    {"metadata_key": "", "metadata_value": "v"},
    {"metadata_key": "k", "metadata_value": "v" * 513},
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
