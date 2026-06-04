#!/usr/bin/env python3
"""
Unit tests for NMTTaskService — no live Triton required.

Tests each pipeline stage in isolation:
  1. validate_request      — valid + four error paths
  2. preprocess_input      — sanitisation
  3. payload_key           — modality input key
  4. postprocess_output    — pairing + unwrap, returns plain dict with output list
  5. process               — full pipeline with mocked GenericTritonMapper + Triton

Triton HTTP is mocked via unittest.mock so no running server is needed.
"""

import asyncio
import logging
import sys
from typing import List
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
    "adapter_config": None,
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


def _make_mock_inference_model(translated: str = "नमस्ते, आप कैसे हैं?", num_outputs: int = 1) -> MagicMock:
    """Return a mock InferenceModel that produces `num_outputs` translated items."""
    model = MagicMock()
    model.convert_payload_to_triton_format = AsyncMock(
        return_value=(
            [{"name": "INPUT_TEXT", "datatype": "BYTES", "shape": [1, 1], "data": ["hello"]}],
            ["OUTPUT_TEXT"],
        )
    )
    model.convert_triton_output_to_task_format = AsyncMock(
        return_value=[{"target": translated}] * num_outputs
    )
    return model


async def test_validate_request_valid():
    from services.nmt_service import NMTTaskService

    service = NMTTaskService(service_info=MOCK_SERVICE_INFO)
    payload = {
        "input": [{"source": "Hello"}],
        "config": {
            "service_id": "indictrans-v2-all",
            "language": {"sourceLanguage": "en", "targetLanguage": "hi"},
        },
    }
    await service.validate_request(payload)  # must not raise
    logger.info("   [PASS] valid request accepted")


async def test_validate_request_errors():
    from services.nmt_service import NMTTaskService

    service = NMTTaskService(service_info=MOCK_SERVICE_INFO)

    # 1. Same source and target language
    try:
        payload = {
            "input": [{"source": "Hello"}],
            "config": {"language": {"sourceLanguage": "en", "targetLanguage": "en"}},
        }
        await service.validate_request(payload)
        raise AssertionError("Should have raised ValueError for same language")
    except ValueError as e:
        assert "cannot be the same" in str(e)
        logger.info("   [PASS] same language rejected")

    # 2. Empty input list
    try:
        payload = {
            "input": [],
            "config": {"language": {"sourceLanguage": "en", "targetLanguage": "hi"}},
        }
        await service.validate_request(payload)
        raise AssertionError("Should have rejected empty input")
    except ValueError:
        logger.info("   [PASS] empty input list rejected")

    # 3. Missing language pair
    try:
        payload = {
            "input": [{"source": "Hello"}],
            "config": {"language": {}},
        }
        await service.validate_request(payload)
        raise AssertionError("Should have raised ValueError for missing language")
    except ValueError as e:
        assert "required" in str(e)
        logger.info("   [PASS] missing language pair rejected")


async def test_preprocess_input():
    from services.nmt_service import NMTTaskService

    service = NMTTaskService(service_info=MOCK_SERVICE_INFO)

    payload = {"input": [
        {"source": "  Hello   world  "},
        {"source": "\nWhat is the weather?\r"},
        {"source": ""},
        {"source": None},
    ], "config": {}}
    result = (await service.preprocess_input(payload))["input"]

    assert len(result) == 4
    assert result[0]["source"] == "Hello world"  # internal whitespace collapsed by _normalize_text
    assert result[1]["source"] == "What is the weather?"  # newlines removed
    assert result[2]["source"] == " "  # empty → single space
    assert result[3]["source"] == " "  # None → single space
    logger.info("   [PASS] preprocess_input sanitised correctly")


async def test_payload_key():
    from services.nmt_service import NMTTaskService

    service = NMTTaskService(service_info=MOCK_SERVICE_INFO)
    assert service.payload_key == "input"
    logger.info("   [PASS] payload_key is 'input'")


async def test_postprocess_output():
    from services.nmt_service import NMTTaskService

    service = NMTTaskService(service_info=MOCK_SERVICE_INFO)
    payload = {
        "input": [{"source": "Hello"}, {"source": "What is your name?"}],
        "config": {"language": {"sourceLanguage": "en", "targetLanguage": "hi"}},
    }
    response_items = [{"target": ["नमस्ते"]}, {"target": b"\xe0\xa4\x86\xe0\xa4\xaa\xe0\xa4\x95\xe0\xa4\xbe \xe0\xa4\xa8\xe0\xa4\xbe\xe0\xa4\xae \xe0\xa4\x95\xe0\xa5\x8d\xe0\xa4\xaf\xe0\xa4\xbe \xe0\xa4\xb9\xe0\xa5\x88?"}]
    source_texts = ["Hello", "What is your name?"]

    from services.base.task_service import PostProcessFormat
    response = await service.postprocess_output(
        PostProcessFormat(payload=payload, response_data=response_items, source_texts=source_texts)
    )
    assert "output" in response
    assert len(response["output"]) == 2
    assert isinstance(response["output"][0], dict)
    # single-element list and bytes targets are unwrapped/decoded
    assert response["output"][0]["source"] == "Hello"
    assert response["output"][0]["target"] == "नमस्ते"
    assert response["output"][1]["source"] == "What is your name?"
    assert response["output"][1]["target"] == "आपका नाम क्या है?"
    logger.info("   [PASS] postprocess paired sources, unwrapped values, returned plain dicts")


async def test_process_full():
    """Full process() pipeline with mocked InferenceModel and mocked Triton."""
    from services.nmt_service import NMTTaskService

    service = NMTTaskService(service_info=MOCK_SERVICE_INFO)

    payload = {
        "input": [
            {"source": "Hello, how are you?"},
            {"source": "What is your name?"},
        ],
        "config": {
            "service_id": "indictrans-v2-all",
            "language": {"sourceLanguage": "en", "targetLanguage": "hi"},
        },
    }

    mock_inference_model = _make_mock_inference_model("नमस्ते, आप कैसे हैं?", num_outputs=2)

    # run_inference instantiates GenericTritonMapper from its module —
    # patch the class there so the mock mapper is used.
    with patch(
        "services.base.config_mapper.GenericTritonMapper",
        MagicMock(return_value=mock_inference_model),
    ):
        with patch.object(
            service,
            "_call_triton_inference",
            new=AsyncMock(return_value=MOCK_TRITON_OUTPUT),
        ):
            response = await service.process(payload, MOCK_SERVICE_INFO)

    assert isinstance(response, dict)
    assert len(response["output"]) == 2  # one per input item
    assert response["output"][0]["source"] == "Hello, how are you?"
    assert response["output"][0]["target"] == "नमस्ते, आप कैसे हैं?"
    logger.info("   [PASS] process returned dict with correct sources")


async def test_process_missing_endpoint():
    """process raises RuntimeError when service_info lacks endpoint."""
    from services.nmt_service import NMTTaskService

    bad_service_info = {"service_id": "x", "name": "model", "endpoint": "", "api_key": None}
    service = NMTTaskService(service_info=bad_service_info)

    payload = {
        "input": [{"source": "Hello"}],
        "config": {"language": {"sourceLanguage": "en", "targetLanguage": "hi"}},
    }
    try:
        await service.process(payload)
        raise AssertionError("Should have raised RuntimeError")
    except RuntimeError as e:
        assert "endpoint" in str(e)
        logger.info("   [PASS] missing endpoint raises RuntimeError")


async def test_resolver_url_construction():
    """InferenceServerResolver builds /api/v1/services/{id} regardless of trailing slash."""
    from unittest.mock import patch as _patch
    from inference.inference_server_resolver import InferenceServerResolver

    resolver = InferenceServerResolver()
    captured: List[str] = []

    async def _mock_get_json(self_or_url, url=None):
        actual_url = url if url is not None else self_or_url
        captured.append(actual_url)
        return {
            "service_id": "indictrans-v2-all",
            "name": "indictrans-gpu-t4",
            "endpoint": "http://triton:8000/v2/models/indictrans-gpu-t4/infer",
            "api_key": None,
            "adapter_config": None,
        }

    cases = [
        ("http://localhost:9090",   "http://localhost:9090/api/v1/services/indictrans-v2-all"),
        ("http://localhost:9090/",  "http://localhost:9090/api/v1/services/indictrans-v2-all"),
        ("https://mms.internal",    "https://mms.internal/api/v1/services/indictrans-v2-all"),
        ("https://mms.internal/",   "https://mms.internal/api/v1/services/indictrans-v2-all"),
    ]

    # The resolver reads settings (single config source), not raw env vars —
    # patch the Settings attribute instead of os.environ.
    from config import settings as _settings

    for base_url, expected in cases:
        captured.clear()
        resolver._memory_cache.clear()
        with _patch.object(_settings, "MODEL_MANAGEMENT_SERVICE_URL", base_url):
            with _patch("utils.http_client.HTTPServiceClient.get_json", new=_mock_get_json):
                await resolver.resolve_service("indictrans-v2-all")
        assert captured[0] == expected, f"base={base_url!r}: got {captured[0]!r}, want {expected!r}"

    logger.info("   [PASS] resolver URL constructed correctly for all base URL variants")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def run_all():
    tests = [
        ("validate_request — valid", test_validate_request_valid),
        ("validate_request — error paths", test_validate_request_errors),
        ("preprocess_input — sanitise", test_preprocess_input),
        ("payload_key", test_payload_key),
        ("postprocess_output — pairing + unwrap", test_postprocess_output),
        ("process — full pipeline (mocked)", test_process_full),
        ("process — missing endpoint", test_process_missing_endpoint),
        ("resolver URL — /api/v1/services/{id} path", test_resolver_url_construction),
    ]

    logger.info("=" * 70)
    logger.info("NMTTaskService Unit Tests")
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
