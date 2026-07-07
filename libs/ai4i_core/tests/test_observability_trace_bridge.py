"""Tests for ObservabilityMiddleware payload analysis and tracing headers."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse

from ai4i_core.observability.config import PluginConfig
from ai4i_core.observability.metrics import MetricsCollector
from ai4i_core.observability.middleware import ObservabilityMiddleware, _has_llm_metrics
from ai4i_core.observability.tracing_headers import TRACING_HEADER_PREFIX, read_tracing_headers


class TestHasLlmMetrics:
    @pytest.mark.parametrize(
        "metrics,expected",
        [
            (None, False),
            ({}, False),
            ({"llm_prompt_tokens": 10}, True),
            ({"llm_completion_tokens": 5}, True),
            ({"llm_total_tokens": 15}, True),
        ],
    )
    def test_detects_llm_usage_fields(self, metrics, expected):
        assert _has_llm_metrics(metrics) is expected


class TestEmitTracePayloadMetrics:
    @pytest.fixture
    def middleware(self):
        collector = MetricsCollector()
        mw = ObservabilityMiddleware(MagicMock(), metrics_collector=collector)
        return mw, collector

    def test_emits_asr_audio_seconds(self, middleware):
        mw, collector = middleware
        mw._emit_trace_payload_metrics(
            trace_metrics={
                "audio_seconds": 3.5,
                "source_lang": "hi",
            },
            service_type="asr",
            tenant="tenant-a",
            service_id="asr-svc",
        )
        rendered = collector.render()
        assert "telemetry_obsv_asr_audio_seconds_processed" in rendered

    def test_emits_nmt_characters(self, middleware):
        mw, collector = middleware
        mw._emit_trace_payload_metrics(
            trace_metrics={
                "characters": 42,
                "source_lang": "en",
                "target_lang": "hi",
            },
            service_type="translation",
            tenant="tenant-a",
            service_id="nmt-svc",
        )
        rendered = collector.render()
        assert "telemetry_obsv_nmt_characters_translated" in rendered


class TestRecordMetrics:
    @pytest.fixture
    def middleware(self):
        collector = MetricsCollector()
        config = PluginConfig(enabled=True, debug=False)
        mw = ObservabilityMiddleware(MagicMock(), metrics_collector=collector, config=config)
        return mw, collector

    @pytest.mark.asyncio
    async def test_uses_precomputed_snapshot_for_asr(self, middleware):
        mw, collector = middleware
        trace_metrics = {
            "service_type": "asr",
            "service_id": "from-observability",
            "audio_seconds": 2.0,
            "source_lang": "en",
        }
        await mw._record_metrics(
            path="/api/v1/inference",
            method="POST",
            service_type="unknown",
            tenant="tenant-x",
            service_id="",
            status_code=200,
            duration=0.5,
            trace_metrics=trace_metrics,
        )
        rendered = collector.render()
        assert "telemetry_obsv_requests_total" in rendered
        assert "telemetry_obsv_asr_audio_seconds_processed" in rendered


class TestPrepareInferenceRequest:
    @pytest.mark.asyncio
    async def test_injects_tracing_headers_before_handler(self):
        collector = MetricsCollector()
        config = PluginConfig(enabled=True)
        mw = ObservabilityMiddleware(MagicMock(), metrics_collector=collector, config=config)

        payload = {
            "task_type": "NMT",
            "input": [{"source": "hello world"}],
            "config": {"serviceId": "nmt-svc-1"},
        }
        body = json.dumps(payload).encode()

        scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/inference",
            "headers": [(b"content-type", b"application/json")],
        }

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        request = Request(scope, receive)
        replay_body, trace_metrics = await mw._prepare_inference_request(request, "unknown")

        assert replay_body == body
        assert trace_metrics["service_type"] == "translation"
        assert trace_metrics["characters"] == 11

        header_map = {k.decode(): v.decode() for k, v in scope["headers"]}
        tracing = read_tracing_headers(header_map)
        assert tracing["service_type"] == "translation"
        assert tracing["input_type"] == "text"
        assert any(k.decode().startswith(TRACING_HEADER_PREFIX.lower()) for k, _ in scope["headers"])


class TestDispatchWithPrecomputedMetrics:
    @staticmethod
    def _streaming_json_response(payload: dict, status_code: int = 200) -> StreamingResponse:
        body = json.dumps(payload).encode()

        async def stream():
            yield body

        return StreamingResponse(stream(), status_code=status_code, media_type="application/json")

    @staticmethod
    async def _await_pending_tasks(middleware: ObservabilityMiddleware) -> None:
        pending = list(middleware._pending_tasks)
        if pending:
            await asyncio.gather(*pending)

    @pytest.mark.asyncio
    async def test_llm_metrics_from_response_body(self):
        collector = MetricsCollector()
        config = PluginConfig(enabled=True)

        usage_body = {
            "model": "fallback-model",
            "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
        }

        async def call_next(request):
            return self._streaming_json_response(usage_body)

        async def app(scope, receive, send):
            pass

        mw = ObservabilityMiddleware(app, metrics_collector=collector, config=config)

        request = MagicMock()
        request.url.path = "/api/v1/chat/completions"
        request.method = "POST"
        request.headers = {"X-Tenant-Id": "tenant-1", "content-type": "application/json"}
        request.state = MagicMock(service_id="", observability_payload_metrics={"service_type": "llm"})
        request.scope = {"headers": []}
        request.body = AsyncMock(return_value=b'{"model":"fallback-model","messages":[]}')

        mw._should_analyze_request_body = MagicMock(return_value=False)

        captured = {}
        original_record = mw._record_metrics

        async def _capture_record(**kwargs):
            captured.update(kwargs)
            await original_record(**kwargs)

        mw._record_metrics = _capture_record

        response = await mw.dispatch(request, call_next)
        await self._await_pending_tasks(mw)

        assert response.status_code == 200
        assert captured["llm_prompt_tokens"] == 5
        assert captured["llm_model"] == "fallback-model"


class TestDetectServiceType:
    @pytest.mark.parametrize(
        "path,expected",
        [
            ("/api/v1/nmt/inference", "translation"),
            ("/api/v1/asr/inference", "asr"),
            ("/api/v1/chat/completions", "llm"),
            ("/api/v1/inference", "unknown"),
        ],
    )
    def test_path_detection(self, path, expected):
        assert ObservabilityMiddleware._detect_service_type(path) == expected


class TestDispatchDisabled:
    @pytest.mark.asyncio
    async def test_skips_metrics_when_disabled(self):
        collector = MetricsCollector()
        config = PluginConfig(enabled=False)

        async def call_next(request):
            return JSONResponse({"ok": True})

        async def app(scope, receive, send):
            pass

        mw = ObservabilityMiddleware(app, metrics_collector=collector, config=config)
        request = MagicMock()
        request.url.path = "/api/v1/asr/inference"
        request.method = "POST"

        response = await mw.dispatch(request, call_next)
        assert response.status_code == 200
        assert "telemetry_obsv_requests_total_count" not in collector.render()
