"""Tests for payload analysis and the optional trace → observability bridge."""

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
from trace import observability_bridge as ob
from trace import payload_analysis as pa
from trace import span_attributes as sa
from trace.request_span import traced_inference


@pytest.fixture(autouse=True)
def _reset_context():
    pa._payload_analysis.set(None)
    clear_inference_payload_metrics()
    yield
    pa._payload_analysis.set(None)
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
        analysis = pa.analyze_payload(payload)

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
        analysis = pa.analyze_payload(payload)

        assert analysis["input_type"] == "audio"
        assert analysis["service_type"] == "asr"
        assert analysis["audio_seconds"] == pytest.approx(2.0, rel=0.01)

    def test_ocr_payload_analysis(self):
        content = "A" * 400
        payload = {
            "task_type": "OCR",
            "image": [{"imageContent": content}],
        }
        analysis = pa.analyze_payload(payload)

        assert analysis["input_type"] == "image"
        assert analysis["ocr_characters"] == 2
        assert analysis["ocr_image_kb"] > 0

    def test_caches_second_call_for_same_payload(self):
        payload = {"task_type": "NER", "input": [{"source": "one two three"}]}
        first = pa.analyze_payload(payload)
        second = pa.analyze_payload(payload)
        assert first is second

    def test_non_dict_returns_empty(self):
        assert pa.analyze_payload(None) == {}


class TestPublishInferencePayloadMetrics:
    def test_publishes_nmt_snapshot_to_contextvar(self):
        payload = {
            "task_type": "NMT",
            "input": [{"source": "hello"}],
            "config": {"serviceId": "nmt-1"},
        }
        ob.publish_inference_payload_metrics(
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
        ob.publish_inference_payload_metrics(
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

    def test_service_type_from_task_name_suffix(self):
        payload = {"task_type": "NMT", "input": [{"source": "x"}]}
        ob.publish_inference_payload_metrics(payload, {}, "NMTTaskService")
        assert get_inference_payload_metrics()["service_type"] == "translation"

    def test_publish_swallows_errors(self, monkeypatch):
        monkeypatch.setattr(
            pa,
            "analyze_payload",
            lambda _payload: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        ob.publish_inference_payload_metrics({"input": []}, {}, "NER")


class TestTracedInferenceIntegration:
    @pytest.mark.asyncio
    async def test_traced_inference_publishes_on_success(self):
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

    @pytest.mark.asyncio
    async def test_traced_inference_does_not_publish_on_failure(self):
        payload = {"task_type": "ASR", "audio": [{"audioContent": _wav_base64(0.5)}]}
        logger = logging.getLogger("test.trace.failure")

        with pytest.raises(RuntimeError, match="inference failed"):
            async with traced_inference(payload, "ASRTaskService", logger):
                raise RuntimeError("inference failed")

        assert get_inference_payload_metrics() is None


class TestSpanAttributes:
    def test_get_input_type(self):
        assert sa.get_input_type({"input": [{"source": "hi"}]}) == "text"
        assert sa.get_input_type({"audio": [{}]}) == "audio"
        assert sa.get_input_type({}) == "unknown"

    def test_get_output_type_text_audio_image(self):
        assert sa.get_output_type([{"target": "hello"}]) == "text"
        assert sa.get_output_type([{"audio_content": "abc"}]) == "audio"
        assert sa.get_output_type([{"image_content": "xyz"}]) == "image"
        assert sa.get_output_type([]) == "unknown"

    def test_count_output_tokens_by_modality(self):
        assert sa.count_output_tokens([{"target": "one two"}], "text") == 2
        assert sa.count_output_tokens([{"audio_content": "x" * 200}], "audio") >= 1
        assert sa.count_output_tokens([{"image_content": "x" * 2000}], "image") >= 1

    def test_count_input_tokens(self):
        items = [{"num_samples": 16000}]
        assert sa.count_input_tokens(items, "audio") >= 1


class TestPayloadShapeVariants:
    def test_input_data_nested_text(self):
        payload = {
            "task_type": "NMT",
            "inputData": {"input": [{"source": "nested text"}]},
        }
        analysis = pa.analyze_payload(payload)
        assert analysis["characters"] == len("nested text")


class TestObservabilityPackageExport:
    def test_set_inference_payload_metrics_exported(self):
        from ai4i_core.observability import set_inference_payload_metrics as exported

        exported({"service_type": "ner", "ner_tokens": 1})
        assert get_inference_payload_metrics()["ner_tokens"] == 1
