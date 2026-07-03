"""Tests for single-pass payload analysis and trace → observability publishing."""

import base64
import io
import logging
import wave
from unittest.mock import patch

import pytest
from opentelemetry.sdk.trace import TracerProvider

from ai4i_core.observability.middleware import (
    clear_inference_payload_metrics,
    get_inference_payload_metrics,
)
from trace import span_attributes as sa
from trace.request_span import traced_inference


@pytest.fixture(autouse=True)
def _reset_context():
    sa._payload_analysis.set(None)
    clear_inference_payload_metrics()
    yield
    sa._payload_analysis.set(None)
    clear_inference_payload_metrics()


@pytest.fixture(autouse=True)
def _otel_tracer():
    provider = TracerProvider()
    with patch("trace.request_span.tracer", provider.get_tracer("test")):
        with patch("trace.request_span.log_span_attributes"):
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


class TestEnsurePayloadAnalyzed:
    def test_nmt_payload_analysis(self):
        payload = {
            "task_type": "NMT",
            "input": [{"source": "hello world"}],
            "config": {
                "serviceId": "nmt-svc-1",
                "language": {"sourceLanguage": "en", "targetLanguage": "hi"},
            },
        }
        analysis = sa.ensure_payload_analyzed(payload)

        assert analysis["input_type"] == "text"
        assert analysis["input_tokens"] == 2
        assert analysis["characters"] == 11
        assert analysis["ner_tokens"] == 2
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
        analysis = sa.ensure_payload_analyzed(payload)

        assert analysis["input_type"] == "audio"
        assert analysis["service_type"] == "asr"
        assert analysis["audio_seconds"] == pytest.approx(2.0, rel=0.01)

    def test_ocr_payload_analysis(self):
        content = "A" * 400
        payload = {
            "task_type": "OCR",
            "image": [{"imageContent": content}],
        }
        analysis = sa.ensure_payload_analyzed(payload)

        assert analysis["input_type"] == "image"
        assert analysis["ocr_characters"] == 2
        assert analysis["ocr_image_kb"] > 0

    def test_caches_second_call_for_same_payload(self):
        payload = {"task_type": "NER", "input": [{"source": "one two three"}]}
        first = sa.ensure_payload_analyzed(payload)
        second = sa.ensure_payload_analyzed(payload)
        assert first is second

    def test_non_dict_returns_empty(self):
        assert sa.ensure_payload_analyzed(None) == {}


class TestPublishObservabilityMetrics:
    def test_publishes_nmt_snapshot_to_contextvar(self):
        payload = {
            "task_type": "NMT",
            "input": [{"source": "hello"}],
            "config": {"serviceId": "nmt-1"},
        }
        sa.publish_observability_metrics(
            payload,
            span_attrs={"service_id": "span-svc"},
            task_name="NMTTaskService",
        )
        metrics = get_inference_payload_metrics()
        assert metrics is not None
        assert metrics["service_type"] == "translation"
        assert metrics["characters"] == 5
        assert metrics["service_id"] == "span-svc"

    def test_publishes_llm_token_fields(self):
        payload = {"task_type": "LLM", "model": "gemma-test"}
        sa.publish_observability_metrics(
            payload,
            span_attrs={"input_tokens": 100, "output_tokens": 25},
            task_name="LLM",
        )
        metrics = get_inference_payload_metrics()
        assert metrics["service_type"] == "llm"
        assert metrics["llm_prompt_tokens"] == 100
        assert metrics["llm_completion_tokens"] == 25
        assert metrics["llm_total_tokens"] == 125
        assert metrics["llm_model"] == "gemma-test"

    def test_count_input_tokens_reuses_cache(self):
        payload = {"input": [{"source": "alpha beta gamma"}]}
        sa.ensure_payload_analyzed({**payload, "task_type": "NER"})
        assert sa.count_input_tokens(payload["input"], "text") == 3

    def test_get_input_type_reuses_cache(self):
        payload = {"task_type": "TTS", "input": [{"source": "hi"}]}
        sa.ensure_payload_analyzed(payload)
        assert sa.get_input_type(payload) == "text"


class TestTracedInferenceIntegration:
    @pytest.mark.asyncio
    async def test_traced_inference_publishes_on_exit(self):
        payload = {
            "task_type": "ASR",
            "audio": [{"audioContent": _wav_base64(1.0)}],
            "config": {"serviceId": "asr-svc"},
        }
        logger = logging.getLogger("test.trace")

        async with traced_inference(payload, "ASRTaskService", logger) as attrs:
            attrs["input_tokens"] = 10
            attrs["output_tokens"] = 5
            attrs["output_type"] = "text"
            attrs["service_id"] = "asr-svc"

        metrics = get_inference_payload_metrics()
        assert metrics is not None
        assert metrics["service_type"] == "asr"
        assert metrics["service_id"] == "asr-svc"
        assert metrics["audio_seconds"] == pytest.approx(1.0, rel=0.05)
