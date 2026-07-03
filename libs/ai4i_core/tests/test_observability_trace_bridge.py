"""Tests for trace → observability ContextVar bridge and payload metric emission."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.responses import StreamingResponse

from ai4i_core.observability.config import PluginConfig
from ai4i_core.observability.metrics import MetricsCollector
from ai4i_core.observability.middleware import (
    ObservabilityMiddleware,
    _has_llm_metrics,
    clear_inference_payload_metrics,
    get_inference_payload_metrics,
    set_inference_payload_metrics,
)


@pytest.fixture(autouse=True)
def _reset_inference_payload_metrics():
    clear_inference_payload_metrics()
    yield
    clear_inference_payload_metrics()


class TestInferencePayloadMetricsContextVar:
    def test_set_get_and_clear(self):
        assert get_inference_payload_metrics() is None
        snapshot = {"service_type": "asr", "audio_seconds": 1.5}
        set_inference_payload_metrics(snapshot)
        assert get_inference_payload_metrics() == snapshot
        clear_inference_payload_metrics()
        assert get_inference_payload_metrics() is None


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

    def test_emits_ocr_characters_and_image_size(self, middleware):
        mw, collector = middleware
        mw._emit_trace_payload_metrics(
            trace_metrics={"ocr_characters": 100, "ocr_image_kb": 12.5},
            service_type="ocr",
            tenant="tenant-a",
            service_id="ocr-svc",
        )
        rendered = collector.render()
        assert "telemetry_obsv_ocr_characters_processed" in rendered
        assert "telemetry_obsv_ocr_image_size_kb" in rendered

    def test_emits_ner_tokens(self, middleware):
        mw, collector = middleware
        mw._emit_trace_payload_metrics(
            trace_metrics={"ner_tokens": 7},
            service_type="ner",
            tenant="tenant-a",
            service_id="ner-svc",
        )
        assert "telemetry_obsv_ner_tokens_processed" in collector.render()

    @pytest.mark.parametrize(
        "service_type,metric_fragment",
        [
            ("tts", "telemetry_obsv_tts_characters_synthesized_count"),
            ("transliteration", "telemetry_obsv_transliteration_characters_processed_count"),
            ("language_detection", "telemetry_obsv_language_detection_characters_processed_count"),
            ("audio_lang_detection", "telemetry_obsv_audio_lang_detection_seconds_processed_count"),
            ("speaker_diarization", "telemetry_obsv_speaker_diarization_seconds_processed_count"),
            ("language_diarization", "telemetry_obsv_language_diarization_seconds_processed_count"),
        ],
    )
    def test_emits_remaining_service_types(self, middleware, service_type, metric_fragment):
        mw, collector = middleware
        trace_metrics = {
            "characters": 10,
            "audio_seconds": 4.0,
            "source_lang": "en",
            "target_lang": "hi",
        }
        mw._emit_trace_payload_metrics(
            trace_metrics=trace_metrics,
            service_type=service_type,
            tenant="tenant-a",
            service_id="svc",
        )
        assert metric_fragment in collector.render()

    def test_skips_zero_values(self, middleware):
        mw, collector = middleware
        mw._emit_trace_payload_metrics(
            trace_metrics={"characters": 0, "audio_seconds": 0.0},
            service_type="tts",
            tenant="tenant-a",
            service_id="tts-svc",
        )
        rendered = collector.render()
        assert "telemetry_obsv_tts_characters_synthesized_count" not in rendered


class TestRecordMetrics:
    @pytest.fixture
    def middleware(self):
        collector = MetricsCollector()
        config = PluginConfig(enabled=True, debug=False)
        mw = ObservabilityMiddleware(MagicMock(), metrics_collector=collector, config=config)
        return mw, collector

    @pytest.mark.asyncio
    async def test_uses_trace_snapshot_for_asr(self, middleware):
        mw, collector = middleware
        trace_metrics = {
            "service_type": "asr",
            "service_id": "from-trace",
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

    @pytest.mark.asyncio
    async def test_llm_tokens_from_trace_snapshot(self, middleware):
        mw, collector = middleware
        await mw._record_metrics(
            path="/api/v1/chat/completions",
            method="POST",
            service_type="llm",
            tenant="tenant-x",
            service_id="gpt-test",
            status_code=200,
            duration=1.2,
            trace_metrics={"service_type": "llm"},
            llm_prompt_tokens=100,
            llm_completion_tokens=50,
            llm_total_tokens=150,
            llm_model="gpt-test",
        )
        rendered = collector.render()
        assert "telemetry_obsv_llm_tokens_processed" in rendered


class TestDispatchWithTraceMetrics:
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
    async def test_skips_llm_response_buffer_when_trace_published_usage(self):
        collector = MetricsCollector()
        config = PluginConfig(enabled=True)
        captured = {}

        async def call_next(request):
            set_inference_payload_metrics(
                {
                    "service_type": "llm",
                    "llm_prompt_tokens": 11,
                    "llm_completion_tokens": 22,
                    "llm_total_tokens": 33,
                    "llm_model": "test-model",
                }
            )
            return self._streaming_json_response({"usage": {"prompt_tokens": 99}})

        async def app(scope, receive, send):
            pass

        mw = ObservabilityMiddleware(app, metrics_collector=collector, config=config)
        mw._buffer_response = AsyncMock(side_effect=AssertionError("should not buffer"))

        request = MagicMock()
        request.url.path = "/api/v1/chat/completions"
        request.method = "POST"
        request.headers = {"X-Tenant-Id": "tenant-1"}
        request.state = MagicMock(service_id="")

        original_record = mw._record_metrics

        async def _capture_record(**kwargs):
            captured.update(kwargs)
            await original_record(**kwargs)

        mw._record_metrics = _capture_record

        response = await mw.dispatch(request, call_next)
        await self._await_pending_tasks(mw)

        assert response.status_code == 200
        assert captured["llm_prompt_tokens"] == 11
        assert captured["llm_total_tokens"] == 33
        assert get_inference_payload_metrics() is None

    @pytest.mark.asyncio
    async def test_llm_fallback_buffers_response_when_no_trace_metrics(self):
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
        request.headers = {"X-Tenant-Id": "tenant-1"}
        request.state = MagicMock(service_id="")

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


class TestLlmUsageExtraction:
    def test_extract_llm_usage_from_body(self):
        collector = MetricsCollector()
        mw = ObservabilityMiddleware(MagicMock(), metrics_collector=collector)
        body = json.dumps(
            {
                "model": "m1",
                "usage": {"prompt_tokens": 3, "completion_tokens": 7},
            }
        ).encode()
        prompt, completion, total, model = mw._extract_llm_usage_from_body(body)
        assert prompt == 3
        assert completion == 7
        assert total == 10
        assert model == "m1"

    def test_extract_llm_usage_invalid_json_returns_zeros(self):
        mw = ObservabilityMiddleware(MagicMock(), metrics_collector=MetricsCollector())
        assert mw._extract_llm_usage_from_body(b"not-json") == (0, 0, 0, "")


class TestDetectServiceType:
    @pytest.mark.parametrize(
        "path,expected",
        [
            ("/api/v1/nmt/inference", "translation"),
            ("/api/v1/asr/inference", "asr"),
            ("/api/v1/tts/inference", "tts"),
            ("/api/v1/ocr/inference", "ocr"),
            ("/api/v1/transliteration/inference", "transliteration"),
            ("/api/v1/audio-lang-detection/inference", "audio_lang_detection"),
            ("/api/v1/language-detection/inference", "language_detection"),
            ("/api/v1/language-diarization/inference", "language_diarization"),
            ("/api/v1/speaker-diarization/inference", "speaker_diarization"),
            ("/api/v1/ner/inference", "ner"),
            ("/api/v1/speaker/enrollment", "speaker_verification"),
            ("/api/v1/chat/completions", "llm"),
            ("/enterprise/metrics", "enterprise"),
            ("/docs", "documentation"),
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
            return StreamingResponse(self._stream_ok(), media_type="text/plain")

        async def app(scope, receive, send):
            pass

        mw = ObservabilityMiddleware(app, metrics_collector=collector, config=config)
        request = MagicMock()
        request.url.path = "/api/v1/asr/inference"
        request.method = "POST"

        response = await mw.dispatch(request, call_next)
        assert response.status_code == 200
        assert "telemetry_obsv_requests_total_count" not in collector.render()

    @staticmethod
    async def _stream_ok():
        yield b"ok"
