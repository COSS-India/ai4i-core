#!/usr/bin/env python3
"""
End-to-end integration tests for TextDefaultModel (NMT).

Uses a real NMTInferenceModel + real GenericTritonMapper with a representative
adapter_config, but mocks only the HTTP call to Triton.

This mirrors how the service runs in production:
  process(payload) → _deserialize_payload → validate → preprocess
                   → run_inference (real mapper, mocked HTTP) → NMTInferenceResponse

Run from the inference-service root:
    python test/test_nmt_e2e.py
"""

import asyncio
import logging
import sys
from unittest.mock import AsyncMock, patch

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Representative adapter config for indictrans (source, src-lang, tgt-lang → translation)
# value_path keys use snake_case to match model_dump(by_alias=False) output
# ---------------------------------------------------------------------------
MOCK_ADAPTER_CONFIG = {
    "version": "1.0",
    "model_version": "1",
    "inputs": [
        {
            "tensor": "INPUT_TEXT",
            "dtype": "BYTES",
            "shape": [1, 1],
            "value_path": "input.source",
        },
        {
            "tensor": "SRC_LANG",
            "dtype": "BYTES",
            "shape": [1, 1],
            "value_path": "request.config.language.source_language",
        },
        {
            "tensor": "TGT_LANG",
            "dtype": "BYTES",
            "shape": [1, 1],
            "value_path": "request.config.language.target_language",
        },
    ],
    "outputs": [
        {
            "tensor": "OUTPUT_TEXT",
            "dtype": "BYTES",
            "maps_to": "target",
        }
    ],
}

MOCK_SERVICE_INFO = {
    "service_id": "indictrans-v2-all",
    "name": "indictrans-gpu-t4",
    "endpoint": "http://localhost:8000/v2/models/indictrans-gpu-t4/infer",
    "api_key": None,
    "adapter_config": MOCK_ADAPTER_CONFIG,
}

# ---------------------------------------------------------------------------
# Mock Triton response (KServe v2 format, one translated item)
# ---------------------------------------------------------------------------
MOCK_TRITON_RESPONSE_SINGLE = {
    "outputs": [
        {
            "name": "OUTPUT_TEXT",
            "datatype": "BYTES",
            "shape": [1, 1],
            "data": ["नमस्ते, आप कैसे हैं?"],
        }
    ]
}

MOCK_TRITON_RESPONSE_HINDI = {
    "outputs": [
        {"name": "OUTPUT_TEXT", "datatype": "BYTES", "shape": [1, 1], "data": ["आपका नाम क्या है?"]}
    ]
}


async def test_full_pipeline_camel_payload():
    """process() with a camelCase portal payload → NMTInferenceResponse."""
    from services.models.text_models import TextDefaultModel
    from models.schemas.nmt import NMTInferenceResponse

    service = TextDefaultModel(service_info=MOCK_SERVICE_INFO)

    portal_payload = {
        "input": [{"source": "Hello, how are you?"}],
        "config": {
            "serviceId": "indictrans-v2-all",
            "language": {"sourceLanguage": "en", "targetLanguage": "hi"},
        },
    }

    with patch(
        "utils.http_client.HTTPServiceClient.post_json",
        new=AsyncMock(return_value=MOCK_TRITON_RESPONSE_SINGLE),
    ):
        response = await service.process(portal_payload)

    assert isinstance(response, NMTInferenceResponse)
    assert len(response.output) == 1
    assert response.output[0].source == "Hello, how are you?"
    assert response.output[0].target == "नमस्ते, आप कैसे हैं?"
    logger.info("   [PASS] camelCase portal payload → correct NMTInferenceResponse")


async def test_full_pipeline_snake_payload():
    """process() with snake_case payload (both naming conventions work)."""
    from services.models.text_models import TextDefaultModel
    from models.schemas.nmt import NMTInferenceResponse

    service = TextDefaultModel(service_info=MOCK_SERVICE_INFO)

    snake_payload = {
        "input": [{"source": "What is your name?"}],
        "config": {
            "service_id": "indictrans-v2-all",
            "language": {"sourceLanguage": "en", "targetLanguage": "hi"},
        },
    }

    with patch(
        "utils.http_client.HTTPServiceClient.post_json",
        new=AsyncMock(return_value=MOCK_TRITON_RESPONSE_HINDI),
    ):
        response = await service.process(snake_payload)

    assert isinstance(response, NMTInferenceResponse)
    assert response.output[0].target == "आपका नाम क्या है?"
    logger.info("   [PASS] snake_case payload → correct NMTInferenceResponse")


async def test_multi_input_pipeline():
    """Two input items → two separate Triton calls → two TranslationOutput items."""
    from services.models.text_models import TextDefaultModel
    from models.schemas.nmt import NMTInferenceResponse

    service = TextDefaultModel(service_info=MOCK_SERVICE_INFO)

    payload = {
        "input": [
            {"source": "Hello"},
            {"source": "Goodbye"},
        ],
        "config": {
            "language": {"sourceLanguage": "en", "targetLanguage": "hi"}
        },
    }

    triton_responses = [
        {"outputs": [{"name": "OUTPUT_TEXT", "datatype": "BYTES", "shape": [1, 1], "data": ["नमस्ते"]}]},
        {"outputs": [{"name": "OUTPUT_TEXT", "datatype": "BYTES", "shape": [1, 1], "data": ["अलविदा"]}]},
    ]
    call_count = 0

    async def mock_post_json(url, body, headers=None):
        nonlocal call_count
        result = triton_responses[call_count]
        call_count += 1
        return result

    with patch("utils.http_client.HTTPServiceClient.post_json", new=mock_post_json):
        response = await service.process(payload)

    assert isinstance(response, NMTInferenceResponse)
    assert len(response.output) == 2
    assert call_count == 2  # one Triton call per input item
    assert response.output[0].source == "Hello"
    assert response.output[0].target == "नमस्ते"
    assert response.output[1].source == "Goodbye"
    assert response.output[1].target == "अलविदा"
    logger.info("   [PASS] two inputs → two Triton calls → two TranslationOutput items")


async def test_response_serialization():
    """NMTInferenceResponse.model_dump() excludes None fields."""
    from services.models.text_models import TextDefaultModel

    service = TextDefaultModel(service_info=MOCK_SERVICE_INFO)

    payload = {
        "input": [{"source": "Hello"}],
        "config": {"language": {"sourceLanguage": "en", "targetLanguage": "hi"}},
    }

    with patch(
        "utils.http_client.HTTPServiceClient.post_json",
        new=AsyncMock(return_value=MOCK_TRITON_RESPONSE_SINGLE),
    ):
        response = await service.process(payload)

    serialized = response.model_dump()
    assert "smr_response" not in serialized  # None fields excluded
    assert "output" in serialized
    assert serialized["output"][0]["source"] == "Hello, how are you?"
    assert serialized["output"][0]["target"] == "नमस्ते, आप कैसे हैं?"
    logger.info("   [PASS] model_dump() excludes None + contains correct output")


async def test_validate_same_language_rejected():
    """process() raises ValueError when source == target language."""
    from services.models.text_models import TextDefaultModel

    service = TextDefaultModel(service_info=MOCK_SERVICE_INFO)

    payload = {
        "input": [{"source": "Hello"}],
        "config": {"language": {"sourceLanguage": "hi", "targetLanguage": "hi"}},
    }

    try:
        await service.process(payload)
        raise AssertionError("Should have raised ValueError")
    except ValueError as e:
        assert "must differ" in str(e)
        logger.info("   [PASS] same language pair rejected in full pipeline")


async def test_validate_whitespace_source_accepted():
    """Whitespace-only source is sanitised to single space and accepted."""
    from services.models.text_models import TextDefaultModel
    from models.schemas.nmt import NMTInferenceResponse

    service = TextDefaultModel(service_info=MOCK_SERVICE_INFO)

    payload = {
        "input": [{"source": "   "}],
        "config": {"language": {"sourceLanguage": "en", "targetLanguage": "hi"}},
    }

    with patch(
        "utils.http_client.HTTPServiceClient.post_json",
        new=AsyncMock(return_value=MOCK_TRITON_RESPONSE_SINGLE),
    ):
        response = await service.process(payload)

    assert isinstance(response, NMTInferenceResponse)
    # Source sanitised to " " (single space) — pipeline completes without error
    assert response.output[0].source == " "
    logger.info("   [PASS] whitespace-only source sanitised and accepted")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run_all():
    tests = [
        ("full pipeline — camelCase portal payload", test_full_pipeline_camel_payload),
        ("full pipeline — snake_case payload", test_full_pipeline_snake_payload),
        ("multi-input — two Triton calls", test_multi_input_pipeline),
        ("response serialization — exclude_none", test_response_serialization),
        ("validation — same language rejected", test_validate_same_language_rejected),
        ("validation — whitespace source sanitised", test_validate_whitespace_source_accepted),
    ]

    logger.info("=" * 70)
    logger.info("NMT TextDefaultModel End-to-End Tests  (real mapper, mocked HTTP)")
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
