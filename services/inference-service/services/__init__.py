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

from services.base.audio_tasks import (
    ASRTaskService,
    LanguageDiarizationTaskService,
    SpeakerDiarizationTaskService,
)
from services.base.text_base import (
    LanguageDetectionTaskService,
    NERTaskService,
    TextDefaultModel,
    TransliterationTaskService,
)
from services.tts_service import TTSTaskService

__all__ = [
    "TextDefaultModel",
    "ASRTaskService",
    "NERTaskService",
    "LanguageDetectionTaskService",
    "TTSTaskService",
    "TransliterationTaskService",
    "LanguageDiarizationTaskService",
    "SpeakerDiarizationTaskService",
]
