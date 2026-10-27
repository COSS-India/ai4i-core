"""Trace view: service-fallback attempts are grouped and labelled (AI4IDS-3488).

Stored span names stay "model" / "ai-inference" (billing reads ai-inference by
name); GET /traces/{id} orders spans by attributes.attempt and labels a
fallback attempt's spans "fallback model" / "fallback ai-inference".
"""
import importlib.util
import sys
from pathlib import Path

# Loaded by file path, like test_telemetry_column_picker.py: importing
# app.routes eagerly imports every route module.
_TELEMETRY_ROUTE_PATH = Path(__file__).resolve().parents[1] / "app" / "routes" / "telemetry.py"
_spec = importlib.util.spec_from_file_location("app.routes.telemetry", _TELEMETRY_ROUTE_PATH)
_telemetry = importlib.util.module_from_spec(_spec)
sys.modules["app.routes.telemetry"] = _telemetry
_spec.loader.exec_module(_telemetry)

_span_display_name = _telemetry._span_display_name
_span_sort_key = _telemetry._span_sort_key


def _span(name, attempt=None):
    attrs = {} if attempt is None else {"attempt": attempt}
    return {"name": name, "attributes": attrs}


def _view(spans):
    ordered = sorted(spans, key=_span_sort_key)
    return [_span_display_name(s) for s in ordered]


def test_failed_over_request_reads_in_attempt_order():
    # Arrival order from OpenSearch is arbitrary.
    spans = [
        _span("ai-inference", 1),
        _span("model", 0),
        _span("fallback request", 1),
        _span("request"),
        _span("ai-inference", 0),
        _span("model", 1),
    ]
    assert _view(spans) == [
        "request", "model", "ai-inference",
        "fallback request", "fallback model", "fallback ai-inference",
    ]


def test_second_fallback_is_numbered():
    spans = [
        _span("request"), _span("model", 0), _span("ai-inference", 0),
        _span("fallback request", 1), _span("model", 1), _span("ai-inference", 1),
        _span("fallback request", 2), _span("model", 2), _span("ai-inference", 2),
    ]
    assert _view(spans)[-3:] == ["fallback 2 request", "fallback 2 model", "fallback 2 ai-inference"]


def test_request_without_fallback_is_unchanged():
    spans = [_span("ai-inference"), _span("request"), _span("model")]
    assert _view(spans) == ["request", "model", "ai-inference"]


def test_bad_attempt_value_is_treated_as_the_requested_service():
    assert _span_display_name(_span("model", "x")) == "model"
