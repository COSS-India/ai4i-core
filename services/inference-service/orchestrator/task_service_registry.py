"""
Task Service Registry.

Maps (task_type, model_name) combinations to their TaskService class.

To add a new model or service:
  1. Import the service class below.
  2. Add an entry to TASK_SERVICE_REGISTRY with the task_type, the list of
     model_name values it handles, and the service_class to instantiate.

Lookup at runtime:
  Given task_type and service_id (from the payload), the Orchestrator finds
  the entry where task_type matches AND service_id is in model_name[].
  It then instantiates service_class(service_info=...) to handle the request.
"""

from services.asr_service import ASRTaskService
from services.models.audio_default_model import AudioDefaultModel
from services.language_detection_service import LanguageDetectionTaskService
from services.language_diarization_service import LanguageDiarizationTaskService
from services.llm_service import LLMTaskService
from services.models.text_default_model import TextDefaultModel
from services.ner_service import NERTaskService
from services.models.image_default_model import ImageDefaultModel
from services.pii_service import PIITaskService
from services.speaker_diarization_service import SpeakerDiarizationTaskService
from services.transliteration_service import TransliterationTaskService
from services.tts_service import TTSTaskService


TASK_SERVICE_REGISTRY = [
    {
        "task_type":     "NMT",
        "model_name":    ["indictrans-gpu-t4"],
        "service_class": TextDefaultModel,
    },
    {
        "task_type":     "ASR",
        "model_name":    ["ai4bharat/triton-multilingual-asr", "asr-gpu"],
        "service_class": ASRTaskService,
    },
    {
        "task_type":     "TTS",
        "model_name":    ["ai4bharat/triton-indo-aryan-tts", "indo-aryan-tts-gpu"],
        "service_class": TTSTaskService,
    },
    {
        "task_type":     "NER",
        "model_name":    ["ner-gpu"],
        "service_class": NERTaskService,
    },
    {
        "task_type":     "OCR",
        "model_name":    ["surya-ocr-gpu", "ai4bharat/triton-ocr"],
        "service_class": ImageDefaultModel,
    },
    {
        "task_type":     "LLM",
        "model_name":    ["ai4bharat/triton-llm", "llm-indic-prod"],
        "service_class": LLMTaskService,
    },
    {
        "task_type":     "PII",
        "model_name":    ["ai4bharat/triton-pii"],
        "service_class": PIITaskService,
    },
    {
        "task_type":     "LANGUAGE_DETECTION",
        "model_name":    ["indiclid-gpu"],
        "service_class": LanguageDetectionTaskService,
    },
    {
        "task_type":     "TRANSLITERATION",
        "model_name":    ["indic-xlit-cpu"],
        "service_class": TransliterationTaskService,
    },
    {
        "task_type":     "SPEAKER_DIARIZATION",
        "model_name":    ["ai4bharat/triton-speaker-diarization", "sd-gpu"],
        "service_class": SpeakerDiarizationTaskService,
    },
    {
        "task_type":     "LANGUAGE_DIARIZATION",
        "model_name":    ["ai4bharat/triton-language-diarization", "lang-diarization-gpu"],
        "service_class": LanguageDiarizationTaskService,
    },
    {
        "task_type":     "AUDIO_LANGUAGE_DETECTION",
        "model_name":    ["ai4bharat/triton-audio-language-detection", "ald-gpu"],
        "service_class": AudioDefaultModel,
    },
]
