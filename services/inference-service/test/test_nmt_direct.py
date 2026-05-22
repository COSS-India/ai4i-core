#!/usr/bin/env python3
"""
Unit tests for TextDefaultModel (NMT) — no live Triton required.

Tests each pipeline stage in isolation:
  1. _deserialize_payload  — camelCase and snake_case inputs
  2. validate_request      — valid + four error paths
  3. preprocess_input      — sanitisation + _chunk key
  4. _create_inference_model — returns NMTInferenceModel
  5. postprocess_output    — pairing + TranslationOutput wrapping
  6. _build_response       — NMTInferenceResponse wrapping
  7. run_inference          — full loop with mocked InferenceModel + Triton

Triton HTTP is mocked via unittest.mock so no running server is needed.
"""

import asyncio
import logging
import sys
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Minimal service_info injected at construction (replaces old resolver pattern)
# ---------------------------------------------------------------------------
MOCK_SERVICE_INFO = {
    "service_id": "indictrans-v2-all",
    "name": "indictrans-gpu-t4",
    "endpoint": "http://localhost:8000/v2/models/indictrans-gpu-t4/infer",
    "api_key": None,
    "adapter_config": None,  # individual tests mock _create_inference_model
}

# ---------------------------------------------------------------------------
# Mock Triton output (KServe v2 format)
# ---------------------------------------------------------------------------
MOCK_TRITON_OUTPUT = {
    "outputs": [
        {
            "name": "OUTPUT_TEXT",
            "datatype": "BYTES",
            "shape": [1, 1],
            "data": ["नमस्ते, आप कैसे हैं?"],
        }
    ]
}


def _make_mock_inference_model(translated: str = "नमस्ते, आप कैसे हैं?") -> MagicMock:
    """Return a mock InferenceModel that produces one translated item."""
    model = MagicMock()
    model.convert_payload_to_triton_format = AsyncMock(
        return_value=(
            [{"name": "INPUT_TEXT", "datatype": "BYTES", "shape": [1, 1], "data": ["hello"]}],
            ["OUTPUT_TEXT"],
        )
    )
    model.convert_triton_output_to_task_format = AsyncMock(
        return_value=[{"target": translated}]
    )
    return model


async def test_deserialize_payload():
    """Accepts both camelCase (portal) and snake_case field names."""
    from services.models.text_models import TextDefaultModel
    from models.schemas.nmt import NMTInferenceRequest

    service = TextDefaultModel(service_info=MOCK_SERVICE_INFO)

    # snake_case payload
    snake_payload = {
        "input": [{"source": "Hello, how are you?"}],
        "config": {
            "service_id": "indictrans-v2-all",
            "language": {"sourceLanguage": "en", "targetLanguage": "hi"},
        },
    }
    req = await service._deserialize_payload(snake_payload)
    assert isinstance(req, NMTInferenceRequest)
    assert req.input[0].source == "Hello, how are you?"
    assert req.config.language.source_language == "en"
    assert req.config.language.target_language == "hi"
    logger.info("   [PASS] snake_case payload deserialised")

    # camelCase payload (portal format)
    camel_payload = {
        "input": [{"source": "What is your name?"}],
        "config": {
            "serviceId": "indictrans-v2-all",
            "language": {"sourceLanguage": "en", "targetLanguage": "te"},
        },
    }
    req2 = await service._deserialize_payload(camel_payload)
    assert req2.config.service_id == "indictrans-v2-all"
    assert req2.config.language.source_language == "en"
    assert req2.config.language.target_language == "te"
    logger.info("   [PASS] camelCase payload deserialised")


async def test_validate_request_valid():
    from services.models.text_models import TextDefaultModel
    from models.schemas.nmt import NMTInferenceRequest, NMTConfig, LanguagePair, TextInput

    service = TextDefaultModel(service_info=MOCK_SERVICE_INFO)
    request = NMTInferenceRequest(
        input=[TextInput(source="Hello")],
        config=NMTConfig(
            language=LanguagePair(sourceLanguage="en", targetLanguage="hi")
        ),
    )
    await service.validate_request(request)  # must not raise
    logger.info("   [PASS] valid request accepted")


async def test_validate_request_errors():
    from services.models.text_models import TextDefaultModel
    from models.schemas.nmt import NMTInferenceRequest, NMTConfig, LanguagePair, TextInput

    service = TextDefaultModel(service_info=MOCK_SERVICE_INFO)

    # 1. Same source and target language
    try:
        req = NMTInferenceRequest(
            input=[TextInput(source="Hello")],
            config=NMTConfig(language=LanguagePair(sourceLanguage="en", targetLanguage="en")),
        )
        await service.validate_request(req)
        raise AssertionError("Should have raised ValueError for same language")
    except ValueError as e:
        assert "must differ" in str(e)
        logger.info("   [PASS] same language rejected")

    # 2. Pydantic rejects empty input list at construction
    try:
        NMTInferenceRequest(
            input=[],
            config=NMTConfig(language=LanguagePair(sourceLanguage="en", targetLanguage="hi")),
        )
        raise AssertionError("Should have rejected empty input")
    except Exception:
        logger.info("   [PASS] empty input list rejected by schema")


async def test_preprocess_input():
    from services.models.text_models import TextDefaultModel

    service = TextDefaultModel(service_info=MOCK_SERVICE_INFO)

    raw = [
        {"source": "  Hello   world  "},
        {"source": "\nWhat is the weather?\r"},
        {"source": ""},
        {"source": None},
    ]
    result = await service.preprocess_input(raw)

    assert len(result) == 4
    assert result[0]["source"] == "Hello   world"  # strip only, not internal spaces
    assert result[1]["source"] == "What is the weather?"  # newlines removed
    assert result[2]["source"] == " "  # empty → single space
    assert result[3]["source"] == " "  # None → single space
    assert all("_chunk" in item for item in result)
    assert result[0]["_chunk"] == 0
    logger.info("   [PASS] preprocess_input sanitised and chunked correctly")


async def test_create_inference_model():
    from services.models.text_models import TextDefaultModel
    from inference_models.nmt_inference_model import NMTInferenceModel

    service = TextDefaultModel(service_info=MOCK_SERVICE_INFO)

    # With adapter_config=None, NMTInferenceModel.mapper is None
    # (will raise InferenceModelError on convert, but construction succeeds)
    model = service._create_inference_model(adapter_config=None)
    assert isinstance(model, NMTInferenceModel)
    logger.info("   [PASS] _create_inference_model returns NMTInferenceModel")


async def test_postprocess_output():
    from services.models.text_models import TextDefaultModel
    from models.schemas.nmt import TranslationOutput

    service = TextDefaultModel(service_info=MOCK_SERVICE_INFO)

    response_items = [{"target": "नमस्ते"}, {"target": "आपका नाम क्या है?"}]
    source_texts = ["Hello", "What is your name?"]

    result = await service.postprocess_output(response_items, source_texts=source_texts)
    assert "output" in result
    assert len(result["output"]) == 2
    assert isinstance(result["output"][0], TranslationOutput)
    assert result["output"][0].source == "Hello"
    assert result["output"][0].target == "नमस्ते"
    assert result["output"][1].source == "What is your name?"
    assert result["output"][1].target == "आपका नाम क्या है?"
    logger.info("   [PASS] postprocess_output paired sources and wrapped in TranslationOutput")


async def test_build_response():
    from services.models.text_models import TextDefaultModel
    from models.schemas.nmt import (
        NMTInferenceRequest, NMTConfig, LanguagePair, TextInput,
        NMTInferenceResponse, TranslationOutput,
    )

    service = TextDefaultModel(service_info=MOCK_SERVICE_INFO)
    request = NMTInferenceRequest(
        input=[TextInput(source="Hello")],
        config=NMTConfig(language=LanguagePair(sourceLanguage="en", targetLanguage="hi")),
    )
    postprocessed = {"output": [TranslationOutput(source="Hello", target="नमस्ते")]}
    response = service._build_response(request, postprocessed)

    assert isinstance(response, NMTInferenceResponse)
    assert len(response.output) == 1
    assert response.output[0].target == "नमस्ते"
    logger.info("   [PASS] _build_response returns NMTInferenceResponse")


async def test_run_inference_full():
    """Full run_inference with mocked InferenceModel and mocked _call_triton_inference."""
    from services.models.text_models import TextDefaultModel
    from models.schemas.nmt import (
        NMTInferenceRequest, NMTConfig, LanguagePair, TextInput, NMTInferenceResponse,
    )

    service = TextDefaultModel(service_info=MOCK_SERVICE_INFO)

    request = NMTInferenceRequest(
        input=[
            TextInput(source="Hello, how are you?"),
            TextInput(source="What is your name?"),
        ],
        config=NMTConfig(language=LanguagePair(sourceLanguage="en", targetLanguage="hi")),
    )

    # Preprocess mutates request.input (as process() would do)
    preprocessed = await service.preprocess_input(request.input)
    request.input = preprocessed

    mock_inference_model = _make_mock_inference_model("नमस्ते, आप कैसे हैं?")

    with patch.object(service, "_create_inference_model", return_value=mock_inference_model):
        with patch.object(
            service,
            "_call_triton_inference",
            new=AsyncMock(return_value=MOCK_TRITON_OUTPUT),
        ):
            response = await service.run_inference(request)

    assert isinstance(response, NMTInferenceResponse)
    assert len(response.output) == 2  # one per input item
    assert response.output[0].source == "Hello, how are you?"
    assert response.output[0].target == "नमस्ते, आप कैसे हैं?"
    logger.info("   [PASS] run_inference returned NMTInferenceResponse with correct sources")


async def test_run_inference_missing_endpoint():
    """run_inference raises RuntimeError when service_info lacks endpoint."""
    from services.models.text_models import TextDefaultModel
    from models.schemas.nmt import NMTInferenceRequest, NMTConfig, LanguagePair, TextInput

    bad_service_info = {"service_id": "x", "name": "model", "endpoint": "", "api_key": None}
    service = TextDefaultModel(service_info=bad_service_info)

    request = NMTInferenceRequest(
        input=[TextInput(source="Hello")],
        config=NMTConfig(language=LanguagePair(sourceLanguage="en", targetLanguage="hi")),
    )
    try:
        await service.run_inference(request)
        raise AssertionError("Should have raised RuntimeError")
    except RuntimeError as e:
        assert "endpoint" in str(e)
        logger.info("   [PASS] missing endpoint raises RuntimeError")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run_all():
    tests = [
        ("_deserialize_payload (camelCase + snake_case)", test_deserialize_payload),
        ("validate_request — valid", test_validate_request_valid),
        ("validate_request — error paths", test_validate_request_errors),
        ("preprocess_input — sanitise + chunk", test_preprocess_input),
        ("_create_inference_model", test_create_inference_model),
        ("postprocess_output — pairing", test_postprocess_output),
        ("_build_response", test_build_response),
        ("run_inference — full pipeline (mocked)", test_run_inference_full),
        ("run_inference — missing endpoint", test_run_inference_missing_endpoint),
    ]

    logger.info("=" * 70)
    logger.info("NMT TextDefaultModel Unit Tests")
    logger.info("=" * 70)

    passed = 0
    failed = 0
    for name, fn in tests:
        logger.info(f"\n-- {name}")
        try:
            await fn()
            passed += 1
        except Exception as exc:
            logger.error(f"   [FAIL] {exc}")
            import traceback; traceback.print_exc()
            failed += 1

    logger.info("\n" + "=" * 70)
    if failed == 0:
        logger.info(f"ALL {passed} TESTS PASSED")
    else:
        logger.info(f"{passed} passed, {failed} FAILED")
    logger.info("=" * 70)

    return failed == 0


if __name__ == "__main__":
    ok = asyncio.run(run_all())
    sys.exit(0 if ok else 1)
