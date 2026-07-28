"""Unit tests for the shared task-type name normalizer.

Guards the invariant that every spelling of a task type across the codebase
(hyphen / underscore / mixed case / the audio-lang-detection alias) folds to the
one canonical yaml name, so a single enabled set can gate all of them.
"""

from app.core.task_type_norm import normalize_task_type


def test_case_and_underscore_folding():
    assert normalize_task_type("LLM") == "llm"
    assert normalize_task_type("Language_Detection") == "language-detection"
    assert normalize_task_type("speaker_diarization") == "speaker-diarization"


def test_whitespace_and_empty():
    assert normalize_task_type("  nmt  ") == "nmt"
    assert normalize_task_type("") == ""
    assert normalize_task_type(None) == ""


def test_audio_lang_alias_collapses_to_canonical():
    """The wire/metric/yaml name is `audio-lang-detection`; the UI ServiceId,
    metering key, and alert task use `audio-language-detection`. Every spelling
    must resolve to the canonical short form."""
    canonical = "audio-lang-detection"
    for spelling in (
        "audio-lang-detection",
        "audio_lang_detection",
        "audio-language-detection",
        "audio_language_detection",
        "AUDIO_LANGUAGE_DETECTION",
        "Audio-Language-Detection",
    ):
        assert normalize_task_type(spelling) == canonical, spelling


def test_non_alias_names_pass_through_unchanged():
    for name in ("nmt", "asr", "tts", "ocr", "ner", "llm", "pipeline"):
        assert normalize_task_type(name) == name
