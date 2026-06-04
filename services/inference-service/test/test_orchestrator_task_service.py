"""Unit tests: Orchestrator._get_task_service class_instance lookup (AI4IDS-1767)."""

import sys
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, ".")

from orchestrator.orchestrator import Orchestrator, TaskServiceExecutionError


def _make_orchestrator() -> Orchestrator:
    """Return an Orchestrator with InferenceServerResolver mocked out."""
    with patch("orchestrator.orchestrator.InferenceServerResolver"):
        return Orchestrator()


def _make_service_info(class_instance: str | None) -> dict:
    return {
        "name": "test-ocr-model-1-service-1",
        "endpoint": "http://triton:8000",
        "api_key": None,
        "adapter_config": {},
        "class_instance": class_instance,
    }


# ── Happy path ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_known_class_instance_instantiates_correct_service():
    orch = _make_orchestrator()
    mock_class = MagicMock(return_value=MagicMock())
    orch.task_service_registry = {"ImageDefaultModel": mock_class}

    service_info = _make_service_info("ImageDefaultModel")
    result = await orch._get_task_service("OCR", service_info)

    mock_class.assert_called_once_with(service_info=service_info)
    assert result is mock_class.return_value


# ── Missing class_instance ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_missing_class_instance_raises():
    orch = _make_orchestrator()
    service_info = _make_service_info(None)

    with pytest.raises(TaskServiceExecutionError, match="No class_instance set"):
        await orch._get_task_service("OCR", service_info)


@pytest.mark.asyncio
async def test_absent_class_instance_key_raises():
    orch = _make_orchestrator()
    service_info = {
        "name": "test-ocr-model-1-service-1",
        "endpoint": "http://triton:8000",
        "api_key": None,
        "adapter_config": {},
        # class_instance key not present at all
    }

    with pytest.raises(TaskServiceExecutionError, match="No class_instance set"):
        await orch._get_task_service("OCR", service_info)


# ── Unknown class_instance ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unregistered_class_instance_raises():
    orch = _make_orchestrator()
    orch.task_service_registry = {"ImageDefaultModel": MagicMock()}
    service_info = _make_service_info("NonExistentTaskService")

    with pytest.raises(TaskServiceExecutionError, match="Unknown class_instance"):
        await orch._get_task_service("OCR", service_info)


# ── Registry coverage ─────────────────────────────────────────────────────────

def test_all_registry_classes_are_importable():
    """Every entry in TASK_SERVICE_REGISTRY must be a callable class."""
    from orchestrator.task_service_registry import TASK_SERVICE_REGISTRY

    for name, cls in TASK_SERVICE_REGISTRY.items():
        assert callable(cls), f"{name} is not callable"
