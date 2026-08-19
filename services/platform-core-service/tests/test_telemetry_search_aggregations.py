"""Unit tests: Logs Dashboard summary cards must reflect the full filtered
total across all pages, not just the current page of results, and Success +
Failures must reconcile with Total Requests (each trace counts once)."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Resolve relative to this file, not the process CWD - pytest run from the
# repo root (e.g. `pytest services/platform-core-service/tests`) has a
# different CWD than running it from inside the service directory, and a
# bare relative path here would raise FileNotFoundError during collection,
# aborting the whole test run rather than just this file.
_TELEMETRY_ROUTE_PATH = Path(__file__).resolve().parents[1] / "app" / "routes" / "telemetry.py"
_spec = importlib.util.spec_from_file_location(
    "app.routes.telemetry", _TELEMETRY_ROUTE_PATH
)
_telemetry_route_mod = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.telemetry"] = _telemetry_route_mod
_spec.loader.exec_module(_telemetry_route_mod)

_collect_all_trace_ids = _telemetry_route_mod._collect_all_trace_ids
_build_traces_map = _telemetry_route_mod._build_traces_map
_compute_full_breakdown = _telemetry_route_mod._compute_full_breakdown
_BREAKDOWN_BATCH_SIZE = _telemetry_route_mod._BREAKDOWN_BATCH_SIZE
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


def test_collect_all_trace_ids_raises_on_missing_aggregations():
    """A response with no "aggregations" key means the query failed (this is
    what OpenSearchTraceClient.search_traces returns on any exception) - it
    must not be treated as "no more matching traces", which would silently
    produce a zero/undercounted breakdown next to a correct Total."""
    client = MagicMock()
    client.search_traces.return_value = {"hits": {"hits": [], "total": {"value": 0}}}

    with pytest.raises(RuntimeError):
        _collect_all_trace_ids(client, {"match_all": {}}, limit=100)


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

    by_level, by_task, truncated = asyncio.run(_compute_full_breakdown(client, ["t1", "t2", "t3"], tenant_filter="tenant-a"))

    assert by_level == {"success": 2, "failure": 1}
    assert sum(by_level.values()) == 3  # reconciles with the 3 traces, no double counting
    assert by_task == {"nmt": 1, "unknown": 2}
    assert truncated is False


def test_compute_full_breakdown_ignores_filter_specific_fields():
    """Classification must not reuse the original filter_query's must/filter
    clauses (e.g. a task_types filter only matches the 'model'/'ai-inference'
    spans, which would hide the 'request' span's real status if reused).
    Asserts directly on the outgoing query shape - a mock that returns the
    same response regardless of what query it receives would pass this test
    whether or not the fix is actually in place, so the query itself is what's
    checked here, not just the classification result."""
    client = MagicMock()
    captured_queries = []

    def search_traces(**kwargs):
        captured_queries.append(kwargs["query"])
        return {"hits": {"hits": [_span_hit("t1", "request", {"status": "failure"})]}}

    client.search_traces.side_effect = search_traces

    by_level, _, _ = asyncio.run(_compute_full_breakdown(client, ["t1"], tenant_filter=None))

    assert by_level == {"failure": 1}
    assert len(captured_queries) == 1
    query_bool = captured_queries[0]["bool"]
    # No "must"/"filter" key - if the original filter_query were reused/merged
    # in, it would show up as one of those here.
    assert set(query_bool.keys()) == {"should", "minimum_should_match"}
    assert query_bool["should"] == [{"match_phrase": {"context.trace_id": "t1"}}]


def test_compute_full_breakdown_batches_large_trace_id_lists():
    """A filtered set larger than one batch must issue multiple span fetches,
    one per _BREAKDOWN_BATCH_SIZE chunk, and still tally every trace."""
    client = MagicMock()
    trace_ids = [f"t{i}" for i in range(_BREAKDOWN_BATCH_SIZE + 5)]

    def search_traces(**kwargs):
        # Echo back one "success" span per trace_id referenced in this batch's query
        should = kwargs["query"]["bool"]["should"]
        batch_ids = [clause["match_phrase"]["context.trace_id"] for clause in should]
        return {"hits": {"hits": [_span_hit(tid, "request", {"status": "success"}) for tid in batch_ids]}}

    client.search_traces.side_effect = search_traces

    by_level, by_task, truncated = asyncio.run(_compute_full_breakdown(client, trace_ids, tenant_filter="tenant-a"))

    assert client.search_traces.call_count == 2  # one full batch + one partial batch
    assert by_level == {"success": len(trace_ids)}
    assert truncated is False


def test_compute_full_breakdown_flags_truncated_batch():
    """Regression test for the review comment on span-count truncation: a
    batch's fetch is capped at len(batch) * _BREAKDOWN_SPAN_CEILING_PER_TRACE
    spans TOTAL (not per trace_id), sorted newest-first, so if the batch's
    real span count exceeds that, the oldest trace_ids in it can silently
    return zero spans while other trace_ids in the same batch still return
    spans normally - `hits` is never fully empty, so a bare "if not hits"
    check can't catch it. Simulates that here: the batch asks about 3
    trace_ids but only 2 come back with spans."""
    client = MagicMock()

    def search_traces(**kwargs):
        # t3 is silently dropped, as if its spans fell outside the size cap
        return {"hits": {"hits": [
            _span_hit("t1", "request", {"status": "success"}),
            _span_hit("t2", "request", {"status": "failure"}),
        ]}}

    client.search_traces.side_effect = search_traces

    by_level, by_task, truncated = asyncio.run(_compute_full_breakdown(client, ["t1", "t2", "t3"], tenant_filter="tenant-a"))

    assert truncated is True
    # The traces that DID come back are still counted correctly
    assert by_level == {"success": 1, "failure": 1}
    assert sum(by_level.values()) == 2  # t3 is undercounted, not fabricated as anything


def test_compute_full_breakdown_empty_trace_ids_skips_fetch():
    client = MagicMock()

    by_level, by_task, truncated = asyncio.run(_compute_full_breakdown(client, [], tenant_filter="tenant-a"))

    assert by_level == {}
    assert by_task == {}
    assert truncated is False
    client.search_traces.assert_not_called()


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
    assert response.aggregations.partial is False


def test_search_traces_flags_partial_when_breakdown_is_capped():
    """Above _MAX_BREAKDOWN_TRACE_IDS, the breakdown covers only a slice of
    the true total - the response must say so via aggregations.partial
    rather than silently presenting a partial Success/Failures split as
    if it were exact."""
    client = MagicMock()
    _telemetry_route_mod._MAX_BREAKDOWN_TRACE_IDS = 2  # lower the cap so the test stays small

    try:
        def search_traces(**kwargs):
            aggs = kwargs.get("aggs") or {}
            if "trace_count" in aggs:
                return {
                    "aggregations": {"trace_count": {"value": 5}},
                    "hits": {"hits": [{"_source": {"context": {"trace_id": "trace-0"}}}]},
                }
            if "trace_ids" in aggs:
                return {"aggregations": {"trace_ids": {"buckets": [
                    {"key": {"trace_id": "trace-0"}}, {"key": {"trace_id": "trace-1"}},
                ]}}}
            hits = [_span_hit("trace-0", "request", {"status": "success"})]
            return {"hits": {"hits": hits}}

        client.search_traces.side_effect = search_traces

        request = _make_request()
        response = asyncio.run(
            search_traces_opensearch(
                request=request, task_types=None, status_filter=None, tenant_id=None,
                start_date=None, end_date=None, page=1, page_size=1, opensearch_client=client,
            )
        )

        assert response.total == 5
        assert response.aggregations.total == 5  # Total Requests is never capped
        assert response.aggregations.partial is True  # but the breakdown is
    finally:
        _telemetry_route_mod._MAX_BREAKDOWN_TRACE_IDS = 20000
