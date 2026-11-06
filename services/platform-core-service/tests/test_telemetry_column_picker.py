"""Unit tests: column picker — GET /traces/columns, columns param on search,
_build_page_data, _required_span_types.

AC-6: error + status_code columns exposed on failed traces
AC-7: columns param → only selected fields returned per row; /traces/columns for picker UI
AC-8: no columns param → default 5 columns returned
AC-11: q > 256 chars → 422
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

# Load schemas first — telemetry_params imports from it, so it must be in
# sys.modules before the service and route modules are exec'd.
_SCHEMAS_PATH = Path(__file__).resolve().parents[1] / "app" / "schemas" / "telemetry.py"
_schemas_spec = importlib.util.spec_from_file_location("app.schemas.telemetry", _SCHEMAS_PATH)
_schemas = importlib.util.module_from_spec(_schemas_spec)
sys.modules["app.schemas.telemetry"] = _schemas
_schemas_spec.loader.exec_module(_schemas)

# Load the service next — the route imports from it.
_TELEMETRY_SERVICE_PATH = Path(__file__).resolve().parents[1] / "app" / "services" / "telemetry_service.py"
_svc_spec = importlib.util.spec_from_file_location("app.services.telemetry_service", _TELEMETRY_SERVICE_PATH)
_telemetry_svc = importlib.util.module_from_spec(_svc_spec)
sys.modules["app.services.telemetry_service"] = _telemetry_svc
_svc_spec.loader.exec_module(_telemetry_svc)

_TELEMETRY_ROUTE_PATH = Path(__file__).resolve().parents[1] / "app" / "routes" / "telemetry.py"
_spec = importlib.util.spec_from_file_location("app.routes.telemetry", _TELEMETRY_ROUTE_PATH)
_telemetry = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.telemetry"] = _telemetry
_spec.loader.exec_module(_telemetry)

search_traces_opensearch = _telemetry.search_traces_opensearch
_build_page_data = _telemetry_svc._build_page_data
_build_search_filter_clauses = _telemetry_svc._build_search_filter_clauses
_SpanFilterParams = _telemetry_svc._SpanFilterParams
_inline_span_filters = _telemetry_svc._inline_span_filters
VALID_COLUMN_KEYS = _schemas.VALID_COLUMN_KEYS
DEFAULT_COLUMN_KEYS = _schemas.DEFAULT_COLUMN_KEYS

ADMIN = "1"
TENANT_ADMIN = "5"


def _request(permission_ids: str = ADMIN, tenant_id: str = "9") -> MagicMock:
    req = MagicMock()
    req.headers = {"X-Permission-IDS": permission_ids, "X-Tenant-Id": tenant_id}
    return req


def _hit(trace_id: str, name: str = "request", attrs: dict | None = None, status_description: str | None = None) -> dict:
    source: dict = {
        "@timestamp": "2026-10-24T08:00:00Z",
        "name": name,
        "context": {"trace_id": trace_id},
        "attributes": attrs or {},
        "service_name": "ai4x-inference",
    }
    if status_description is not None:
        source["status"] = {"description": status_description}
    return {"_source": source}


def _make_client(trace_ids: list, span_hits_by_trace: dict | None = None):
    """Mock OpenSearch client that handles all three query shapes in a full search flow.

    span_hits_by_trace: maps trace_id → list of _hit() dicts for Step 3.
    Defaults to a single request span with success + tenantId=9 per trace.
    """
    client = MagicMock()

    def search_traces(**kwargs):
        aggs = kwargs.get("aggs") or {}
        query = kwargs.get("query", {})

        if "trace_count" in aggs:
            return {
                "aggregations": {"trace_count": {"value": len(trace_ids)}},
                "hits": {"hits": [{"_source": {"context": {"trace_id": t}}} for t in trace_ids]},
            }

        if "trace_ids" in aggs:
            return {
                "aggregations": {
                    "trace_ids": {"buckets": [{"key": {"trace_id": t}} for t in trace_ids]}
                }
            }

        # Span fetch — extract trace IDs from either query shape:
        # direct: bool.should / filtered: bool.must[0].bool.should
        query_bool = query.get("bool", {})
        should = query_bool.get("should") or (
            (query_bool.get("must") or [{}])[0].get("bool", {}).get("should", [])
        )
        batch_ids = [c["match_phrase"]["context.trace_id"] for c in should]

        hits = []
        for tid in batch_ids:
            if span_hits_by_trace and tid in span_hits_by_trace:
                hits.extend(span_hits_by_trace[tid])
            else:
                hits.append(_hit(tid, "request", {
                    "status": "success", "tenantId": "9",
                    "task_type": "llm", "url": "/api/v1/inference",
                }))
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


def _http_client(opensearch_client):
    app = FastAPI()
    app.include_router(_telemetry.router)
    app.dependency_overrides[_telemetry._get_opensearch_client] = lambda: opensearch_client

    # The conftest stubs InsufficientPermissionsError with a plain Exception subclass
    # (not HTTPException) so TestClient raises instead of returning 403. Register a
    # handler here so auth tests can assert on the HTTP status code.
    _perm_err = sys.modules["ai4i_core.exceptions"].InsufficientPermissionsError

    @app.exception_handler(_perm_err)
    async def _perm_handler(request, exc):
        return JSONResponse(status_code=403, content={"detail": "Insufficient permissions"})

    return TestClient(app)


# ── _build_page_data ──────────────────────────────────────────────────────────

def _base_traces_map(trace_id: str, **overrides) -> dict:
    entry = {
        "trace_id":   trace_id,
        "service":    "ai4x-inference",
        "task_type":  "llm",
        "status":     "success",
        "url":        "/api/v1/inference",
        "tenant_id":  "9",
        "timestamp":  "2026-10-24T08:00:00Z",
        "latency":    None,
        "status_code": None,
        "method":     None,
        "error":      None,
        "model_name": None,
        "app_id":     None,
        "end_user":   None,
        "metadata":   None,
    }
    entry.update(overrides)
    return {trace_id: entry}


def test_build_page_data_trace_id_always_present():
    """trace_id must appear in every row regardless of selected columns."""
    result = _build_page_data(
        _base_traces_map("t1"),
        frozenset({"timestamp"}),
        ["t1"],
    )
    assert result[0]["trace_id"] == "t1"


def test_build_page_data_only_selected_columns_in_row():
    """Unselected columns must not appear in the response row."""
    result = _build_page_data(
        _base_traces_map("t1"),
        frozenset({"timestamp", "status"}),
        ["t1"],
    )
    row = result[0]

    assert "timestamp" in row
    assert "status" in row
    assert "url" not in row
    assert "latency" not in row
    assert "task_type" not in row


def test_build_page_data_request_span_fields():
    """status_code, latency, method are read from traces_map (set by _build_traces_map)."""
    result = _build_page_data(
        _base_traces_map("t1", status_code=500, latency=1234.5, method="POST"),
        frozenset({"status_code", "latency", "method"}),
        ["t1"],
    )
    row = result[0]

    assert row["status_code"] == 500
    assert row["latency"] == 1234.5
    assert row["method"] == "POST"


def test_build_page_data_model_span_fields():
    """model and task_type are read from traces_map (set by _build_traces_map)."""
    result = _build_page_data(
        _base_traces_map("t1", task_type="llm", model_name="gemma-7b"),
        frozenset({"model", "task_type"}),
        ["t1"],
    )
    row = result[0]

    assert row["model"] == "gemma-7b"
    assert row["task_type"] == "llm"


def test_build_page_data_any_span_fields():
    """application, end_user, metadata are read from traces_map (set by _build_traces_map)."""
    result = _build_page_data(
        _base_traces_map("t1", app_id="app-123", end_user="user-99", metadata=["env=prod"]),
        frozenset({"application", "end_user", "metadata"}),
        ["t1"],
    )
    row = result[0]

    assert row["application"] == "app-123"
    assert row["end_user"] == "user-99"
    assert row["metadata"] == ["env=prod"]


def test_build_page_data_missing_span_returns_none():
    """If a column has no value in traces_map, the field value is None."""
    result = _build_page_data(
        _base_traces_map("t1"),  # model_name=None by default
        frozenset({"model"}),
        ["t1"],
    )
    assert result[0]["model"] is None


def test_build_page_data_preserves_sort_order():
    """Output order must match paginated_trace_ids, not insertion order."""
    traces_map = {**_base_traces_map("t1"), **_base_traces_map("t2")}

    result = _build_page_data(traces_map, frozenset({"timestamp"}), ["t1", "t2"])

    assert result[0]["trace_id"] == "t1"
    assert result[1]["trace_id"] == "t2"


def test_build_page_data_skips_trace_not_in_map():
    """trace_ids present in paginated list but absent from traces_map are skipped."""
    result = _build_page_data(
        _base_traces_map("t1"),
        frozenset({"timestamp"}),
        ["t1", "t_missing"],
    )
    assert len(result) == 1
    assert result[0]["trace_id"] == "t1"


# ── AC-8: default columns ─────────────────────────────────────────────────────

def test_no_columns_param_returns_default_5_fields():
    """AC-8: omitting columns → exactly the 5 default fields per row."""
    client = _make_client(["t1"])

    response = _search(client)

    row = response.data[0]
    assert set(row.keys()) == {"trace_id", "timestamp", "status", "task_type", "url", "tenant_id"}


def test_default_column_keys_are_valid():
    """DEFAULT_COLUMN_KEYS must be a subset of VALID_COLUMN_KEYS."""
    assert DEFAULT_COLUMN_KEYS <= VALID_COLUMN_KEYS


# ── AC-7: custom columns ──────────────────────────────────────────────────────

def test_custom_columns_returns_only_selected_fields():
    """AC-7: specified columns appear in response; unspecified ones do not."""
    client = _make_client(["t1"], span_hits_by_trace={
        "t1": [_hit("t1", "request", {
            "status": "success", "total_time_ms": 500.0, "status_code": 200, "tenantId": "9",
        })]
    })

    response = _search(client, columns="timestamp,latency,status_code")

    row = response.data[0]
    assert "timestamp" in row
    assert "latency" in row
    assert "status_code" in row
    assert "status" not in row
    assert "url" not in row
    assert "task_type" not in row


def test_single_column_returns_only_that_field_plus_trace_id():
    client = _make_client(["t1"])

    response = _search(client, columns="timestamp")

    assert set(response.data[0].keys()) == {"trace_id", "timestamp"}


def test_all_valid_columns_selected_returns_all_fields():
    """Selecting every valid key → every key present in the response row.

    Checks only columns that _build_page_data currently extracts. Columns backed
    by TraceSpanAttributes but not yet extracted (input_tokens, output_tokens,
    input_type, output_type, model_version) are valid to request but not yet
    populated — they are omitted from this assertion intentionally.
    """
    _EXTRACTED_COLUMNS = {
        "timestamp", "status", "task_type", "url", "tenant_id",
        "status_code", "service", "model", "latency", "application",
        "end_user", "metadata", "method",
    }
    client = _make_client(["t1"], span_hits_by_trace={
        "t1": [
            _hit("t1", "request", {
                "status": "success", "url": "/api", "status_code": 200,
                "total_time_ms": 100, "method": "POST", "tenantId": "9",
            }),
            _hit("t1", "model", {"task_type": "llm", "model_name": "gemma-7b"}),
        ]
    })

    response = _search(client, columns=",".join(VALID_COLUMN_KEYS))

    row = response.data[0]
    for key in _EXTRACTED_COLUMNS:
        assert key in row, f"Expected column '{key}' missing from row"


def test_each_valid_column_key_accepted_individually():
    """Every key in VALID_COLUMN_KEYS passes validation without raising."""
    client = _make_client(["t1"])

    for key in VALID_COLUMN_KEYS:
        response = _search(client, columns=key)
        assert response is not None


# ── AC-6: error column on failed traces ──────────────────────────────────────

def test_error_and_status_code_columns_on_failed_trace():
    """AC-6: error and status_code are returned for a failed trace (admin only).

    error is read from the span's status.description (not span attributes),
    so the hit must carry status.description in _source.
    """
    client = _make_client(["t1"], span_hits_by_trace={
        "t1": [_hit(
            "t1", "request",
            {"status": "failed", "status_code": 500, "tenantId": "9"},
            status_description="Internal server error: model timeout",
        )]
    })

    response = _search(client, log_status="failed", columns="status,status_code,error,timestamp")

    row = response.data[0]
    assert row["status"] == "failed"
    assert row["status_code"] == 500
    assert row["error"] == "Internal server error: model timeout"


def test_error_column_is_none_on_success_trace():
    """error field is None when the trace has no error attribute."""
    client = _make_client(["t1"], span_hits_by_trace={
        "t1": [_hit("t1", "request", {"status": "success", "status_code": 200, "tenantId": "9"})]
    })

    response = _search(client, columns="status,status_code,error")

    assert response.data[0]["error"] is None


# ── Column validation ─────────────────────────────────────────────────────────

def test_unknown_column_key_raises_422():
    """AC-7: unknown key in columns param → 422 with the bad key named."""
    client = _make_client(["t1"])

    with pytest.raises(HTTPException) as exc:
        _search(client, columns="timestamp,nonexistent_col")

    assert exc.value.status_code == 422
    assert "nonexistent_col" in str(exc.value.detail)


def test_multiple_unknown_keys_all_listed_in_error():
    client = _make_client(["t1"])

    with pytest.raises(HTTPException) as exc:
        _search(client, columns="bad_one,bad_two,timestamp")

    assert exc.value.status_code == 422
    assert "bad_one" in str(exc.value.detail)
    assert "bad_two" in str(exc.value.detail)


# ── AC-11: q > 256 chars ─────────────────────────────────────────────────────

def test_q_exactly_256_chars_is_accepted():
    """AC-11 boundary: 256-char keyword is the max allowed — must pass."""
    client = _make_client(["t1"])

    response = _search(client, q="a" * 256)

    assert response is not None


# ── HTTP integration ──────────────────────────────────────────────────────────

def test_http_unknown_column_returns_422():
    response = _http_client(_make_client(["t1"])).get(
        "/telemetry/traces/search",
        params={"columns": "timestamp,bad_column"},
        headers={"X-Permission-IDS": ADMIN, "X-Tenant-Id": "9"},
    )

    assert response.status_code == 422


def test_http_valid_columns_returns_200():
    response = _http_client(_make_client(["t1"])).get(
        "/telemetry/traces/search",
        params={"columns": "timestamp,status,latency"},
        headers={"X-Permission-IDS": ADMIN, "X-Tenant-Id": "9"},
    )

    assert response.status_code == 200, response.text


def test_http_q_over_256_chars_returns_422():
    """AC-11: via HTTP, q > 256 chars → 422."""
    response = _http_client(_make_client(["t1"])).get(
        "/telemetry/traces/search",
        params={"q": "a" * 257},
        headers={"X-Permission-IDS": ADMIN, "X-Tenant-Id": "9"},
    )

    assert response.status_code == 422


def test_http_default_columns_on_no_columns_param():
    """AC-8: via HTTP, no columns param → default 5 fields per row."""
    response = _http_client(_make_client(["t1"])).get(
        "/telemetry/traces/search",
        params={"page": 1, "page_size": 10},
        headers={"X-Permission-IDS": ADMIN, "X-Tenant-Id": "9"},
    )

    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    assert rows, "expected at least one row in response"
    row_keys = set(rows[0].keys())
    assert {"timestamp", "status", "task_type", "url", "tenant_id"}.issubset(row_keys)
    assert "latency" not in row_keys
    assert "model" not in row_keys
    assert "error" not in row_keys


def test_http_columns_response_contains_only_selected_keys():
    """AC-7: via HTTP, only the requested column keys appear in each data row."""
    client = _make_client(["t1"], span_hits_by_trace={
        "t1": [_hit("t1", "request", {
            "status": "success", "total_time_ms": 200.0, "tenantId": "9",
        })]
    })

    response = _http_client(client).get(
        "/telemetry/traces/search",
        params={"columns": "timestamp,latency"},
        headers={"X-Permission-IDS": ADMIN, "X-Tenant-Id": "9"},
    )

    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    assert rows, "expected at least one row in response"
    row_keys = set(rows[0].keys())
    assert "timestamp" in row_keys
    assert "latency" in row_keys
    assert "status" not in row_keys
    assert "url" not in row_keys


# ── New filter params: clause building ───────────────────────────────────────

def test_method_filter_adds_attribute_method_clause():
    # method is span-exclusive (owned by "request"), so it lands in span_groups,
    # not filter_clauses directly — inline it the same way search_traces() does
    # when there's no cross-span conflict (<=1 group).
    clauses, span_groups = _build_search_filter_clauses(
        [], None, None, None, None, None, None, [], False, None,
        span_filters=_SpanFilterParams(method="POST"),
    )
    _inline_span_filters(span_groups, clauses)
    assert any("attributes.method" in str(c) for c in clauses)


def test_model_filter_adds_attribute_model_name_clause():
    clauses, span_groups = _build_search_filter_clauses(
        [], None, None, None, None, None, None, [], False, None,
        span_filters=_SpanFilterParams(model="gemma-7b"),
    )
    _inline_span_filters(span_groups, clauses)
    assert any("attributes.model_name" in str(c) for c in clauses)


def test_error_filter_adds_status_description_clause():
    clauses, _ = _build_search_filter_clauses(
        [], None, None, None, None, None, None, [], False, None,
        span_filters=_SpanFilterParams(error="timeout"),
    )
    assert any("status.description" in str(c) and "timeout" in str(c) for c in clauses)


def test_service_filter_adds_service_name_clause():
    clauses, _ = _build_search_filter_clauses(
        [], None, None, None, None, None, None, [], False, None,
        span_filters=_SpanFilterParams(service="inference-service"),
    )
    assert {"match_phrase": {"service_name": "inference-service"}} in clauses


def test_no_new_filters_adds_no_extra_clauses():
    """With all new filters None, clause count is unchanged."""
    base_clauses, _ = _build_search_filter_clauses(
        [], None, None, None, None, None, None, [], False, None
    )
    new_clauses, _ = _build_search_filter_clauses(
        [], None, None, None, None, None, None, [], False, None,
        span_filters=_SpanFilterParams(method=None, model=None, error=None, service=None),
    )
    assert base_clauses == new_clauses


# ── needs_request_anchor suppression when model filter is active ─────────────

def test_model_filter_suppresses_request_anchor_with_non_timestamp_sort():
    """sort_by=url normally triggers needs_request_anchor, but model filter must disable it.

    If the anchor were added, the query would include {"term": {"name": "request"}},
    which can never match a span that also has attributes.model_name — producing zero results.
    """
    client = _make_client(["t1"])
    _search(client, model="gemma-7b", sort_by="url")

    for call in client.search_traces.call_args_list:
        query = call.kwargs.get("query", {})
        must_clauses = query.get("bool", {}).get("must", [])
        assert {"term": {"name": "request"}} not in must_clauses, (
            "request anchor must not be applied when model filter is active"
        )


def test_request_anchor_still_applied_without_model_filter():
    """sort_by=url without model filter must still anchor to request spans."""
    client = _make_client(["t1"])
    _search(client, sort_by="url")

    anchor_found = any(
        {"term": {"name": "request"}} in call.kwargs.get("query", {}).get("bool", {}).get("must", [])
        for call in client.search_traces.call_args_list
    )
    assert anchor_found, "request anchor must be present when sort_by=url and no model filter"


# ── HTTP integration: new filter params accepted ─────────────────────────────

def test_http_method_filter_returns_200():
    response = _http_client(_make_client(["t1"])).get(
        "/telemetry/traces/search",
        params={"method": "POST"},
        headers={"X-Permission-IDS": ADMIN, "X-Tenant-Id": "9"},
    )
    assert response.status_code == 200, response.text


def test_http_model_filter_returns_200():
    response = _http_client(_make_client(["t1"])).get(
        "/telemetry/traces/search",
        params={"model": "gemma-7b"},
        headers={"X-Permission-IDS": ADMIN, "X-Tenant-Id": "9"},
    )
    assert response.status_code == 200, response.text


def test_http_error_filter_returns_200():
    response = _http_client(_make_client(["t1"])).get(
        "/telemetry/traces/search",
        params={"error": "timeout"},
        headers={"X-Permission-IDS": ADMIN, "X-Tenant-Id": "9"},
    )
    assert response.status_code == 200, response.text


def test_http_service_filter_returns_200():
    response = _http_client(_make_client(["t1"])).get(
        "/telemetry/traces/search",
        params={"service": "inference-service"},
        headers={"X-Permission-IDS": ADMIN, "X-Tenant-Id": "9"},
    )
    assert response.status_code == 200, response.text
