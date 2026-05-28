"""
Task type definitions and registry mapping task types to their service implementations.
"""

from enum import Enum
from typing import Any, Dict, Type


class TaskType(str, Enum):
    """Enumeration of supported inference task types."""

    NMT = "NMT"  # Neural Machine Translation
    ASR = "ASR"  # Automatic Speech Recognition
    OCR = "OCR"  # Optical Character Recognition
    NER = "NER"  # Named Entity Recognition
    LANGUAGE_DETECTION = "LANGUAGE_DETECTION"  # Language Detection
    TTS = "TTS"  # Text-to-Speech
    TRANSLITERATION = "TRANSLITERATION"  # Transliteration
    LANGUAGE_DIARIZATION = "LANGUAGE_DIARIZATION"  # Language Diarization
    SPEAKER_DIARIZATION = "SPEAKER_DIARIZATION"  # Speaker Diarization
    AUDIO_LANGUAGE_DETECTION = "AUDIO_LANGUAGE_DETECTION"  # Audio Language Detection
    PII = "PII"  # PII Detection and Redaction


class TaskRegistry:
    """
    Central registry mapping task types to their implementations.
    Stores request models, config models, response models, and service classes.
    """

    def __init__(self):
        self._registry: Dict[str, Dict[str, Any]] = {}

    def register(
        self,
        task_type: TaskType,
        request_model: Type,
        config_model: Type,
        response_model: Type,
        service_class: Type,
        input_key: str = "input",
    ) -> None:
        """
        Register a task type with its associated models and service.

        Args:
            task_type: TaskType enum value
            request_model: Pydantic model for task-specific request
            config_model: Pydantic model for task-specific config
            response_model: Pydantic model for task-specific response
            service_class: TaskService implementation class
            input_key: Which input array key to use ("input", "audio", or "image")
        """
        self._registry[task_type.value] = {
            "request_model": request_model,
            "config_model": config_model,
            "response_model": response_model,
            "service_class": service_class,
            "input_key": input_key,
            "task_type": task_type,
        }

    def get(self, task_type: str) -> Dict[str, Any]:
        """Retrieve registry entry for a task type."""
        if task_type not in self._registry:
            raise ValueError(
                f"Unknown task type: {task_type}. "
                f"Registered types: {list(self._registry.keys())}"
            )
        return self._registry[task_type]

    def get_request_model(self, task_type: str) -> Type:
        """Get the Pydantic request model for a task type."""
        return self.get(task_type)["request_model"]

    def get_config_model(self, task_type: str) -> Type:
        """Get the Pydantic config model for a task type."""
        return self.get(task_type)["config_model"]

    def get_response_model(self, task_type: str) -> Type:
        """Get the Pydantic response model for a task type."""
        return self.get(task_type)["response_model"]

    def get_service_class(self, task_type: str) -> Type:
        """Get the TaskService implementation class for a task type."""
        return self.get(task_type)["service_class"]

    def get_input_key(self, task_type: str) -> str:
        """Get which input array key to use for a task type."""
        return self.get(task_type)["input_key"]

    def is_registered(self, task_type: str) -> bool:
        """Check if a task type is registered."""
        return task_type in self._registry

    def list_registered_types(self) -> list:
        """Return list of all registered task types."""
        return list(self._registry.keys())


# Global registry instance
task_registry = TaskRegistry()
