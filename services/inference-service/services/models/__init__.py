from services import (
    NERTaskService,
    TransliterationTaskService,
    LanguageDetectionTaskService,
)

from services.models.text_default_model import TextDefaultModel
__all__ = [
    "TextDefaultModel",
    "NERTaskService",
    "TransliterationTaskService",
    "LanguageDetectionTaskService",
]
