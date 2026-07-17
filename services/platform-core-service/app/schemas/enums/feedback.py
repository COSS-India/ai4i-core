"""
Enums for the Explicit Feedback API (v0.1 — thumbs up/down only).
"""

from enum import Enum

from app.schemas.enums.model_management import TaskTypeEnum, resolve_task_type


class FeedbackTypeEnum(str, Enum):
    """Feedback collection mechanism. v0.1 supports THUMBS only — star-based
    and list (checkbox/radio) types are deferred to a later version."""

    THUMBS = "THUMBS"


class RatingEnum(str, Enum):
    """Thumbs up (POSITIVE) or thumbs down (NEGATIVE) — the core signal."""

    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"


class FeedbackSourceEnum(str, Enum):
    """Where a feedback submission originated. Not part of the public
    FeedbackSubmission contract — the server derives this itself (v0.1:
    PORTAL_TRY_IT_NOW for anonymous/guest submissions, API otherwise)."""

    API = "API"
    UI_COMPONENT = "UI_COMPONENT"
    PORTAL_TRY_IT_NOW = "PORTAL_TRY_IT_NOW"


class ModelTaskTypeEnum(str, Enum):
    """The 10 model task types the Feedback API accepts. LLM and Pipeline
    are excluded from v0.1 — deferred to a later version. Values match the
    Feedback API's own OpenAPI vocabulary (SCREAMING_SNAKE_CASE), which
    differs in spelling/casing from the platform's internal TaskTypeEnum
    (e.g. TEXT_LANG_DETECTION here vs. "language-detection" internally)."""

    NMT = "NMT"
    ASR = "ASR"
    TTS = "TTS"
    OCR = "OCR"
    NER = "NER"
    TRANSLITERATION = "TRANSLITERATION"
    TEXT_LANG_DETECTION = "TEXT_LANG_DETECTION"
    AUDIO_LANG_DETECTION = "AUDIO_LANG_DETECTION"
    SPEAKER_DIARIZATION = "SPEAKER_DIARIZATION"
    LANGUAGE_DIARIZATION = "LANGUAGE_DIARIZATION"


# Maps the Feedback API's public ModelTaskTypeEnum vocabulary to the
# platform's internal TaskTypeEnum value (mm_services.task_type / inference
# task_type vocabulary), so ef_feedback.model_task_type stays in the same
# vocabulary as the rest of the platform's task-type data (and joinable with
# whatever vocabulary the ef_feedback_reason catalog ends up using).
_MODEL_TASK_TYPE_TO_INTERNAL: dict[ModelTaskTypeEnum, str] = {
    ModelTaskTypeEnum.NMT: TaskTypeEnum.nmt.value,
    ModelTaskTypeEnum.ASR: TaskTypeEnum.asr.value,
    ModelTaskTypeEnum.TTS: TaskTypeEnum.tts.value,
    ModelTaskTypeEnum.OCR: TaskTypeEnum.ocr.value,
    ModelTaskTypeEnum.NER: TaskTypeEnum.ner.value,
    ModelTaskTypeEnum.TRANSLITERATION: TaskTypeEnum.transliteration.value,
    ModelTaskTypeEnum.TEXT_LANG_DETECTION: TaskTypeEnum.language_detection.value,
    ModelTaskTypeEnum.AUDIO_LANG_DETECTION: TaskTypeEnum.audio_lang_detection.value,
    ModelTaskTypeEnum.SPEAKER_DIARIZATION: TaskTypeEnum.speaker_diarization.value,
    ModelTaskTypeEnum.LANGUAGE_DIARIZATION: TaskTypeEnum.language_diarization.value,
}


def resolve_feedback_task_type(value: ModelTaskTypeEnum) -> str:
    """Canonicalize a Feedback API modelTaskType to the platform's internal
    TaskTypeEnum value.

    Pydantic already rejects anything outside ModelTaskTypeEnum (so "llm"
    and unknown values 422 before this is ever called) — resolve_task_type
    here is a defensive double-check reusing the platform's single source
    of truth for task-type canonicalization, per the LLD's instruction to
    "reuse TaskTypeEnum via resolve_task_type".
    """
    return resolve_task_type(_MODEL_TASK_TYPE_TO_INTERNAL[value])
