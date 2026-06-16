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
