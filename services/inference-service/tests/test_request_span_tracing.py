"""Extended coverage for trace.request_span tracing helpers."""

import json
import logging
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from opentelemetry.sdk.trace import TracerProvider

import ai4i_core.context as ctx
from trace.request_span import (
    compute_total_time_ms,
    finalize_span,
    get_context_attributes,
    get_endpoint_path,
    log_span_attributes,
    traced_inference,
    traced_span,
)


CORR_ID = "aabbccdd11223344aabbccdd11223344"


@pytest.fixture(autouse=True)
def _reset_context():
    ctx._trace_id_var.set(None)
    ctx._tenant_id_var.set(None)
    ctx._user_id_var.set(None)
    ctx._auth_type_var.set(None)
    ctx._endpoint_path_var.set(None)
    yield
    ctx._trace_id_var.set(None)
    ctx._tenant_id_var.set(None)
    ctx._user_id_var.set(None)
    ctx._auth_type_var.set(None)
    ctx._endpoint_path_var.set(None)


@pytest.fixture(autouse=True)
def _otel_tracer():
    provider = TracerProvider()
    with patch("trace.request_span.tracer", provider.get_tracer("test")):
        yield


def _mock_span(trace_id_int=0xCAFEBABE00000000CAFEBABE00000000, span_id_int=0x1234567890ABCDEF):
    sc = MagicMock()
    sc.trace_id = trace_id_int
    sc.span_id = span_id_int
    sc.trace_state = ""
    span = MagicMock()
    span.get_span_context.return_value = sc
    return span


def _capture_log(logger_name: str, fn) -> str:
    buf = StringIO()
    handler = logging.StreamHandler(buf)
    handler.setLevel(logging.DEBUG)
    log = logging.getLogger(logger_name)
    level = log.level
    log.setLevel(logging.DEBUG)
    log.addHandler(handler)
    try:
        fn()
    finally:
        log.removeHandler(handler)
        log.setLevel(level)
    return buf.getvalue().strip()


class TestGetContextAttributesExtended:
    def test_includes_auth_type_and_user_id(self):
        ctx.set_trace_id(CORR_ID)
        ctx.set_tenant_id("tenant-1")
        ctx.set_user_id("user-42")
        ctx.set_auth_type("api_key")

        attrs = get_context_attributes()
        assert attrs == {
            "userId": "user-42",
            "tenantId": "tenant-1",
            "correlation_id": CORR_ID,
            "authType": "api_key",
        }

    def test_returns_empty_when_context_unset(self):
        assert get_context_attributes() == {}

    def test_swallows_context_read_errors(self):
        with patch("ai4i_core.context.get_user_id", side_effect=RuntimeError("boom")):
            assert get_context_attributes() == {}


class TestGetEndpointPath:
    def test_returns_empty_when_unset(self):
        assert get_endpoint_path() == ""

    def test_returns_endpoint_from_context(self):
        ctx.set_endpoint_path("/api/v1/nmt/inference")
        assert get_endpoint_path() == "/api/v1/nmt/inference"

    def test_swallows_errors(self):
        with patch("ai4i_core.context.get_endpoint_path", side_effect=RuntimeError("nope")):
            assert get_endpoint_path() == ""


class TestComputeTotalTimeMs:
    def test_returns_non_negative_ms(self):
        import time

        start = time.time()
        assert compute_total_time_ms(start) >= 0.0


class TestLogSpanAttributesExtended:
    def test_falls_back_to_otel_trace_id_without_correlation(self):
        span = _mock_span()
        raw = _capture_log(
            "trace.request_span",
            lambda: log_span_attributes("request", span, {"total_time_ms": 1.0}),
        )
        out = json.loads(raw)
        assert out["context"]["trace_id"].startswith("0x")
        assert out["context"]["otel_trace_id"].startswith("0x")

    def test_swallows_logging_errors(self):
        span = MagicMock()
        span.get_span_context.side_effect = RuntimeError("bad span")
        _capture_log(
            "trace.request_span",
            lambda: log_span_attributes("request", span, {}),
        )


class TestTracedSpanLifecycle:
    def test_success_classifies_status(self):
        with traced_span("request", root=True, classify_status=True) as attrs:
            attrs["url"] = "/api/v1/inference"
        assert attrs["status"] == "success"
        assert attrs["status_code"] == 200
        assert attrs["total_time_ms"] >= 0

    def test_value_error_maps_to_400(self):
        with pytest.raises(ValueError, match="bad input"):
            with traced_span("request", classify_status=True) as attrs:
                raise ValueError("bad input")
        assert attrs["status"] == "failure"
        assert attrs["status_code"] == 400

    def test_runtime_error_maps_to_500(self):
        with pytest.raises(RuntimeError, match="upstream"):
            with traced_span("request", classify_status=True) as attrs:
                raise RuntimeError("upstream")
        assert attrs["status"] == "failure"
        assert attrs["status_code"] == 500

    def test_error_attrs_callback_runs(self):
        def _reshape(attrs, exc):
            attrs["custom"] = str(exc)
            return attrs

        with pytest.raises(RuntimeError):
            with traced_span("model", error_attrs=_reshape) as attrs:
                raise RuntimeError("fail")
        assert attrs["custom"] == "fail"


class TestFinalizeSpan:
    def test_sets_ok_status(self):
        span = MagicMock()
        with patch("trace.request_span.log_span_attributes") as log_fn:
            finalize_span(span, "model", {"k": "v"}, ok=True)
        span.set_attribute.assert_called_with("k", "v")
        span.set_status.assert_called_once()
        log_fn.assert_called_once()

    def test_sets_error_status(self):
        span = MagicMock()
        with patch("trace.request_span.log_span_attributes"):
            finalize_span(span, "model", {}, error=RuntimeError("x"))
        span.set_status.assert_called_once()


class TestTracedInferenceFailure:
    @pytest.mark.asyncio
    async def test_zeros_tokens_and_reraises_on_failure(self):
        logger = logging.getLogger("test.traced_inference.failure")
        with pytest.raises(RuntimeError, match="inference failed"):
            async with traced_inference({"input": []}, "NERTaskService", logger) as attrs:
                attrs["output_tokens"] = 99
                raise RuntimeError("inference failed")

    @pytest.mark.asyncio
    async def test_merges_context_attributes(self):
        ctx.set_trace_id(CORR_ID)
        ctx.set_tenant_id("tenant-x")
        logger = logging.getLogger("test.traced_inference.context")

        async with traced_inference({"input": [{"source": "hi"}]}, "NER", logger) as attrs:
            assert attrs["correlation_id"] == CORR_ID
            assert attrs["tenantId"] == "tenant-x"
