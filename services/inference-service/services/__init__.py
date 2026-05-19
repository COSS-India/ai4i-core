"""Services package initialization."""

import os
import sys
import types

# The inference-models directory uses a dash, which Python can't import as a package name.
# Register it as 'inference_models' once here so every service can import from it directly.
_models_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "inference-models"))
if "inference_models" not in sys.modules:
    _pkg = types.ModuleType("inference_models")
    _pkg.__path__ = [_models_dir]
    _pkg.__package__ = "inference_models"
    sys.modules["inference_models"] = _pkg

from services.nmt_service import NMTTaskService
from services.asr_service import ASRTaskService
from services.ocr_service import OCRTaskService
from services.llm_service import LLMTaskService
from services.ner_service import NERTaskService
from services.language_detection_service import LanguageDetectionTaskService
from services.tts_service import TTSTaskService
from services.transliteration_service import TransliterationTaskService
from services.language_diarization_service import LanguageDiarizationTaskService
from services.speaker_diarization_service import SpeakerDiarizationTaskService
from services.audio_language_detection_service import AudioLanguageDetectionTaskService
from services.pii_service import PIITaskService

__all__ = [
    "NMTTaskService",
    "ASRTaskService",
    "OCRTaskService",
    "LLMTaskService",
    "NERTaskService",
    "LanguageDetectionTaskService",
    "TTSTaskService",
    "TransliterationTaskService",
    "LanguageDiarizationTaskService",
    "SpeakerDiarizationTaskService",
    "AudioLanguageDetectionTaskService",
    "PIITaskService",
]
