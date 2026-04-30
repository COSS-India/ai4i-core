"""Tests for StandardSpanManager (optional OTel, partial failure, phase spans)."""

from contextlib import contextmanager
from unittest.mock import MagicMock

import pytest

from ai4icore_telemetry import Status, StatusCode
from ai4icore_telemetry.standard_spans import (
    StandardSpanManager,
    _TRACING_AVAILABLE,
    _inference_partial_message,
)


def _make_tracer_mock(span: MagicMock):
    tracer = MagicMock()

    @contextmanager
    def _start_as_current_span(*_args, **_kwargs):
        yield span

    tracer.start_as_current_span = _start_as_current_span
    return tracer


def test_inference_without_tracer_is_safe_noop():
    mgr = StandardSpanManager("testsvc")
    mgr._tracer = None
    with mgr.inference(service_id="s1", input_count=1) as span:
        span.set_attribute("x", 1)
        mgr.note_partial_inference_failure("should not leak")
    assert _inference_partial_message.get() is None


def test_inference_partial_failure_marks_parent_span_error():
    mock_span = MagicMock()
    mock_tracer = _make_tracer_mock(mock_span)
    mgr = StandardSpanManager("audiolang")
    # Simulate an active tracer regardless of env OTel import success (CI / minimal images).
    mgr._tracer = mock_tracer

    with mgr.inference(service_id="svc", input_count=2):
        mgr.note_partial_inference_failure("one or more inputs failed")

    mock_span.set_attribute.assert_any_call("audiolang.has_partial_errors", True)
    mock_span.set_status.assert_called()
    if _TRACING_AVAILABLE:
        status_arg = mock_span.set_status.call_args_list[-1][0][0]
        assert status_arg.status_code.name == "ERROR"


def test_inference_success_sets_ok():
    mock_span = MagicMock()
    mock_tracer = _make_tracer_mock(mock_span)
    mgr = StandardSpanManager("audiolang")
    mgr._tracer = mock_tracer

    with mgr.inference(service_id="svc", input_count=1):
        pass

    if _TRACING_AVAILABLE:
        status_arg = mock_span.set_status.call_args_list[-1][0][0]
        assert status_arg.status_code.name == "OK"
    else:
        mock_span.set_status.assert_called()


def test_inference_exception_clears_partial_flag():
    mock_span = MagicMock()
    mock_tracer = _make_tracer_mock(mock_span)
    mgr = StandardSpanManager("audiolang")
    mgr._tracer = mock_tracer

    with pytest.raises(ValueError):
        with mgr.inference(service_id="svc", input_count=1):
            mgr.note_partial_inference_failure("partial")
            raise ValueError("fail")

    assert _inference_partial_message.get() is None


def test_filtering_span_exporter_is_importable():
    """Regression: symbol must exist when OTel is off (no NameError on import)."""
    import ai4icore_telemetry.tracing as tr
    from ai4icore_telemetry.tracing import FilteringSpanExporter

    assert FilteringSpanExporter is not None

    if not tr.TRACING_AVAILABLE:
        exp = FilteringSpanExporter(base_exporter=None, service_name="unit-test")
        assert exp.export([]) is True
        assert exp.force_flush() is True
        return

    from opentelemetry.sdk.trace.export import SpanExportResult

    base = MagicMock()
    base.export.return_value = SpanExportResult.SUCCESS
    exp = FilteringSpanExporter(base_exporter=base, service_name="asr-service")
    mock_span = MagicMock()
    mock_span.name = "asr inference"
    assert exp.export([mock_span]) == SpanExportResult.SUCCESS
    base.export.assert_called_once()


def test_standard_phase_span_names():
    """Document expected span name shape for dashboard / trace queries."""
    mgr = StandardSpanManager("audio-lang-detection")
    assert mgr._svc_key("inference") == "audio-lang-detection.inference"
    assert mgr._svc_key("preprocess") == "audio-lang-detection.preprocess"
    assert mgr._svc_key("resolve_model") == "audio-lang-detection.resolve_model"
    assert mgr._svc_key("triton_inference") == "audio-lang-detection.triton_inference"
    assert mgr._svc_key("postprocess") == "audio-lang-detection.postprocess"
    assert mgr._svc_key("persist") == "audio-lang-detection.persist"
    assert mgr._svc_key("persist_request") == "audio-lang-detection.persist_request"


def test_phase_span_with_disabled_tracer():
    mgr = StandardSpanManager("testsvc")
    mgr._tracer = None
    with mgr.preprocess() as s:
        s.set_attribute("a", 1)
    with mgr.resolve_model() as s:
        s.record_exception(RuntimeError("x"))
    with mgr.triton_inference() as s:
        s.set_status(Status(StatusCode.OK))
