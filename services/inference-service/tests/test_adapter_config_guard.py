"""Unit tests: BaseTaskService raises a clear error when adapter_config is missing (AI4IDS-1767)."""

import asyncio
import sys
import pytest
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

sys.path.insert(0, ".")

from services.base.task_service import BaseTaskService


def _make_service(adapter_config) -> BaseTaskService:
    service_info = {
        "name": "test-ocr-model-1-service-1",
        "endpoint": "http://triton:8000/v2/models/surya-ocr/infer",
        "api_key": None,
        "adapter_config": adapter_config,
        "class_instance": "ImageDefaultModel",
    }
    svc = BaseTaskService.__new__(BaseTaskService)
    svc.service_info = service_info
    svc.task_name = "OCR"
    svc.logger = MagicMock()
    svc.payload_key = "image"
    svc.TRITON_CALL_MODE = "batch"
    return svc


@asynccontextmanager
async def _fake_traced_inference(payload, task_name, logger):
    yield {"input_type": "image", "input_tokens": 0, "output_tokens": 0}


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── Missing adapter_config ─────────────────────────────────────────────────────

def test_none_adapter_config_raises_clear_error():
    svc = _make_service(adapter_config=None)
    payload = {"image": [{"imageContent": "abc"}]}

    with patch("trace.request_span.traced_inference", _fake_traced_inference):
        with pytest.raises(RuntimeError) as exc_info:
            _run(svc.run_inference(payload))

    assert "adapter_config" in str(exc_info.value)
    assert "test-ocr-model-1-service-1" in str(exc_info.value)
    assert "adapterConfig" in str(exc_info.value)


def test_missing_adapter_config_key_raises_clear_error():
    svc = _make_service(adapter_config=None)
    svc.service_info.pop("adapter_config")
    payload = {"image": [{"imageContent": "abc"}]}

    with patch("trace.request_span.traced_inference", _fake_traced_inference):
        with pytest.raises(RuntimeError) as exc_info:
            _run(svc.run_inference(payload))

    assert "adapter_config" in str(exc_info.value)


def test_error_message_mentions_model_management_api():
    svc = _make_service(adapter_config=None)
    payload = {"image": [{"imageContent": "abc"}]}

    with patch("trace.request_span.traced_inference", _fake_traced_inference):
        with pytest.raises(RuntimeError) as exc_info:
            _run(svc.run_inference(payload))

    msg = str(exc_info.value)
    assert "Model Management API" in msg or "model registration" in msg
