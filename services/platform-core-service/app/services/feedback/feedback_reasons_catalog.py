"""
Static feedback reason catalog backing GET /feedback/reasons (v0.1 stub).

ef_feedback_reason (the real, configurable catalog table) doesn't exist yet —
see the note in feedback_service.py and the ef_feedback migration docstring.
Until that table is built and seeded, the catalog is this hardcoded dict.
Every task type ends with an "other" entry per the spec's example. Swapping
this for a DB-backed catalog later is a single-file change: replace
_CATALOG with a repository lookup in feedback_service.get_reasons.
"""

from app.schemas.enums.feedback import ModelTaskTypeEnum
from app.schemas.feedback.feedback import Reason

_OTHER = Reason(code="other", label="Other")

CATALOG: dict[ModelTaskTypeEnum, list[Reason]] = {
    ModelTaskTypeEnum.NMT: [
        Reason(code="incorrect_meaning", label="Incorrect meaning"),
        Reason(code="missing_translation", label="Missing translation"),
        _OTHER,
    ],
    ModelTaskTypeEnum.ASR: [
        Reason(code="missing_words", label="Missing words"),
        Reason(code="wrong_language_detected", label="Wrong language detected"),
        _OTHER,
    ],
    ModelTaskTypeEnum.TTS: [
        Reason(code="unnatural_voice", label="Unnatural voice"),
        Reason(code="wrong_pronunciation", label="Wrong pronunciation"),
        Reason(code="audio_quality_issue", label="Audio quality issue"),
        _OTHER,
    ],
    ModelTaskTypeEnum.OCR: [
        Reason(code="incorrect_text_extraction", label="Incorrect text extraction"),
        Reason(code="missing_text", label="Missing text"),
        Reason(code="formatting_issue", label="Formatting issue"),
        _OTHER,
    ],
    ModelTaskTypeEnum.NER: [
        Reason(code="incorrect_entity", label="Incorrect entity"),
        Reason(code="missing_entity", label="Missing entity"),
        Reason(code="wrong_entity_type", label="Wrong entity type"),
        _OTHER,
    ],
    ModelTaskTypeEnum.TRANSLITERATION: [
        Reason(code="incorrect_transliteration", label="Incorrect transliteration"),
        Reason(code="missing_transliteration", label="Missing transliteration"),
        _OTHER,
    ],
    ModelTaskTypeEnum.TEXT_LANG_DETECTION: [
        Reason(code="wrong_language_detected", label="Wrong language detected"),
        Reason(code="low_confidence", label="Low confidence"),
        _OTHER,
    ],
    ModelTaskTypeEnum.AUDIO_LANG_DETECTION: [
        Reason(code="wrong_language_detected", label="Wrong language detected"),
        Reason(code="low_confidence", label="Low confidence"),
        _OTHER,
    ],
    ModelTaskTypeEnum.SPEAKER_DIARIZATION: [
        Reason(code="incorrect_speaker_count", label="Incorrect speaker count"),
        Reason(code="incorrect_speaker_boundaries", label="Incorrect speaker boundaries"),
        _OTHER,
    ],
    ModelTaskTypeEnum.LANGUAGE_DIARIZATION: [
        Reason(code="incorrect_language_segments", label="Incorrect language segments"),
        Reason(code="incorrect_boundaries", label="Incorrect boundaries"),
        _OTHER,
    ],
}