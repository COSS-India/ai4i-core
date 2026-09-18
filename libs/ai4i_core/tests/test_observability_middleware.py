"""Unit tests: ObservabilityMiddleware reads billed_* from request.state
instead of re-deriving unit counts from the request/response body
(AI4IDS-2532).

Covers the specific divergences the ticket flagged:
  - failure path must not emit a fake 0 metric
  - LLM metrics must come from request.state, not a re-parsed response body
  - OCR must emit the billed image COUNT, not the old byte-size heuristic
  - NER must emit the billed CHARACTER count, not a word count
  - ASR/audio must convert billed minutes to seconds for the histogram
"""
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, Request
from starlette.requests import Request as StarletteRequest
from starlette.testclient import TestClient

from types import SimpleNamespace

from ai4i_core.observability.config import PluginConfig
from ai4i_core.observability.middleware import (
    ObservabilityMiddleware,
    set_billed_state,
    set_metric_labels,
)


def _middleware() -> ObservabilityMiddleware:
    mw = ObservabilityMiddleware.__new__(ObservabilityMiddleware)
    mw.metrics_collector = MagicMock()
    mw.config = MagicMock(debug=False)
    return mw


class TestSetBilledState:
    """set_billed_state carries ONLY billed quantities. It must not touch
    metric labels (source_lang/target_lang/model) or service_id — those are
    separate concerns set elsewhere."""

    def test_sets_billed_quantities(self):
        request = SimpleNamespace(state=SimpleNamespace())
        set_billed_state(request, billed_input=42, billed_output=7)
        assert request.state.billed_input == 42
        assert request.state.billed_output == 7

    def test_defaults_applied(self):
        request = SimpleNamespace(state=SimpleNamespace())
        set_billed_state(request, billed_input=5)
        assert request.state.billed_output == 0

    def test_does_not_set_labels_or_dead_fields(self):
        """Labels (languages, model) are not billing data; billed_unit_type
        is dead (middleware dispatches on service_type from the URL path)."""
        request = SimpleNamespace(state=SimpleNamespace())
        set_billed_state(request, billed_input=5)
        assert not hasattr(request.state, "source_lang")
        assert not hasattr(request.state, "target_lang")
        assert not hasattr(request.state, "model")
        assert not hasattr(request.state, "billed_model")
        assert not hasattr(request.state, "billed_unit_type")

    def test_does_not_touch_service_id(self):
        request = SimpleNamespace(state=SimpleNamespace(service_id="set-earlier"))
        set_billed_state(request, billed_input=5)
        assert request.state.service_id == "set-earlier"


class TestSetMetricLabels:
    """set_metric_labels carries ONLY Prometheus metric labels (not billing):
    languages (NMT/TTS/ASR/transliteration) and the LLM model name."""

    def test_sets_language_labels(self):
        request = SimpleNamespace(state=SimpleNamespace())
        set_metric_labels(request, source_lang="en", target_lang="hi")
        assert request.state.source_lang == "en"
        assert request.state.target_lang == "hi"

    def test_sets_model_label(self):
        request = SimpleNamespace(state=SimpleNamespace())
        set_metric_labels(request, model="gemma")
        assert request.state.model == "gemma"

    def test_sets_model_id_label(self):
        """model_id (Model Registry identity) is a distinct dimension from
        model (the upstream-echoed model name) — see MetricsCollector."""
        request = SimpleNamespace(state=SimpleNamespace())
        set_metric_labels(request, model_id="hash-gemma-v1")
        assert request.state.model_id == "hash-gemma-v1"

    def test_defaults_empty(self):
        request = SimpleNamespace(state=SimpleNamespace())
        set_metric_labels(request)
        assert request.state.source_lang == ""
        assert request.state.target_lang == ""
        assert request.state.model == ""
        assert request.state.model_id == ""

    def test_does_not_touch_billed_quantities(self):
        request = SimpleNamespace(state=SimpleNamespace())
        set_metric_labels(request, source_lang="en")
        assert not hasattr(request.state, "billed_input")

    def test_second_call_does_not_clobber_field_it_omits(self):
        """Regression: model_id is typically set EARLY (as soon as the
        service resolves, before a handler runs), then source_lang/
        target_lang are set in a SECOND, later call once they're known. That
        second call must not reset model_id back to "" just because it
        doesn't repeat it — otherwise a request that fails/raises between
        the two calls (e.g. an upstream 502) would end up with no model_id
        on its metrics, since the failure path never reaches a call that
        DOES repeat it."""
        request = SimpleNamespace(state=SimpleNamespace())
        set_metric_labels(request, model_id="hash-gemma-v1")
        set_metric_labels(request, source_lang="en", target_lang="hi")

        assert request.state.model_id == "hash-gemma-v1"
        assert request.state.source_lang == "en"
        assert request.state.target_lang == "hi"

    def test_explicit_empty_string_does_overwrite(self):
        """Distinguish "field omitted" (leave as-is) from "field explicitly
        set to empty" (a caller that genuinely wants to clear/reset it)."""
        request = SimpleNamespace(state=SimpleNamespace())
        set_metric_labels(request, model_id="hash-gemma-v1")
        set_metric_labels(request, model_id="")

        assert request.state.model_id == ""


class TestRecordMetricsFailurePath:
    @pytest.mark.asyncio
    async def test_non_2xx_status_skips_unit_metrics(self):
        mw = _middleware()
        await mw._record_metrics(
            path="/api/v1/nmt/inference", method="POST",
            service_type="translation", tenant="t1", tenant_id="", service_id="s1",
            status_code=502, duration=0.1,
            billed_input=999, billed_output=0,
        )
        mw.metrics_collector.track_request.assert_called_once()
        mw.metrics_collector.track_nmt_characters.assert_not_called()

    @pytest.mark.asyncio
    async def test_billed_input_none_skips_unit_metrics(self):
        """billed_input is None when the handler never set request.state
        (non-inference path, or failure before billing ran) — must not
        emit a misleading 0."""
        mw = _middleware()
        await mw._record_metrics(
            path="/api/v1/nmt/inference", method="POST",
            service_type="translation", tenant="t1", tenant_id="", service_id="s1",
            status_code=200, duration=0.1,
            billed_input=None, billed_output=None,
        )
        mw.metrics_collector.track_nmt_characters.assert_not_called()


class TestLLMMetrics:
    @pytest.mark.asyncio
    async def test_llm_uses_billed_state_not_body(self):
        mw = _middleware()
        await mw._record_metrics(
            path="/api/v1/chat", method="POST", service_type="llm",
            tenant="t1", tenant_id="", service_id="s1", status_code=200, duration=0.2,
            billed_input=10, billed_output=20, model="gemma", model_id="hash-gemma-v1",
        )
        mw.metrics_collector.track_llm_tokens.assert_called_once()
        _, kwargs = mw.metrics_collector.track_llm_tokens.call_args
        assert kwargs["prompt_tokens"] == 10
        assert kwargs["completion_tokens"] == 20
        assert kwargs["total_tokens"] == 30
        assert kwargs["model"] == "gemma"
        assert kwargs["model_id"] == "hash-gemma-v1"

        mw.metrics_collector.track_request.assert_called_once()
        _, request_kwargs = mw.metrics_collector.track_request.call_args
        assert request_kwargs["model_id"] == "hash-gemma-v1"

    @pytest.mark.asyncio
    async def test_llm_skips_when_both_zero(self):
        mw = _middleware()
        await mw._record_metrics(
            path="/api/v1/chat", method="POST",
            service_type="llm", tenant="t1", tenant_id="", service_id="s1",
            status_code=200, duration=0.2,
            billed_input=0, billed_output=0,
        )
        mw.metrics_collector.track_llm_tokens.assert_not_called()


class TestValuesComeFromState:
    """AI4IDS-2532 follow-up: language labels and service_id are passed in
    from request.state (set once by task_service.py/orchestrator), same as
    billed_input/output — _record_metrics uses them verbatim, never a body."""

    @pytest.mark.asyncio
    async def test_language_labels_used_verbatim(self):
        mw = _middleware()
        await mw._record_metrics(
            path="/api/v1/nmt/inference", method="POST",
            service_type="translation", tenant="t1", tenant_id="", service_id="s1",
            status_code=200, duration=0.1,
            billed_input=10, billed_output=0,
            source_lang="en", target_lang="hi",
        )
        mw.metrics_collector.track_nmt_characters.assert_called_once_with(
            source_lang="en", target_lang="hi", characters=10,
            tenant="t1", tenant_id="", service_id="s1", auth_type="",
        )

    @pytest.mark.asyncio
    async def test_service_id_used_verbatim(self):
        mw = _middleware()
        await mw._record_metrics(
            path="/api/v1/nmt/inference", method="POST",
            service_type="translation", tenant="t1", tenant_id="", service_id="state-service-id",
            status_code=200, duration=0.1,
            billed_input=10, billed_output=0,
            source_lang="en", target_lang="hi",
        )
        _, kwargs = mw.metrics_collector.track_nmt_characters.call_args
        assert kwargs["service_id"] == "state-service-id"


class TestPerServiceUnitDispatch:
    def test_ocr_emits_billed_image_count_not_byte_heuristic(self):
        """billed_input for OCR is an image COUNT (the inference-type catalogue
        unit: images) — track_ocr_characters is repurposed to carry it."""
        mw = _middleware()
        mw._track_payload_metrics(
            service_type="ocr", billed_input=3, source_lang="", target_lang="",
            tenant="t1", service_id="s1",
        )
        mw.metrics_collector.track_ocr_characters.assert_called_once_with(
            characters=3, tenant="t1", tenant_id="", service_id="s1", auth_type="",
        )

    def test_ner_emits_billed_character_count_not_word_count(self):
        """billed_input for NER is a CHARACTER count, not len(text.split())."""
        mw = _middleware()
        mw._track_payload_metrics(
            service_type="ner", billed_input=42, source_lang="", target_lang="",
            tenant="t1", service_id="s1",
        )
        mw.metrics_collector.track_ner_tokens.assert_called_once_with(
            tokens=42, tenant="t1", tenant_id="", service_id="s1", auth_type="",
        )

    @pytest.mark.parametrize("service_type,tracker", [
        ("asr", "track_asr_audio_length"),
        ("audio_lang_detection", "track_audio_lang_detection_length"),
        ("speaker_diarization", "track_speaker_diarization_length"),
        ("language_diarization", "track_language_diarization_length"),
    ])
    def test_audio_minutes_passed_through_unconverted(self, service_type, tracker):
        """billed_input is already in minutes (the catalogue's unit:
        audio_minutes) — the histogram is minute-scaled too, so no conversion."""
        mw = _middleware()
        mw._track_payload_metrics(
            service_type=service_type, billed_input=2.5, source_lang="en",
            target_lang="", tenant="t1", service_id="s1",
        )
        getattr(mw.metrics_collector, tracker).assert_called_once()
        _, kwargs = getattr(mw.metrics_collector, tracker).call_args
        assert kwargs["audio_minutes"] == 2.5

    def test_tts_emits_billed_characters(self):
        """billed_input already reflects the post-chunk (<=400-char) sum
        accumulated by task_service, not raw pre-chunk length."""
        mw = _middleware()
        mw._track_payload_metrics(
            service_type="tts", billed_input=777, source_lang="hi",
            target_lang="", tenant="t1", service_id="s1",
        )
        mw.metrics_collector.track_tts_characters.assert_called_once_with(
            language="hi", characters=777, tenant="t1", tenant_id="", service_id="s1", auth_type="",
        )


def _app_with_middleware(state_setter):
    """Minimal FastAPI app with ObservabilityMiddleware mounted; the route
    handler mimics orchestrator.route_inference by setting request.state
    before returning, exactly like the real Triton/LLM code paths do."""
    app = FastAPI()
    app.add_middleware(
        ObservabilityMiddleware,
        metrics_collector=MagicMock(),
        config=PluginConfig(enabled=True),
    )

    @app.post("/api/v1/{task}/inference")
    async def handler(task: str, request: Request):
        state_setter(request)
        return {"ok": True}

    return app


class TestDispatchNeverReadsBody:
    """dispatch() must NEVER read/parse the request body — for any
    service_type, OCR included. Every value it needs (unit counts, language
    labels, service_id) comes from request.state, set once upstream
    (AI4IDS-2532 follow-up). The only body read on the request is FastAPI's
    own, for the route handler."""

    def _billed_state_setter(self, request):
        set_billed_state(request, billed_input=5)
        set_metric_labels(request, source_lang="en", target_lang="hi")
        request.state.service_id = "svc-1"

    @pytest.mark.parametrize("path,payload", [
        ("/api/v1/nmt/inference", {"input": []}),
        ("/api/v1/ocr/inference", {"image": []}),
    ])
    def test_middleware_adds_no_body_read(self, path, payload):
        app = _app_with_middleware(self._billed_state_setter)
        client = TestClient(app)

        original_body = StarletteRequest.body
        with patch.object(StarletteRequest, "body", autospec=True) as mock_body:
            mock_body.side_effect = original_body
            response = client.post(path, json=payload)

        assert response.status_code == 200
        # At most one body read total — FastAPI's own for the handler's
        # `request`/body binding. The middleware adds none of its own.
        assert mock_body.call_count <= 1
