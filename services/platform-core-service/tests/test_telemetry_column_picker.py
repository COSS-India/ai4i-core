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

_TELEMETRY_ROUTE_PATH = Path(__file__).resolve().parents[1] / "app" / "routes" / "telemetry.py"
_spec = importlib.util.spec_from_file_location("app.routes.telemetry", _TELEMETRY_ROUTE_PATH)
_telemetry = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.telemetry"] = _telemetry
_spec.loader.exec_module(_telemetry)

search_traces_opensearch = _telemetry.search_traces_opensearch
_build_page_data = _telemetry._build_page_data
_required_span_types = _telemetry._required_span_types
COLUMN_DEFINITIONS = _telemetry.COLUMN_DEFINITIONS
VALID_COLUMN_KEYS = _telemetry.VALID_COLUMN_KEYS
DEFAULT_COLUMN_KEYS = _telemetry.DEFAULT_COLUMN_KEYS

ADMIN = "1"
TENANT_ADMIN = "5"


def _request(permission_ids: str = ADMIN, tenant_id: str = "9") -> MagicMock:
    req = MagicMock()
    req.headers = {"X-Permission-IDS": permission_ids, "X-Tenant-Id": tenant_id}
    return req


def _hit(trace_id: str, name: str = "request", attrs: dict | None = None) -> dict:
    return {
        "_source": {
            "@timestamp": "2026-10-24T08:00:00Z",
            "name": name,
            "context": {"trace_id": trace_id},
            "attributes": attrs or {},
            "service_name": "ai4x-inference",
        }
    }


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


def _search(client, request=None, **params):
    base = dict(
        task_types=None, status_filter=None, tenant_id=None,
        start_date=None, end_date=None, page=1, page_size=15,
        q=None, log_status=None, status_code=None, service_id=None,
        sort_by=None, sort_order=None, user=None,
        metadata_key=None, metadata_value=None, columns=None,
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

    # The conftest stubs InsufficientPermissionsError with a plain Exception subclass
    # (not HTTPException) so TestClient raises instead of returning 403. Register a
    # handler here so auth tests can assert on the HTTP status code.
    _perm_err = sys.modules["ai4i_core.exceptions"].InsufficientPermissionsError

    @app.exception_handler(_perm_err)
    async def _perm_handler(request, exc):
        return JSONResponse(status_code=403, content={"detail": "Insufficient permissions"})

    return TestClient(app)


# ── _required_span_types ──────────────────────────────────────────────────────

def test_required_span_types_always_includes_request():
    assert "request" in _required_span_types(frozenset({"timestamp", "url", "status"}))


def test_required_span_types_adds_model_for_task_type_column():
    assert "model" in _required_span_types(frozenset({"timestamp", "task_type"}))


def test_required_span_types_adds_model_for_model_column():
    assert "model" in _required_span_types(frozenset({"model"}))


def test_required_span_types_excludes_model_when_not_selected():
    result = _required_span_types(frozenset({"timestamp", "url", "status_code", "latency"}))
    assert "model" not in result
    assert "ai-inference" not in result


def test_required_span_types_default_columns_includes_model():
    """Default columns contain task_type, so the model span is required."""
    assert "model" in _required_span_types(DEFAULT_COLUMN_KEYS)


# ── _build_page_data ──────────────────────────────────────────────────────────

def _base_traces_map(trace_id: str, **overrides) -> dict:
    entry = {
        "trace_id": trace_id,
        "service": "ai4x-inference",
        "task_type": "llm",
        "status": "success",
        "url": "/api/v1/inference",
        "tenant_id": "9",
        "timestamp": "2026-10-24T08:00:00Z",
    }
    entry.update(overrides)
    return {trace_id: entry}


def test_build_page_data_trace_id_always_present():
    """trace_id must appear in every row regardless of selected columns."""
    result = _build_page_data(
        _base_traces_map("t1"),
        [_hit("t1", "request", {"status": "success"})],
        frozenset({"timestamp"}),
        ["t1"],
    )
    assert result[0]["trace_id"] == "t1"


def test_build_page_data_only_selected_columns_in_row():
    """Unselected columns must not appear in the response row."""
    result = _build_page_data(
        _base_traces_map("t1"),
        [_hit("t1", "request", {"status": "success", "url": "/api", "total_time_ms": 100})],
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
    """status_code, error, latency, method come from the request span."""
    result = _build_page_data(
        _base_traces_map("t1"),
        [_hit("t1", "request", {
            "status_code": 500,
            "error": "model timeout",
            "total_time_ms": 1234.5,
            "method": "POST",
        })],
        frozenset({"status_code", "error", "latency", "method"}),
        ["t1"],
    )
    row = result[0]

    assert row["status_code"] == 500
    assert row["error"] == "model timeout"
    assert row["latency"] == 1234.5
    assert row["method"] == "POST"


def test_build_page_data_model_span_fields():
    """model is read from the model span, not the request span."""
    result = _build_page_data(
        _base_traces_map("t1", task_type="llm"),
        [
            _hit("t1", "request", {}),
            _hit("t1", "model", {"model_name": "gemma-7b", "task_type": "llm"}),
        ],
        frozenset({"model", "task_type"}),
        ["t1"],
    )
    row = result[0]

    assert row["model"] == "gemma-7b"
    assert row["task_type"] == "llm"


def test_build_page_data_any_span_fields():
    """application, api_key, end_user, metadata read from first available span."""
    result = _build_page_data(
        _base_traces_map("t1"),
        [_hit("t1", "request", {
            "app_id": "app-123",
            "api_key_id": "key-abc",
            "enduser.id": "user-99",
            "metadata_kv": ["env=prod"],
        })],
        frozenset({"application", "api_key", "end_user", "metadata"}),
        ["t1"],
    )
    row = result[0]

    assert row["application"] == "app-123"
    assert row["api_key"] == "key-abc"
    assert row["end_user"] == "user-99"
    assert row["metadata"] == ["env=prod"]


def test_build_page_data_missing_span_returns_none():
    """If a column's span type is absent, the field value is None."""
    result = _build_page_data(
        _base_traces_map("t1"),
        [_hit("t1", "request", {})],  # no model span
        frozenset({"model"}),
        ["t1"],
    )
    assert result[0]["model"] is None


def test_build_page_data_preserves_sort_order():
    """Output order must match paginated_trace_ids, not the hits order."""
    traces_map = {**_base_traces_map("t1"), **_base_traces_map("t2")}
    hits = [_hit("t2"), _hit("t1")]  # reversed

    result = _build_page_data(traces_map, hits, frozenset({"timestamp"}), ["t1", "t2"])

    assert result[0]["trace_id"] == "t1"
    assert result[1]["trace_id"] == "t2"


def test_build_page_data_skips_trace_not_in_map():
    """trace_ids present in paginated list but absent from traces_map are skipped."""
    result = _build_page_data(
        _base_traces_map("t1"),
        [_hit("t1")],
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
    assert set(row.keys()) == {"trace_id", "timestamp", "status", "task_type", "url", "institution"}


def test_default_column_keys_matches_column_definitions():
    """DEFAULT_COLUMN_KEYS must exactly match entries marked default=True in COLUMN_DEFINITIONS."""
    expected = {col["key"] for col in COLUMN_DEFINITIONS if col["default"]}
    assert DEFAULT_COLUMN_KEYS == expected


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
    """Selecting every valid key → every key present in the response row."""
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
    for key in VALID_COLUMN_KEYS:
        assert key in row, f"Expected column '{key}' missing from row"


def test_each_valid_column_key_accepted_individually():
    """Every key in VALID_COLUMN_KEYS passes validation without raising."""
    client = _make_client(["t1"])

    for key in VALID_COLUMN_KEYS:
        response = _search(client, columns=key)
        assert response is not None


# ── AC-6: error column on failed traces ──────────────────────────────────────

def test_error_and_status_code_columns_on_failed_trace():
    """AC-6: error and status_code are returned for a failed trace."""
    client = _make_client(["t1"], span_hits_by_trace={
        "t1": [_hit("t1", "request", {
            "status": "failed",
            "status_code": 500,
            "error": "Internal server error: model timeout",
            "tenantId": "9",
        })]
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


def test_q_over_256_chars_raises_422():
    """AC-11: 257-char keyword must be rejected with 422."""
    client = _make_client(["t1"])

    with pytest.raises(HTTPException) as exc:
        _search(client, q="a" * 257)

    assert exc.value.status_code == 422


# ── GET /traces/columns endpoint ─────────────────────────────────────────────

def test_columns_endpoint_returns_all_15_columns():
    response = _http_client(_make_client([])).get(
        "/telemetry/traces/columns",
        headers={"X-Permission-IDS": ADMIN, "X-Tenant-Id": "9"},
    )

    assert response.status_code == 200, response.text
    assert len(response.json()) == 15


def test_columns_endpoint_response_fields_per_entry():
    """Each column must have exactly the 6 user-facing fields — no internal ones."""
    response = _http_client(_make_client([])).get(
        "/telemetry/traces/columns",
        headers={"X-Permission-IDS": ADMIN, "X-Tenant-Id": "9"},
    )

    for col in response.json():
        assert set(col.keys()) == {"key", "label", "default", "filterable", "sortable", "keyword_searchable"}
        assert "os_field" not in col
        assert "span" not in col


def test_columns_endpoint_correct_default_flags():
    """Exactly 5 columns have default=True, matching DEFAULT_COLUMN_KEYS."""
    response = _http_client(_make_client([])).get(
        "/telemetry/traces/columns",
        headers={"X-Permission-IDS": ADMIN, "X-Tenant-Id": "9"},
    )

    default_keys = {col["key"] for col in response.json() if col["default"]}
    assert default_keys == DEFAULT_COLUMN_KEYS


def test_columns_endpoint_requires_telemetry_permission():
    """Role 3 (guest) is not in ALLOWED_ROLES — must return 403."""
    response = _http_client(_make_client([])).get(
        "/telemetry/traces/columns",
        headers={"X-Permission-IDS": "3", "X-Tenant-Id": "9"},
    )

    assert response.status_code == 403


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
    if rows:
        row_keys = set(rows[0].keys())
        assert {"timestamp", "status", "task_type", "url", "institution"}.issubset(row_keys)
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
    if rows:
        row_keys = set(rows[0].keys())
        assert "timestamp" in row_keys
        assert "latency" in row_keys
        assert "status" not in row_keys
        assert "url" not in row_keys
