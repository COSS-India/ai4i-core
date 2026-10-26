"""Unit tests: generic keyword search (q), sort, status_code, service_id filters
and the 20,000-trace keyword cap (AC-17) for the Logs Dashboard search endpoint."""

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
_MAX_KEYWORD_TRACE_IDS = _telemetry._MAX_KEYWORD_TRACE_IDS

ADMIN = "1"
TENANT_ADMIN = "5"


def _request(permission_ids: str = ADMIN, tenant_id: str = "9") -> MagicMock:
    request = MagicMock()
    request.headers = {"X-Permission-IDS": permission_ids, "X-Tenant-Id": tenant_id}
    return request


def _span_hit(trace_id: str, name: str = "request", attrs: dict | None = None) -> dict:
    return {
        "_source": {
            "@timestamp": "2026-10-23T11:20:00Z",
            "name": name,
            "context": {"trace_id": trace_id},
            "attributes": attrs or {"status": "success", "task_type": "llm"},
            "service_name": "inference-service",
        }
    }


def _make_client(trace_ids: list, pre_trace_ids: list | None = None):
    """Mock OpenSearch client that handles all call types in a full search flow.

    Distinguishes calls by their query shape:
    - trace_count in aggs              → main collapse query (Step 2)
    - trace_ids in aggs, multi_match   → keyword pre-query composite agg
    - trace_ids in aggs, no multi_match → breakdown composite agg
    - else                             → span fetch (Step 3 / breakdown batch)

    The keyword pre-query is the only composite-agg call that contains multi_match.
    The breakdown uses _collect_all_trace_ids with the main filter (no multi_match),
    so checking for multi_match is the only reliable distinguishing marker.
    """
    client = MagicMock()
    client.captured_pre_queries = []
    client.captured_main_queries = []

    def search_traces(**kwargs):
        aggs = kwargs.get("aggs") or {}
        query = kwargs.get("query", {})

        if "trace_count" in aggs:
            client.captured_main_queries.append(query)
            return {
                "aggregations": {"trace_count": {"value": len(trace_ids)}},
                "hits": {"hits": [{"_source": {"context": {"trace_id": t}}} for t in trace_ids]},
            }

        if "trace_ids" in aggs:
            is_pre_query = "multi_match" in str(query)
            if is_pre_query:
                client.captured_pre_queries.append(query)
                ids = pre_trace_ids if pre_trace_ids is not None else trace_ids
            else:
                ids = trace_ids
            return {
                "aggregations": {"trace_ids": {"buckets": [{"key": {"trace_id": t}} for t in ids]}}
            }

        # Span fetch
        should = query.get("bool", {}).get("should", [])
        batch_ids = [c["match_phrase"]["context.trace_id"] for c in should]
        return {"hits": {"hits": [_span_hit(tid) for tid in batch_ids]}}

    client.search_traces.side_effect = search_traces
    return client


def _search(client, request=None, **params):
    base = dict(
        task_types=None, status_filter=None, tenant_id=None,
        start_date=None, end_date=None, page=1, page_size=15,
        q=None, log_status=None, status_code=None, service_id=None,
        sort_by=None, sort_order=None, user=None,
        metadata_key=None, metadata_value=None,
    )
    return asyncio.run(search_traces_opensearch(
        request=request or _request(),
        opensearch_client=client,
        **{**base, **params},
    ))


def _http_client(opensearch_client):
    app = FastAPI()
    app.include_router(_telemetry.router)
    app.dependency_overrides[_telemetry._get_opensearch_client] = lambda: opensearch_client
    return TestClient(app)


# ── No search_traces call may exceed the OpenSearch default window ────────────

def test_no_search_traces_call_exceeds_opensearch_window():
    """Pre-queries must use composite aggregation (size=0) — no hits-window dependency.

    OpenSearch rejects size > 10,000 (default max_result_window). The old approach used
    size=20001 which was silently swallowed and returned 0 results on default clusters.
    """
    client = _make_client(["t1", "t2"])

    _search(client, q="gemma", service_id="llm0-01-aug")

    for call in client.search_traces.call_args_list:
        size = call[1].get("size", 0)
        assert size <= 10000, f"search_traces called with size={size} > 10000"


# ── Keyword search (q) ────────────────────────────────────────────────────────

def test_two_word_keyword_reaches_opensearch_as_phrase():
    """AC-10: a two-word keyword must reach OpenSearch as a phrase, not OR-ed tokens.

    query_string default_operator=OR meant q='zzzqqq_nomatch nmt' returned the same
    results as q='nmt'. multi_match type:phrase treats the whole input as a literal
    phrase so both words must appear adjacent in that order.
    """
    client = _make_client(["t1"])

    _search(client, q="zzzqqq_nomatch nmt")

    assert len(client.captured_pre_queries) == 1
    must = client.captured_pre_queries[0]["bool"]["must"][0]
    assert "multi_match" in must, "expected multi_match, not query_string"
    assert must["multi_match"]["type"] == "phrase"
    assert must["multi_match"]["query"] == "zzzqqq_nomatch nmt"


def test_q_filters_main_query_to_pre_query_trace_ids():
    """Trace IDs from the keyword pre-query must gate the main collapse query."""
    client = _make_client(["t1", "t2"])

    _search(client, q="gemma")

    assert len(client.captured_main_queries) == 1
    filter_clauses = client.captured_main_queries[0]["bool"]["must"]
    trace_id_clause = next(
        (c for c in filter_clauses if "terms" in c and "context.trace_id.keyword" in c["terms"]),
        None,
    )
    assert trace_id_clause is not None
    assert set(trace_id_clause["terms"]["context.trace_id.keyword"]) == {"t1", "t2"}


def test_q_with_no_matches_returns_empty_response_without_main_query():
    """If the keyword pre-query finds no traces, return empty immediately."""
    client = _make_client([], pre_trace_ids=[])

    response = _search(client, q="nonexistent")

    assert response.total == 0
    assert response.data == []
    assert client.captured_main_queries == []


def test_no_q_does_not_add_trace_id_filter_to_main_query():
    """Without q the main query must not contain a context.trace_id.keyword filter."""
    client = _make_client(["t1"])

    _search(client)

    assert len(client.captured_main_queries) == 1
    flat = str(client.captured_main_queries[0])
    assert "context.trace_id.keyword" not in flat


# ── AC-17: 20,000-trace cap ───────────────────────────────────────────────────

def test_q_returns_400_when_keyword_matches_more_than_20000_traces():
    """AC-17: a keyword matching >20,000 traces must return HTTP 400."""
    client = MagicMock()
    client.search_traces.return_value = {
        "aggregations": {
            "trace_ids": {
                "buckets": [{"key": {"trace_id": f"t{i}"}} for i in range(_MAX_KEYWORD_TRACE_IDS + 1)]
            }
        }
    }

    with pytest.raises(HTTPException) as exc:
        _search(client, q="very-common-keyword")

    assert exc.value.status_code == 400


def test_q_does_not_400_at_exactly_20000_traces():
    """AC-17 edge case: exactly 20,000 matches is within the limit — only strictly more triggers 400."""
    client = _make_client([f"t{i}" for i in range(_MAX_KEYWORD_TRACE_IDS)])

    response = _search(client, q="keyword")

    assert response.total == _MAX_KEYWORD_TRACE_IDS




# ── task_types + status_code ──────────────────────────────────────────────────

def test_task_types_and_status_code_both_in_main_filter_not_pre_queried():
    """task_type is set on the request span (same doc as status_code/url/total_time_ms)
    so both filters belong in the main query — no pre-query gate needed.

    An earlier review suggested a trace-ID gate, but staging data confirms task_type
    is present on the request span (orchestrator.py:83, routes/inference.py:527),
    so a single bool.must with name=request satisfies both constraints on one document.
    """
    client = _make_client(["t1"])

    _search(client, task_types="llm", status_code="200")

    assert len(client.captured_main_queries) == 1
    flat = str(client.captured_main_queries[0])
    assert "task_type" in flat
    assert "status_code" in flat
    # No pre-query issued: task_type does not need cross-span resolution
    assert len(client.captured_pre_queries) == 0


# ── Sort validation ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("sort_by", ["timestamp", "url", "latency", "status_code"])
def test_valid_sort_by_values_are_accepted(sort_by):
    client = _make_client(["t1"])
    response = _search(client, sort_by=sort_by, sort_order="desc")
    assert response is not None


def test_invalid_sort_by_returns_422():
    client = _make_client(["t1"])

    with pytest.raises(HTTPException) as exc:
        _search(client, sort_by="invalid_field")

    assert exc.value.status_code == 422


def test_invalid_sort_order_returns_422():
    client = _make_client(["t1"])

    with pytest.raises(HTTPException) as exc:
        _search(client, sort_order="sideways")

    assert exc.value.status_code == 422


def test_sort_by_latency_maps_to_total_time_ms():
    """sort_by=latency must use attributes.total_time_ms, not latency_ms."""
    client = _make_client(["t1"])

    _search(client, sort_by="latency", sort_order="desc")

    for call_obj in client.search_traces.call_args_list:
        kwargs = call_obj[1]
        if "trace_count" in (kwargs.get("aggs") or {}):
            sort_clause = kwargs.get("sort", [])
            assert any("total_time_ms" in str(s) for s in sort_clause), (
                f"Expected total_time_ms in sort clause, got: {sort_clause}"
            )
            return
    pytest.fail("main query call not found")


# ── Status code filter ────────────────────────────────────────────────────────

def test_status_code_filter_is_included_in_main_query():
    client = _make_client(["t1"])

    _search(client, status_code="200")

    assert len(client.captured_main_queries) == 1
    flat = str(client.captured_main_queries[0])
    assert "200" in flat and "status_code" in flat


def test_status_code_comma_separated_values_all_included():
    client = _make_client(["t1"])

    _search(client, status_code="200,404,500")

    assert len(client.captured_main_queries) == 1
    flat = str(client.captured_main_queries[0])
    assert "200" in flat and "404" in flat and "500" in flat


def test_status_code_rejects_non_integer():
    client = _make_client(["t1"])

    with pytest.raises(HTTPException) as exc:
        _search(client, status_code="ok")

    assert exc.value.status_code == 422


def test_status_code_rejects_out_of_range():
    client = _make_client(["t1"])

    with pytest.raises(HTTPException) as exc:
        _search(client, status_code="99")

    assert exc.value.status_code == 422


def test_status_code_rejects_more_than_10_values():
    client = _make_client(["t1"])

    with pytest.raises(HTTPException) as exc:
        _search(client, status_code=",".join(str(200 + i) for i in range(11)))

    assert exc.value.status_code == 422


# ── Service ID filter ─────────────────────────────────────────────────────────

def test_service_id_in_main_filter_not_pre_queried():
    """service_id is set on the request span (orchestrator.py:84, 93) so it belongs
    in the main filter — no pre-query or 400 cap needed."""
    client = _make_client(["t1"])

    _search(client, service_id="llm0-01-aug")

    assert len(client.captured_pre_queries) == 0, "service_id must not trigger a pre-query"
    assert len(client.captured_main_queries) == 1
    flat = str(client.captured_main_queries[0])
    assert "service_id" in flat and "llm0-01-aug" in flat


def test_service_id_with_many_traces_does_not_return_400():
    """service_id is a plain filter, not subject to the AC-17 keyword cap."""
    client = _make_client([f"t{i}" for i in range(25000)])

    response = _search(client, service_id="busy-service")

    assert response is not None


def test_service_id_and_q_together():
    """service_id goes into the main filter; q gates via trace IDs — both applied."""
    client = _make_client(["t1"])

    _search(client, q="gemma", service_id="llm0-01-aug")

    assert len(client.captured_pre_queries) == 1, "only q= should trigger a pre-query"
    assert len(client.captured_main_queries) == 1
    flat = str(client.captured_main_queries[0])
    assert "service_id" in flat and "llm0-01-aug" in flat
    assert "context.trace_id.keyword" in flat


# ── log_status (status alias) ─────────────────────────────────────────────────

def test_log_status_takes_precedence_over_status_filter():
    """The new `status` param must override the legacy status_filter when both given."""
    client = _make_client(["t1"])

    _search(client, log_status="success", status_filter="failed")

    assert len(client.captured_main_queries) == 1
    flat = str(client.captured_main_queries[0])
    assert "success" in flat
    assert flat.count("attributes.status") == 1


# ── HTTP integration ──────────────────────────────────────────────────────────

def test_http_q_param_triggers_pre_query():
    """Through FastAPI: q is parsed from the query string and triggers a pre-query."""
    client = _make_client(["t1"])

    response = _http_client(client).get(
        "/telemetry/traces/search",
        params={"q": "gemma", "page": 1, "page_size": 10},
        headers={"X-Permission-IDS": ADMIN, "X-Tenant-Id": "9"},
    )

    assert response.status_code == 200, response.text
    assert len(client.captured_pre_queries) == 1


def test_http_invalid_sort_by_returns_422():
    client = _make_client(["t1"])

    response = _http_client(client).get(
        "/telemetry/traces/search",
        params={"sort_by": "badfield"},
        headers={"X-Permission-IDS": ADMIN, "X-Tenant-Id": "9"},
    )

    assert response.status_code == 422


def test_http_invalid_status_code_returns_422():
    client = _make_client(["t1"])

    response = _http_client(client).get(
        "/telemetry/traces/search",
        params={"status_code": "999"},
        headers={"X-Permission-IDS": ADMIN, "X-Tenant-Id": "9"},
    )

    assert response.status_code == 422


def test_http_ac17_returns_400_for_large_keyword_result():
    """AC-17: the HTTP layer must surface the 400 when keyword matches >20,000 traces."""
    client = MagicMock()
    client.search_traces.return_value = {
        "aggregations": {
            "trace_ids": {
                "buckets": [{"key": {"trace_id": f"t{i}"}} for i in range(_MAX_KEYWORD_TRACE_IDS + 1)]
            }
        }
    }

    response = _http_client(client).get(
        "/telemetry/traces/search",
        params={"q": "common"},
        headers={"X-Permission-IDS": ADMIN, "X-Tenant-Id": "9"},
    )

    assert response.status_code == 400
