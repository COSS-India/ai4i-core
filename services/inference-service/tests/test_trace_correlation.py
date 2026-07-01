"""
Unit tests — verify that inference spans carry the request correlation ID
(seeded by RequestMiddleware from X-Correlation-ID) in context.trace_id,
not the OTel SDK's own unrelated trace ID.
"""

import json
import logging
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import ai4i_core.context as ctx


CORR_ID = "aabbccdd11223344aabbccdd11223344"


@pytest.fixture(autouse=True)
def reset_context():
    ctx._trace_id_var.set(None)
    ctx._tenant_id_var.set(None)
    ctx._user_id_var.set(None)
    yield
    ctx._trace_id_var.set(None)
    ctx._tenant_id_var.set(None)
    ctx._user_id_var.set(None)


def _capture_log(logger_name: str, fn) -> str:
    """Run fn() and return every line it emitted at INFO+ on logger_name."""
    buf = StringIO()
    h = logging.StreamHandler(buf)
    h.setLevel(logging.DEBUG)
    log = logging.getLogger(logger_name)
    orig_level = log.level
    log.setLevel(logging.DEBUG)
    log.addHandler(h)
    try:
        fn()
    finally:
        log.removeHandler(h)
        log.setLevel(orig_level)
    return buf.getvalue().strip()


def _mock_span(trace_id_int: int = 0xCAFEBABE00000000CAFEBABE00000000,
               span_id_int: int = 0x1234567890ABCDEF,
               attrs: dict = None) -> MagicMock:
    """Build a minimal span mock with a real-looking span context."""
    sc = MagicMock()
    sc.trace_id = trace_id_int
    sc.span_id = span_id_int
    sc.trace_state = ""
    span = MagicMock()
    span.get_span_context.return_value = sc
    span.attributes = attrs or {}
    span.name = "request"
    span.parent = None
    span.kind = "SpanKind.INTERNAL"
    span.start_time = 0
    span.end_time = 1_000_000_000
    span.status.status_code = "OK"
    span.status.description = None
    return span


def _make_exporter():
    with patch("trace.setup.settings") as s:
        s.KAFKA_ENABLED = False
        s.KAFKA_TOPIC_OTEL_TRACE = "otel-traces"
        from trace.setup import LoggerSpanExporter
        return LoggerSpanExporter()


# ── get_context_attributes ────────────────────────────────────────────────────

class TestGetContextAttributes:
    def test_includes_correlation_id(self):
        from trace.request_span import get_context_attributes
        ctx.set_trace_id(CORR_ID)
        ctx.set_tenant_id("t-001")
        attrs = get_context_attributes()
        assert attrs["correlation_id"] == CORR_ID
        assert attrs["tenantId"] == "t-001"

    def test_omits_correlation_id_when_not_set(self):
        from trace.request_span import get_context_attributes
        attrs = get_context_attributes()
        assert "correlation_id" not in attrs

    def test_still_returns_user_without_trace(self):
        from trace.request_span import get_context_attributes
        ctx.set_user_id("u-99")
        attrs = get_context_attributes()
        assert attrs.get("userId") == "u-99"
        assert "correlation_id" not in attrs


# ── log_span_attributes ───────────────────────────────────────────────────────

class TestLogSpanAttributes:
    def test_uses_correlation_id_as_trace_id(self):
        from trace.request_span import log_span_attributes
        span = _mock_span(attrs={"correlation_id": CORR_ID, "total_time_ms": 42.0})

        raw = _capture_log(
            "trace.request_span",
            lambda: log_span_attributes("request", span, dict(span.attributes)),
        )

        out = json.loads(raw)
        assert out["context"]["trace_id"] == CORR_ID

    def test_preserves_otel_trace_id(self):
        from trace.request_span import log_span_attributes
        OTEL_INT = 0xDEADBEEF00000000DEADBEEF00000000
        span = _mock_span(trace_id_int=OTEL_INT, attrs={"correlation_id": CORR_ID})
        expected_otel = f"0x{OTEL_INT:032x}"

        raw = _capture_log(
            "trace.request_span",
            lambda: log_span_attributes("request", span, dict(span.attributes)),
        )

        out = json.loads(raw)
        assert out["context"]["otel_trace_id"] == expected_otel
        assert out["context"]["trace_id"] == CORR_ID
        assert out["context"]["otel_trace_id"] != CORR_ID

    def test_falls_back_to_otel_id_when_no_correlation(self):
        from trace.request_span import log_span_attributes
        OTEL_INT = 0xDEADBEEF00000000DEADBEEF00000000
        span = _mock_span(trace_id_int=OTEL_INT, attrs={})
        expected_otel = f"0x{OTEL_INT:032x}"

        raw = _capture_log(
            "trace.request_span",
            lambda: log_span_attributes("request", span, {}),
        )

        out = json.loads(raw)
        assert out["context"]["trace_id"] == expected_otel
        assert out["context"]["otel_trace_id"] == expected_otel


# ── LoggerSpanExporter ────────────────────────────────────────────────────────

class TestLoggerSpanExporter:
    def test_uses_correlation_id_from_span_attributes(self):
        exporter = _make_exporter()
        span = _mock_span(attrs={"correlation_id": CORR_ID, "status": "success"})

        raw = _capture_log("trace.setup", lambda: exporter.export([span]))

        out = json.loads(raw)
        assert out["context"]["trace_id"] == CORR_ID

    def test_preserves_otel_trace_id(self):
        exporter = _make_exporter()
        OTEL_INT = 0xCAFEBABE00000000CAFEBABE00000000
        span = _mock_span(trace_id_int=OTEL_INT, attrs={"correlation_id": CORR_ID})
        expected_otel = f"0x{OTEL_INT:032x}"

        raw = _capture_log("trace.setup", lambda: exporter.export([span]))

        out = json.loads(raw)
        assert out["context"]["otel_trace_id"] == expected_otel
        assert out["context"]["otel_trace_id"] != CORR_ID

    def test_falls_back_to_otel_id_when_no_correlation(self):
        exporter = _make_exporter()
        OTEL_INT = 0xCAFEBABE00000000CAFEBABE00000000
        span = _mock_span(trace_id_int=OTEL_INT, attrs={})
        expected_otel = f"0x{OTEL_INT:032x}"

        raw = _capture_log("trace.setup", lambda: exporter.export([span]))

        out = json.loads(raw)
        assert out["context"]["trace_id"] == expected_otel
        assert out["context"]["otel_trace_id"] == expected_otel

    def test_background_thread_safety(self):
        """Exporter reads correlation_id from span.attributes only — never get_trace_id()."""
        exporter = _make_exporter()
        span = _mock_span(attrs={"correlation_id": CORR_ID})

        # Context vars empty — simulates background thread after request ends
        assert ctx.get_trace_id() is None

        raw = _capture_log("trace.setup", lambda: exporter.export([span]))

        out = json.loads(raw)
        assert out["context"]["trace_id"] == CORR_ID


# ── end-to-end: context var → span attribute → log ───────────────────────────

class TestEndToEnd:
    def test_correlation_id_flows_from_context_to_log(self):
        """
        Simulates the full in-request path:
        middleware sets trace_id → get_context_attributes() captures it as a
        span attribute → log_span_attributes() uses it as context.trace_id.
        """
        from trace.request_span import get_context_attributes, log_span_attributes

        ctx.set_trace_id(CORR_ID)
        ctx.set_tenant_id("tenant-xyz")

        attrs = get_context_attributes()
        attrs["total_time_ms"] = 120.5
        attrs["status"] = "success"
        assert attrs["correlation_id"] == CORR_ID

        OTEL_INT = 0x1A2B3C4D5E6F7A8B1A2B3C4D5E6F7A8B
        span = _mock_span(trace_id_int=OTEL_INT, attrs=attrs)

        raw = _capture_log(
            "trace.request_span",
            lambda: log_span_attributes("request", span, attrs),
        )
        out = json.loads(raw)

        assert out["context"]["trace_id"] == CORR_ID, (
            f"Expected {CORR_ID!r}, got {out['context']['trace_id']!r}"
        )
        assert out["attributes"]["correlation_id"] == CORR_ID
        assert out["attributes"]["tenantId"] == "tenant-xyz"
        assert out["context"]["otel_trace_id"] != CORR_ID

    def test_exporter_reads_stored_attribute_after_context_cleared(self):
        """
        Simulates the background-thread path:
        correlation_id was stored as span attribute during the request →
        LoggerSpanExporter reads it after context vars are cleared.
        """
        ctx.set_trace_id(CORR_ID)
        from trace.request_span import get_context_attributes
        attrs = get_context_attributes()
        assert attrs["correlation_id"] == CORR_ID

        # Context cleared (request ended)
        ctx._trace_id_var.set(None)
        assert ctx.get_trace_id() is None

        # Exporter now runs on background thread with the stored attribute
        exporter = _make_exporter()
        span = _mock_span(attrs=attrs)

        raw = _capture_log("trace.setup", lambda: exporter.export([span]))
        out = json.loads(raw)

        assert out["context"]["trace_id"] == CORR_ID
