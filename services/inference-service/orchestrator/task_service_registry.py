"""
Task Service Registry.

Maps task_type to its TaskService class.

Which concrete model serves a request is NOT decided here — the Orchestrator
resolves the serviceId against MMS (InferenceServerResolver), which supplies
the endpoint, model name, and adapter_config. The registry only picks the
TaskService class that knows how to drive that task type's pipeline.

To add a new task type:
  1. Import the service class below.
  2. Add a "TASK_TYPE": ServiceClass entry to TASK_SERVICE_REGISTRY.

New models for an existing task type need no change here — they are
onboarded in MMS (mm_services) with their adapter_config.
"""

from services.base.audio_base import AudioDefaultModel
from services.base.audio_tasks import (
    ASRTaskService,
    LanguageDiarizationTaskService,
    SpeakerDiarizationTaskService,
)
from services.base.image_base import ImageDefaultModel
from services.base.text_base import (
    LanguageDetectionTaskService,
    NERTaskService,
    TextDefaultModel,
    TransliterationTaskService,
)
from services.tts_service import TTSTaskService


TASK_SERVICE_REGISTRY = {
    "NMT":                      TextDefaultModel,
    "ASR":                      ASRTaskService,
    "TTS":                      TTSTaskService,
    "NER":                      NERTaskService,
    "OCR":                      ImageDefaultModel,
    "LANGUAGE_DETECTION":       LanguageDetectionTaskService,
    "TRANSLITERATION":          TransliterationTaskService,
    "SPEAKER_DIARIZATION":      SpeakerDiarizationTaskService,
    "LANGUAGE_DIARIZATION":     LanguageDiarizationTaskService,
    "AUDIO_LANGUAGE_DETECTION": AudioDefaultModel,
}
