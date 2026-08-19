"""Unit tests: Logs Dashboard summary cards must reflect the full filtered
total across all pages, not just the current page of results, and Success +
Failures must reconcile with Total Requests (each trace counts once).

History:
- v1 bug: GET /telemetry/traces/search built `aggregations.total`/`by_level`/
  `by_task` by counting only `data` (the current page, capped at page_size),
  while the pagination footer already used the correct full-result `total`
  (an OpenSearch cardinality aggregation).
- v2 bug (introduced by the first fix): the replacement used a raw OpenSearch
  `terms` aggregation on `attributes.status`/`attributes.task_type` scoped to
  a trace_id join. Two issues: (a) those fields are mapped `text` with a
  `.keyword` sub-field in this index, so a `terms` agg on the bare field
  throws and gets silently swallowed by the client, producing empty
  aggregations; (b) even after using `.keyword`, bucketing raw span docs by
  status let a trace with disagreeing spans (e.g. a retried request) count
  toward more than one status bucket, so Success + Failures could exceed
  Total.
- Fix: `_compute_full_breakdown` reuses the exact same per-trace extraction
  logic as the table rows (`_build_traces_map` - first non-unknown status
  wins, mirroring the app's own precedence rule) so each trace resolves to
  exactly one status/task bucket.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from unittest.mock import MagicMock

import pytest

_spec = importlib.util.spec_from_file_location(
    "app.routes.telemetry", "app/routes/telemetry.py"
)
_telemetry_route_mod = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.telemetry"] = _telemetry_route_mod
_spec.loader.exec_module(_telemetry_route_mod)

_collect_all_trace_ids = _telemetry_route_mod._collect_all_trace_ids
_build_traces_map = _telemetry_route_mod._build_traces_map
_compute_full_breakdown = _telemetry_route_mod._compute_full_breakdown
_TRACE_ID_FETCH_BATCH_SIZE = _telemetry_route_mod._TRACE_ID_FETCH_BATCH_SIZE
search_traces_opensearch = _telemetry_route_mod.search_traces_opensearch


def _make_request(permission_ids: str = "1", tenant_id: str = "tenant-a") -> MagicMock:
    request = MagicMock()
    request.headers = {"X-Permission-IDS": permission_ids, "X-Tenant-Id": tenant_id}
    return request


def _span_hit(trace_id: str, name: str, attrs: dict, timestamp: str = "2026-06-25T10:01:00Z") -> dict:
    return {
        "_source": {
            "@timestamp": timestamp,
            "name": name,
            "context": {"trace_id": trace_id},
            "attributes": attrs,
            "service_name": "ai4x-inference",
        }
    }


def test_collect_all_trace_ids_paginates_with_after_key():
    """A filtered result set larger than one composite page must be fully enumerated."""
    client = MagicMock()
    client.search_traces.side_effect = [
        {
            "aggregations": {
                "trace_ids": {
                    "buckets": [{"key": {"trace_id": "t1"}}, {"key": {"trace_id": "t2"}}],
                    "after_key": {"trace_id": "t2"},
                }
            }
        },
        {
            "aggregations": {
                "trace_ids": {
                    "buckets": [{"key": {"trace_id": "t3"}}],
                    "after_key": {"trace_id": "t3"},
                }
            }
        },
        # Loop keeps paging while len(trace_ids) < limit and an after_key is present;
        # an empty final page is what actually signals "no more matches" and stops it.
        {"aggregations": {"trace_ids": {"buckets": []}}},
    ]

    result = _collect_all_trace_ids(client, {"match_all": {}}, limit=10)

    assert result == ["t1", "t2", "t3"]
    assert client.search_traces.call_count == 3


def test_collect_all_trace_ids_respects_limit():
    """The safety cap must stop enumeration instead of fetching unboundedly."""
    client = MagicMock()
    client.search_traces.return_value = {
        "aggregations": {
            "trace_ids": {
                "buckets": [{"key": {"trace_id": f"t{i}"}} for i in range(5)],
                "after_key": {"trace_id": "t4"},
            }
        }
    }

    result = _collect_all_trace_ids(client, {"match_all": {}}, limit=3)

    assert len(result) <= 5  # one page can overshoot slightly but must not keep paging
    assert client.search_traces.call_count == 1


def test_collect_all_trace_ids_empty_when_no_matches():
    client = MagicMock()
    client.search_traces.return_value = {"aggregations": {"trace_ids": {"buckets": []}}}

    result = _collect_all_trace_ids(client, {"match_all": {}}, limit=100)

    assert result == []


def test_build_traces_map_prefers_most_recent_status():
    """Hits arrive timestamp-desc; the first non-unknown status wins per trace,
    matching the table-row extraction exactly (not a bare last-value-wins)."""
    hits = [
        _span_hit("t1", "request", {"status": "success"}, timestamp="2026-06-25T10:05:00Z"),
        _span_hit("t1", "model", {"task_type": "nmt"}, timestamp="2026-06-25T10:04:59Z"),
        _span_hit("t1", "request", {"status": "failure"}, timestamp="2026-06-25T10:00:00Z"),
    ]

    traces_map = _build_traces_map(hits, tenant_filter="tenant-a")

    assert traces_map["t1"]["status"] == "success"
    assert traces_map["t1"]["task_type"] == "nmt"


def test_build_traces_map_ignores_hits_without_trace_id():
    hits = [{"_source": {"context": {}, "attributes": {}}}]

    traces_map = _build_traces_map(hits, tenant_filter="tenant-a")

    assert traces_map == {}


def test_compute_full_breakdown_counts_each_trace_exactly_once():
    """The bug this guards against: a trace with a success span AND a failure
    span (e.g. a retried request) must land in exactly one bucket, so
    Success + Failures reconciles with Total instead of exceeding it."""
    client = MagicMock()
    client.search_traces.return_value = {
        "hits": {
            "hits": [
                _span_hit("t1", "request", {"status": "success"}, timestamp="2026-06-25T10:05:00Z"),
                _span_hit("t1", "request", {"status": "failure"}, timestamp="2026-06-25T10:00:00Z"),
                _span_hit("t2", "request", {"status": "success"}),
                _span_hit("t2", "model", {"task_type": "nmt"}),
                _span_hit("t3", "request", {"status": "failure"}),
            ]
        }
    }

    by_level, by_task = _compute_full_breakdown(client, ["t1", "t2", "t3"], tenant_filter="tenant-a")

    assert by_level == {"success": 2, "failure": 1}
    assert sum(by_level.values()) == 3  # reconciles with the 3 traces, no double counting
    assert by_task == {"nmt": 1, "unknown": 2}


def test_compute_full_breakdown_batches_large_trace_id_lists():
    """A filtered set larger than one batch must issue multiple span fetches,
    one per _TRACE_ID_FETCH_BATCH_SIZE chunk, and still tally every trace."""
    client = MagicMock()
    trace_ids = [f"t{i}" for i in range(_TRACE_ID_FETCH_BATCH_SIZE + 5)]

    def search_traces(**kwargs):
        # Echo back one "success" span per trace_id referenced in this batch's query
        should = kwargs["query"]["bool"]["should"]
        batch_ids = [clause["match_phrase"]["context.trace_id"] for clause in should]
        return {"hits": {"hits": [_span_hit(tid, "request", {"status": "success"}) for tid in batch_ids]}}

    client.search_traces.side_effect = search_traces

    by_level, by_task = _compute_full_breakdown(client, trace_ids, tenant_filter="tenant-a")

    assert client.search_traces.call_count == 2  # one full batch + one partial batch
    assert by_level == {"success": len(trace_ids)}


def test_search_traces_summary_matches_pagination_total_and_reconciles():
    """End-to-end: aggregations.total must equal the full-result total (not
    len(data)), and Success + Failures must reconcile with Total instead of
    double-counting a trace whose spans disagree."""
    client = MagicMock()

    page_trace_ids = [f"trace-{i}" for i in range(3)]
    all_trace_ids = page_trace_ids + ["trace-extra"]

    def search_traces(**kwargs):
        aggs = kwargs.get("aggs") or {}
        if "trace_count" in aggs:
            return {
                "aggregations": {"trace_count": {"value": 4}},
                "hits": {"hits": [{"_source": {"context": {"trace_id": tid}}} for tid in page_trace_ids]},
            }
        if "trace_ids" in aggs:
            return {"aggregations": {"trace_ids": {"buckets": [
                {"key": {"trace_id": tid}} for tid in all_trace_ids
            ]}}}
        # Span fetch (Step 3 for the page, or _compute_full_breakdown's batch fetch)
        should = kwargs["query"]["bool"]["should"]
        batch_ids = [clause["match_phrase"]["context.trace_id"] for clause in should]
        hits = []
        for tid in batch_ids:
            if tid == "trace-extra":
                # A retried request: disagreeing spans for the same trace. Real OpenSearch
                # sorts @timestamp desc, so the most recent span (success) comes first.
                hits.append(_span_hit(tid, "request", {"status": "success"}, timestamp="2026-06-25T10:00:00Z"))
                hits.append(_span_hit(tid, "request", {"status": "failure"}, timestamp="2026-06-25T09:00:00Z"))
            else:
                hits.append(_span_hit(tid, "request", {"status": "success", "tenantId": "tenant-a"}))
        return {"hits": {"hits": hits}}

    client.search_traces.side_effect = search_traces

    request = _make_request()
    response = asyncio.run(
        search_traces_opensearch(
            request=request,
            task_types="nmt",
            status_filter=None,
            tenant_id=None,
            start_date="2026-06-25T10:01:00",
            end_date="2026-06-25T10:05:00",
            page=1,
            page_size=3,
            opensearch_client=client,
        )
    )

    assert len(response.data) == 3  # the page itself is unaffected
    assert response.total == 4  # pagination footer total
    assert response.aggregations.total == 4  # Total Requests card
    # trace-extra's most recent span says success, so it resolves to exactly one bucket
    assert response.aggregations.by_level == {"success": 4}
    assert sum(response.aggregations.by_level.values()) == response.aggregations.total
