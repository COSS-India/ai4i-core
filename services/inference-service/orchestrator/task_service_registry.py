"""
Task Service Registry.

Maps class_instance names (stored in mm_models.class_instance) to their
TaskService implementation.

To support a genuinely new inference behaviour, add the service class file
and one entry here.  Adding a new model or service via the platform requires
no code change — the class_instance value stored on the model row is used
for lookup at runtime.
"""

import logging
from typing import Any, Dict, Optional

from services.base.task_service import BaseTaskService

from services.asr_service import ASRTaskService
from services.audio_lang_detection_service import AudioLanguageDetectionTaskService
from services.language_detection_service import LanguageDetectionTaskService
from services.language_diarization_service import LanguageDiarizationTaskService
from services.ner_service import NERTaskService
from services.nmt_service import NMTTaskService
from services.ocr_service import OCRTaskService
from services.pii_service import PIITaskService
from services.speaker_diarization_service import SpeakerDiarizationTaskService
from services.transliteration_service import TransliterationTaskService
from services.tts_service import TTSTaskService


TASK_SERVICE_REGISTRY = {
    "ASRTaskService":                    ASRTaskService,
    "AudioLanguageDetectionTaskService": AudioLanguageDetectionTaskService,
    "LanguageDetectionTaskService":      LanguageDetectionTaskService,
    "LanguageDiarizationTaskService":    LanguageDiarizationTaskService,
    "NERTaskService":                    NERTaskService,
    "NMTTaskService":                    NMTTaskService,
    "OCRTaskService":                    OCRTaskService,
    "PIITaskService":                    PIITaskService,
    "SpeakerDiarizationTaskService":     SpeakerDiarizationTaskService,
    "TransliterationTaskService":        TransliterationTaskService,
    "TTSTaskService":                    TTSTaskService,
    # class_instance values seeded by migration c3d5e7f9a2b4 predate the
    # service-class flatten — keep the DB-seeded names resolving to their
    # successor classes.
    "AudioDefaultModel": AudioLanguageDetectionTaskService,
    "ImageDefaultModel": OCRTaskService,
    "TextDefaultModel":  NMTTaskService,
}


logger = logging.getLogger(__name__)


class TaskServiceRegistry:
    """Resolves a model's class_instance to a TaskService and builds it.

    Wraps the class_instance -> class mapping so the Orchestrator depends on
    a small factory abstraction instead of carrying instantiation logic, and
    so the future PipelineTaskService can build its child stages through the
    same factory. The default registry is the module-level
    TASK_SERVICE_REGISTRY; a custom map can be injected (used by tests).
    """

    def __init__(self, registry: Optional[Dict[str, Any]] = None):
        self._registry = registry if registry is not None else TASK_SERVICE_REGISTRY

    def is_registered(self, class_instance: Optional[str]) -> bool:
        """True if class_instance maps to a registered TaskService."""
        return bool(class_instance) and class_instance in self._registry

    def create(self, service_info: Dict[str, Any]) -> BaseTaskService:
        """Instantiate the TaskService for the resolved service_info.

        class_instance comes from mm_models.class_instance via the resolver,
        so adding a model in the platform needs no code change here.

        Raises:
            RuntimeError: If class_instance is unset or unknown (a platform or
                          config gap, not a client error).
        """
        class_instance = service_info.get("class_instance")
        if not class_instance:
            raise RuntimeError(
                f"No class_instance set on model for serviceId='"
                f"{service_info.get('name', '')}'. "
                f"Set the classInstance field on the model in the platform."
            )

        service_class = self._registry.get(class_instance)
        if not service_class:
            raise RuntimeError(
                f"Unknown class_instance '{class_instance}'. "
                f"Register it in task_service_registry.py."
            )

        logger.debug(
            f"Instantiating {class_instance} for serviceId='{service_info.get('name', '')}'"
        )
        return service_class(service_info=service_info)
