"""Tests for payload analysis, tracing headers, and trace layer integration."""

import base64
import io
import logging
import wave
from unittest.mock import patch

import pytest
from opentelemetry.sdk.trace import TracerProvider
from starlette.requests import Request

from ai4i_core.observability.payload_analysis import analyze_payload
from ai4i_core.observability.tracing_headers import (
    TRACING_HEADER_PREFIX,
    build_tracing_header_pairs,
    inject_tracing_headers,
    read_tracing_headers,
)
from trace import span_attributes as sa
from trace.request_span import traced_inference
from trace.tracing_headers import get_tracing_attributes


@pytest.fixture(autouse=True)
def _otel_tracer():
    provider = TracerProvider()
    with patch("trace.request_span.tracer", provider.get_tracer("test")):
        yield


def _wav_base64(seconds: float = 1.0, rate: int = 16000) -> str:
    buf = io.BytesIO()
    frames = int(rate * seconds)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * frames)
    return base64.b64encode(buf.getvalue()).decode()


def _request_with_tracing_headers(analysis: dict) -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/inference",
        "headers": [],
    }
    inject_tracing_headers(scope, analysis)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    return Request(scope, receive)


class TestAnalyzePayload:
    def test_nmt_payload_analysis(self):
        payload = {
            "task_type": "NMT",
            "input": [{"source": "hello world"}],
            "config": {
                "serviceId": "nmt-svc-1",
                "language": {"sourceLanguage": "en", "targetLanguage": "hi"},
            },
        }
        analysis = analyze_payload(payload)

        assert analysis["input_type"] == "text"
        assert analysis["input_tokens"] == 11
        assert analysis["characters"] == 11
        assert analysis["ner_tokens"] == 2
        assert analysis["task_type"] == "NMT"
        assert analysis["service_type"] == "translation"
        assert analysis["service_id"] == "nmt-svc-1"
        assert analysis["source_lang"] == "en"
        assert analysis["target_lang"] == "hi"

    def test_asr_payload_analysis(self):
        payload = {
            "task_type": "ASR",
            "audio": [{"audioContent": _wav_base64(2.0)}],
            "config": {"language": {"sourceLanguage": "en"}},
        }
        analysis = analyze_payload(payload)

        assert analysis["input_type"] == "audio"
        assert analysis["service_type"] == "asr"
        assert analysis["audio_seconds"] == pytest.approx(2.0, rel=0.01)

    def test_non_dict_returns_empty(self):
        assert analyze_payload(None) == {}


class TestTracingHeaders:
    def test_prefix_constant(self):
        assert TRACING_HEADER_PREFIX == "X-Tracing-"

    def test_build_and_read_round_trip(self):
        analysis = {
            "input_type": "text",
            "input_tokens": 5,
            "service_type": "translation",
            "service_id": "nmt-1",
            "characters": 42,
        }
        pairs = build_tracing_header_pairs(analysis)
        headers = {name: value for name, value in pairs}
        parsed = read_tracing_headers(headers)
        assert parsed["input_type"] == "text"
        assert parsed["input_tokens"] == 5
        assert parsed["service_type"] == "translation"
        assert parsed["service_id"] == "nmt-1"
        assert parsed["characters"] == 42

    def test_get_tracing_attributes_from_request(self):
        analysis = {
            "input_type": "audio",
            "input_tokens": 10,
            "service_type": "asr",
            "service_id": "asr-svc",
            "audio_seconds": 1.5,
        }
        request = _request_with_tracing_headers(analysis)
        attrs = get_tracing_attributes(request)
        assert attrs["input_type"] == "audio"
        assert attrs["input_tokens"] == 10
        assert attrs["service_id"] == "asr-svc"
        assert attrs["audio_seconds"] == pytest.approx(1.5)


class TestTracedInferenceIntegration:
    @pytest.mark.asyncio
    async def test_traced_inference_seeds_from_tracing_headers(self):
        payload = {
            "task_type": "ASR",
            "audio": [{"audioContent": _wav_base64(1.0)}],
            "config": {"serviceId": "asr-svc"},
        }
        analysis = analyze_payload(payload)
        request = _request_with_tracing_headers(analysis)
        logger = logging.getLogger("test.trace")
        captured = {}

        async with traced_inference(payload, "ASRTaskService", logger, request=request) as attrs:
            captured.update(attrs)
            attrs["output_tokens"] = 5
            attrs["output_type"] = "text"

        assert captured["input_type"] == "audio"
        assert captured["input_tokens"] == pytest.approx(analysis["input_tokens"])
        assert captured["service_id"] == "asr-svc"

    @pytest.mark.asyncio
    async def test_traced_inference_without_headers_uses_defaults(self):
        payload = {"input": [{"source": "hello"}]}
        logger = logging.getLogger("test.trace.fallback")

        async with traced_inference(payload, "NER", logger) as attrs:
            assert attrs["input_type"] == "unknown"
            assert attrs["input_tokens"] == 0
            assert attrs["task_type"] == "ner"


class TestSpanAttributes:
    def test_get_output_type_text_audio_image(self):
        assert sa.get_output_type([{"target": "hello"}]) == "text"
        assert sa.get_output_type([{"audio_content": "abc"}]) == "audio"
        assert sa.get_output_type([{"image_content": "xyz"}]) == "image"
        assert sa.get_output_type([]) == "unknown"

    def test_count_output_tokens_by_modality(self):
        assert sa.count_output_tokens([{"target": "one two"}], "text") == len("one two")
        assert sa.count_output_tokens([{"audio_content": "x" * 200}], "audio") >= 1
        assert sa.count_output_tokens([{"image_content": "x" * 2000}], "image") >= 1

    def test_count_input_tokens(self):
        items = [{"num_samples": 960000, "sample_rate": 16000}]
        assert sa.count_input_tokens(items, "audio") >= 1


class TestPayloadShapeVariants:
    def test_input_data_nested_text(self):
        payload = {
            "task_type": "NMT",
            "inputData": {"input": [{"source": "nested text"}]},
        }
        analysis = analyze_payload(payload)
        assert analysis["characters"] == len("nested text")
