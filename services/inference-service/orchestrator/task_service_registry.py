"""
Task Service Registry.

Maps class_instance names (stored in mm_models.class_instance) to their
TaskService implementation.

To support a genuinely new inference behaviour, add the service class file
and one entry here.  Adding a new model or service via the platform requires
no code change — the class_instance value stored on the model row is used
for lookup at runtime.
"""

from services.asr_service import ASRTaskService
from services.language_detection_service import LanguageDetectionTaskService
from services.language_diarization_service import LanguageDiarizationTaskService
from services.ner_service import NERTaskService
from services.pii_service import PIITaskService
from services.speaker_diarization_service import SpeakerDiarizationTaskService
from services.transliteration_service import TransliterationTaskService
from services.tts_service import TTSTaskService
from services.models.audio_default_model import AudioDefaultModel
from services.models.image_default_model import ImageDefaultModel
from services.models.text_default_model import TextDefaultModel


TASK_SERVICE_REGISTRY = {
    "ASRTaskService":                ASRTaskService,
    "AudioDefaultModel":             AudioDefaultModel,
    "ImageDefaultModel":             ImageDefaultModel,
    "LanguageDetectionTaskService":  LanguageDetectionTaskService,
    "LanguageDiarizationTaskService": LanguageDiarizationTaskService,
    "NERTaskService":                NERTaskService,
    "PIITaskService":                PIITaskService,
    "SpeakerDiarizationTaskService": SpeakerDiarizationTaskService,
    "TextDefaultModel":              TextDefaultModel,
    "TransliterationTaskService":    TransliterationTaskService,
    "TTSTaskService":                TTSTaskService,
}
