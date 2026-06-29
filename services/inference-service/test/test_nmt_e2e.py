#!/usr/bin/env python3
"""
End-to-end integration tests for NMTTaskService.

Uses a real mapper with a representative v2 adapter_config (output_transform
pairs each translation with its input source), but mocks only the HTTP call to
Triton.

This mirrors how the service runs in production:
  process(payload) → validate → preprocess
                   → run_inference (real mapper, mocked HTTP) → plain dict response

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
# Representative v2 adapter config for indictrans
# (source, src-lang, tgt-lang → translation; output_transform pairs source/target)
# ---------------------------------------------------------------------------
_NMT_OUTPUT_TRANSFORM = (
    "( $inp := inputs; "
    "{ \"output\": [ $map(tensors.OUTPUT_TEXT, function($t, $i) "
    "{ {\"source\": $inp[$i].source, \"target\": $t} }) ] } )"
)

MOCK_ADAPTER_CONFIG = {
    "schema_version": "2.0",
    "model_version": "1",
    "inputs": [
        {"tensor": "INPUT_TEXT", "dtype": "BYTES", "shape": [-1, 1], "value_path": "input.source"},
        {"tensor": "SRC_LANG", "dtype": "BYTES", "shape": [-1, 1],
         "value_path": "request.config.language.sourceLanguage"},
        {"tensor": "TGT_LANG", "dtype": "BYTES", "shape": [-1, 1],
         "value_path": "request.config.language.targetLanguage"},
    ],
    "outputs": [{"tensor": "OUTPUT_TEXT"}],
    "output_transform": _NMT_OUTPUT_TRANSFORM,
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


async def test_full_pipeline_camel_payload():
    """process() with a camelCase portal payload → plain dict response."""
    from services.nmt_service import NMTTaskService

    service = NMTTaskService(service_info=MOCK_SERVICE_INFO)

    portal_payload = {
        "input": [{"source": "Hello, how are you?"}],
        "config": {
            "serviceId": "indictrans-v2-all",
            "language": {"sourceLanguage": "en", "targetLanguage": "hi"},
        },
    }

    with patch(
        "http_client.HTTPServiceClient.post_json",
        new=AsyncMock(return_value=MOCK_TRITON_RESPONSE_SINGLE),
    ):
        response = await service.process(portal_payload)

    assert isinstance(response, dict)
    assert len(response["output"]) == 1
    assert response["output"][0]["source"] == "Hello, how are you?"
    assert response["output"][0]["target"] == "नमस्ते, आप कैसे हैं?"
    logger.info("   [PASS] camelCase portal payload → correct plain dict response")


async def test_multi_input_pipeline():
    """Two input items → one batch Triton call → two output items."""
    from services.nmt_service import NMTTaskService

    service = NMTTaskService(service_info=MOCK_SERVICE_INFO)

    payload = {
        "input": [
            {"source": "Hello"},
            {"source": "Goodbye"},
        ],
        "config": {
            "language": {"sourceLanguage": "en", "targetLanguage": "hi"}
        },
    }

    # NMT runs in batch mode: one call, the response carries both translations.
    batch_response = {
        "outputs": [{"name": "OUTPUT_TEXT", "datatype": "BYTES",
                     "shape": [2, 1], "data": ["नमस्ते", "अलविदा"]}]
    }
    call_count = 0

    async def mock_post_json(self_, url, body, headers=None):
        nonlocal call_count
        call_count += 1
        return batch_response

    with patch("http_client.HTTPServiceClient.post_json", new=mock_post_json):
        response = await service.process(payload)

    assert isinstance(response, dict)
    assert len(response["output"]) == 2
    assert call_count == 1  # one batch Triton call for the whole input list
    assert response["output"][0]["source"] == "Hello"
    assert response["output"][0]["target"] == "नमस्ते"
    assert response["output"][1]["source"] == "Goodbye"
    assert response["output"][1]["target"] == "अलविदा"
    logger.info("   [PASS] two inputs → one batch call → two output items")


async def test_response_serialization():
    """Response is a plain dict — output key present with correct fields."""
    from services.nmt_service import NMTTaskService

    service = NMTTaskService(service_info=MOCK_SERVICE_INFO)

    payload = {
        "input": [{"source": "Hello"}],
        "config": {"language": {"sourceLanguage": "en", "targetLanguage": "hi"}},
    }

    with patch(
        "http_client.HTTPServiceClient.post_json",
        new=AsyncMock(return_value=MOCK_TRITON_RESPONSE_SINGLE),
    ):
        response = await service.process(payload)

    assert isinstance(response, dict)
    assert "output" in response
    assert response["output"][0]["source"] == "Hello"
    assert response["output"][0]["target"] == "नमस्ते, आप कैसे हैं?"
    logger.info("   [PASS] response is plain dict with correct output structure")


async def test_validate_same_language_rejected():
    """process() raises ValueError when source == target language."""
    from services.nmt_service import NMTTaskService

    service = NMTTaskService(service_info=MOCK_SERVICE_INFO)

    payload = {
        "input": [{"source": "Hello"}],
        "config": {"language": {"sourceLanguage": "hi", "targetLanguage": "hi"}},
    }

    try:
        await service.process(payload)
        raise AssertionError("Should have raised ValueError")
    except ValueError as e:
        assert "cannot be the same" in str(e)
        logger.info("   [PASS] same language pair rejected in full pipeline")


async def test_validate_whitespace_source_accepted():
    """Whitespace-only source is sanitised to single space and accepted."""
    from services.nmt_service import NMTTaskService

    service = NMTTaskService(service_info=MOCK_SERVICE_INFO)

    payload = {
        "input": [{"source": "   "}],
        "config": {"language": {"sourceLanguage": "en", "targetLanguage": "hi"}},
    }

    with patch(
        "http_client.HTTPServiceClient.post_json",
        new=AsyncMock(return_value=MOCK_TRITON_RESPONSE_SINGLE),
    ):
        response = await service.process(payload)

    assert isinstance(response, dict)
    # Source sanitised to " " (single space) — pipeline completes without error
    assert response["output"][0]["source"] == " "
    logger.info("   [PASS] whitespace-only source sanitised and accepted")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run_all():
    tests = [
        ("full pipeline — camelCase portal payload", test_full_pipeline_camel_payload),
        ("multi-input — one batch call", test_multi_input_pipeline),
        ("response serialization — plain dict", test_response_serialization),
        ("validation — same language rejected", test_validate_same_language_rejected),
        ("validation — whitespace source sanitised", test_validate_whitespace_source_accepted),
    ]

    logger.info("=" * 70)
    logger.info("NMTTaskService End-to-End Tests  (real mapper, mocked HTTP)")
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
