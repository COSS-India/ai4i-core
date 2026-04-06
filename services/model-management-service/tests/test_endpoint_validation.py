"""
Unit tests for endpoint / inference validation (httpx mocked; no real network).
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from validation.inference_probe import validate_hosted_inference_endpoint
from validation.triton_payload import build_triton_infer_body, _b64
from validation.types import EndpointValidationFailure, ValidationStage
from validation.url import normalize_http_url


def _http_response(status_code, *, json_body=None, text=""):
    m = MagicMock(spec=httpx.Response)
    m.status_code = status_code
    m.text = text
    if json_body is not None:
        m.json = MagicMock(return_value=json_body)
    else:
        m.json = MagicMock(side_effect=ValueError("no json"))
    return m


# ── URL validation ──────────────────────────────────────────────────────────

@pytest.mark.unit
class TestNormalizeHttpUrl:
    def test_accepts_valid_https(self):
        assert normalize_http_url("https://triton.example.com:8000").startswith("https://")

    def test_rejects_non_http_scheme(self):
        with pytest.raises(ValueError, match="http or https"):
            normalize_http_url("ftp://host")


# ── Triton payload builder ──────────────────────────────────────────────────

@pytest.mark.unit
class TestBuildTritonInferBody:
    """Verify that task-aware Triton payloads use real language codes."""

    def test_nmt_model_uses_language_codes_from_model(self):
        metadata = {
            "inputs": [
                {"name": "INPUT_TEXT", "datatype": "BYTES", "shape": [1]},
                {"name": "INPUT_LANGUAGE_ID", "datatype": "BYTES", "shape": [1]},
                {"name": "OUTPUT_LANGUAGE_ID", "datatype": "BYTES", "shape": [1]},
            ],
            "outputs": [{"name": "OUTPUT_TEXT"}],
        }
        langs = [{"sourceLanguage": "ta", "targetLanguage": "en"}]

        body = build_triton_infer_body(metadata, languages=langs)

        assert body is not None
        inputs_by_name = {i["name"]: i for i in body["inputs"]}
        assert inputs_by_name["INPUT_TEXT"]["data"] == [_b64("validation")]
        assert inputs_by_name["INPUT_LANGUAGE_ID"]["data"] == [_b64("ta")]
        assert inputs_by_name["OUTPUT_LANGUAGE_ID"]["data"] == [_b64("en")]

    def test_defaults_to_en_hi_when_no_languages(self):
        metadata = {
            "inputs": [
                {"name": "INPUT_LANGUAGE_ID", "datatype": "BYTES", "shape": [1]},
                {"name": "OUTPUT_LANGUAGE_ID", "datatype": "BYTES", "shape": [1]},
            ],
        }
        body = build_triton_infer_body(metadata)
        inputs_by_name = {i["name"]: i for i in body["inputs"]}
        assert inputs_by_name["INPUT_LANGUAGE_ID"]["data"] == [_b64("en")]
        assert inputs_by_name["OUTPUT_LANGUAGE_ID"]["data"] == [_b64("hi")]

    def test_numeric_inputs_get_zeros(self):
        metadata = {"inputs": [{"name": "features", "datatype": "FP32", "shape": [1, 3]}]}
        body = build_triton_infer_body(metadata)
        assert body["inputs"][0]["data"] == [0.0, 0.0, 0.0]

    def test_returns_none_when_no_inputs(self):
        assert build_triton_infer_body({}) is None
        assert build_triton_infer_body({"inputs": []}) is None


# ── Full probe ──────────────────────────────────────────────────────────────

@pytest.mark.unit
@pytest.mark.endpoint_validation
class TestValidateHostedInferenceEndpoint:
    """``validate_hosted_inference_endpoint`` with ``httpx.AsyncClient`` fully mocked."""

    @staticmethod
    def _client_context(inner):
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=inner)
        cm.__aexit__ = AsyncMock(return_value=None)
        return cm

    @pytest.mark.asyncio
    async def test_triton_full_path_infer_succeeds(self):
        """Health → model ready → metadata → infer 200."""
        inner = MagicMock()
        meta = {
            "inputs": [
                {"name": "INPUT_TEXT", "datatype": "BYTES", "shape": [1]},
                {"name": "INPUT_LANGUAGE_ID", "datatype": "BYTES", "shape": [1]},
                {"name": "OUTPUT_LANGUAGE_ID", "datatype": "BYTES", "shape": [1]},
            ],
            "outputs": [{"name": "OUTPUT_TEXT"}],
        }

        async def get_impl(url, **kwargs):
            if url.endswith("/v2/health/live"):
                return _http_response(200)
            if url.endswith("/v2/health/ready"):
                return _http_response(200)
            if "/v2/models/" in url and url.endswith("/ready"):
                return _http_response(200, json_body={"ready": True})
            if "/v2/models/" in url and not url.endswith("/ready") and "/infer" not in url:
                return _http_response(200, json_body=meta)
            return _http_response(404)

        inner.get = AsyncMock(side_effect=get_impl)
        inner.post = AsyncMock(return_value=_http_response(200, json_body={}))

        with patch(
            "validation.inference_probe.httpx.AsyncClient",
            return_value=self._client_context(inner),
        ):
            result = await validate_hosted_inference_endpoint(
                "http://triton:8000",
                None,
                {"schema": {"model_name": "nmt", "request": {}, "response": {}}},
                "nmt",
                languages=[{"sourceLanguage": "en", "targetLanguage": "hi"}],
            )

        assert result.ok is True
        assert result.stage == ValidationStage.TRITON_INFER
        inner.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_triton_missing_model_name_fails(self):
        inner = MagicMock()
        inner.get = AsyncMock(return_value=_http_response(200))

        with patch(
            "validation.inference_probe.httpx.AsyncClient",
            return_value=self._client_context(inner),
        ):
            with pytest.raises(EndpointValidationFailure) as ei:
                await validate_hosted_inference_endpoint(
                    "http://triton:8000", None, {}, "nmt",
                )

        assert ei.value.stage == ValidationStage.TRITON_MODEL_READY
        assert "model name" in ei.value.message.lower()

    @pytest.mark.asyncio
    async def test_triton_model_ready_fails(self):
        inner = MagicMock()

        async def get_impl(url, **kwargs):
            if url.endswith("/v2/health/live"):
                return _http_response(200)
            if url.endswith("/v2/health/ready"):
                return _http_response(404)
            if "/v2/models/" in url and url.endswith("/ready"):
                return _http_response(404, text="not found")
            return _http_response(404)

        inner.get = AsyncMock(side_effect=get_impl)

        with patch(
            "validation.inference_probe.httpx.AsyncClient",
            return_value=self._client_context(inner),
        ):
            with pytest.raises(EndpointValidationFailure) as ei:
                await validate_hosted_inference_endpoint(
                    "http://triton:8000",
                    None,
                    {"schema": {"model_name": "m"}},
                    "nmt",
                )

        assert ei.value.stage == ValidationStage.TRITON_MODEL_READY

    @pytest.mark.asyncio
    async def test_triton_infer_failure_raises(self):
        inner = MagicMock()
        meta = {
            "inputs": [{"name": "IN", "datatype": "FP32", "shape": [1]}],
            "outputs": [{"name": "OUT"}],
        }

        async def get_impl(url, **kwargs):
            if url.endswith("/v2/health/live"):
                return _http_response(200)
            if url.endswith("/v2/health/ready"):
                return _http_response(200)
            if "/v2/models/" in url and url.endswith("/ready"):
                return _http_response(200, json_body={"ready": True})
            if "/v2/models/" in url and not url.endswith("/ready") and "/infer" not in url:
                return _http_response(200, json_body=meta)
            return _http_response(404)

        inner.get = AsyncMock(side_effect=get_impl)
        inner.post = AsyncMock(return_value=_http_response(500, text="model error"))

        with patch(
            "validation.inference_probe.httpx.AsyncClient",
            return_value=self._client_context(inner),
        ):
            with pytest.raises(EndpointValidationFailure) as ei:
                await validate_hosted_inference_endpoint(
                    "http://triton:8000",
                    None,
                    {"schema": {"model_name": "m"}},
                    "nmt",
                )

        assert ei.value.stage == ValidationStage.TRITON_INFER

    @pytest.mark.asyncio
    async def test_triton_metadata_unavailable_skips_infer(self):
        """Model ready succeeds but metadata 404 → pass without infer."""
        inner = MagicMock()

        async def get_impl(url, **kwargs):
            if url.endswith("/v2/health/live"):
                return _http_response(200)
            if url.endswith("/v2/health/ready"):
                return _http_response(200)
            if "/v2/models/" in url and url.endswith("/ready"):
                return _http_response(200)
            if "/v2/models/" in url:
                return _http_response(404)
            return _http_response(404)

        inner.get = AsyncMock(side_effect=get_impl)
        inner.post = AsyncMock()

        with patch(
            "validation.inference_probe.httpx.AsyncClient",
            return_value=self._client_context(inner),
        ):
            result = await validate_hosted_inference_endpoint(
                "http://triton:8000",
                None,
                {"schema": {"model_name": "m"}},
                "nmt",
            )

        assert result.ok is True
        assert result.stage == ValidationStage.TRITON_MODEL_READY
        inner.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_generic_json_probe_2xx(self):
        inner = MagicMock()
        inner.get = AsyncMock(side_effect=[_http_response(404), _http_response(404)])
        inner.post = AsyncMock(return_value=_http_response(200, json_body={"ok": True}))

        with patch(
            "validation.inference_probe.httpx.AsyncClient",
            return_value=self._client_context(inner),
        ):
            result = await validate_hosted_inference_endpoint(
                "http://rest-api:9000/v1/infer",
                "secret",
                {"schema": {"request": {"custom": True}, "response": {}}},
                "asr",
            )

        assert result.ok is True
        assert result.stage == ValidationStage.GENERIC_JSON_PROBE
        call_kw = inner.post.await_args
        assert "Authorization" in call_kw.kwargs.get("headers", {})

    @pytest.mark.asyncio
    async def test_generic_json_probe_500_fails(self):
        inner = MagicMock()
        inner.get = AsyncMock(side_effect=[_http_response(404), _http_response(404)])
        inner.post = AsyncMock(return_value=_http_response(503, text="bad"))

        with patch(
            "validation.inference_probe.httpx.AsyncClient",
            return_value=self._client_context(inner),
        ):
            with pytest.raises(EndpointValidationFailure) as ei:
                await validate_hosted_inference_endpoint(
                    "http://rest:8080/", None, {}, "llm",
                )

        assert ei.value.stage == ValidationStage.GENERIC_JSON_PROBE

    @pytest.mark.asyncio
    async def test_connectivity_raises_on_request_error(self):
        inner = MagicMock()
        inner.get = AsyncMock(side_effect=httpx.ConnectError("refused", request=MagicMock()))

        with patch(
            "validation.inference_probe.httpx.AsyncClient",
            return_value=self._client_context(inner),
        ):
            with pytest.raises(EndpointValidationFailure) as ei:
                await validate_hosted_inference_endpoint(
                    "http://localhost:9", None, {}, "nmt",
                )

        assert ei.value.stage == ValidationStage.CONNECTIVITY

    @pytest.mark.asyncio
    async def test_triton_health_503_no_generic_fallback(self):
        inner = MagicMock()
        inner.get = AsyncMock(side_effect=[_http_response(503), _http_response(503)])
        inner.post = AsyncMock()

        with patch(
            "validation.inference_probe.httpx.AsyncClient",
            return_value=self._client_context(inner),
        ):
            with pytest.raises(EndpointValidationFailure) as ei:
                await validate_hosted_inference_endpoint(
                    "http://triton:8000", None,
                    {"schema": {"model_name": "m"}}, "nmt",
                )

        assert ei.value.stage == ValidationStage.CONNECTIVITY
        inner.post.assert_not_called()
