"""Unit tests: TaskServiceRegistry class_instance lookup (AI4IDS-1767)."""

import sys
import pytest
from unittest.mock import MagicMock

sys.path.insert(0, ".")

from orchestrator.task_service_registry import TASK_SERVICE_REGISTRY, TaskServiceRegistry


def _make_service_info(class_instance: str | None) -> dict:
    return {
        "name": "test-ocr-model-1-service-1",
        "endpoint": "http://triton:8000",
        "api_key": None,
        "adapter_config": {},
        "class_instance": class_instance,
    }


# ── Happy path ────────────────────────────────────────────────────────────────

def test_known_class_instance_instantiates_correct_service():
    mock_class = MagicMock(return_value=MagicMock())
    registry = TaskServiceRegistry({"ImageDefaultModel": mock_class})

    service_info = _make_service_info("ImageDefaultModel")
    result = registry.create(service_info)

    mock_class.assert_called_once_with(service_info=service_info)
    assert result is mock_class.return_value


def test_is_registered_reflects_membership():
    registry = TaskServiceRegistry({"ImageDefaultModel": MagicMock()})
    assert registry.is_registered("ImageDefaultModel") is True
    assert registry.is_registered("NonExistentTaskService") is False
    assert registry.is_registered(None) is False


# ── Missing class_instance ────────────────────────────────────────────────────

def test_missing_class_instance_raises():
    registry = TaskServiceRegistry()
    service_info = _make_service_info(None)

    with pytest.raises(RuntimeError, match="No class_instance set"):
        registry.create(service_info)


def test_absent_class_instance_key_raises():
    registry = TaskServiceRegistry()
    service_info = {
        "name": "test-ocr-model-1-service-1",
        "endpoint": "http://triton:8000",
        "api_key": None,
        "adapter_config": {},
        # class_instance key not present at all
    }

    with pytest.raises(RuntimeError, match="No class_instance set"):
        registry.create(service_info)


# ── Unknown class_instance ────────────────────────────────────────────────────

def test_unregistered_class_instance_raises():
    registry = TaskServiceRegistry({"ImageDefaultModel": MagicMock()})
    service_info = _make_service_info("NonExistentTaskService")

    with pytest.raises(RuntimeError, match="Unknown class_instance"):
        registry.create(service_info)


# ── Registry coverage ─────────────────────────────────────────────────────────

def test_all_registry_classes_are_importable():
    """Every entry in TASK_SERVICE_REGISTRY must be a callable class."""
    for name, cls in TASK_SERVICE_REGISTRY.items():
        assert callable(cls), f"{name} is not callable"


def test_legacy_seeded_class_instances_resolve():
    """class_instance values seeded by migration c3d5e7f9a2b4 must resolve."""
    for seeded in ("TextDefaultModel", "AudioDefaultModel", "ImageDefaultModel"):
        assert seeded in TASK_SERVICE_REGISTRY, f"seeded value '{seeded}' missing"
