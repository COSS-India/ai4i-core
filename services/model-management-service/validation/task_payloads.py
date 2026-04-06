"""Task-aware dummy JSON bodies for generic (non-Triton) HTTP probes."""

from __future__ import annotations

import copy
from typing import Any, Dict

from models.type_enum import TaskTypeEnum


def _default_for_task(task_type: str) -> Dict[str, Any]:
    """Minimal JSON body used when ``schema.request`` is empty or unusable."""
    t = (task_type or "").lower().strip()

    if t == TaskTypeEnum.nmt.value:
        return {
            "input": [{"source": "validation"}],
            "config": {
                "language": {"sourceLanguage": "en", "targetLanguage": "hi"},
            },
        }

    if t == TaskTypeEnum.asr.value:
        return {
            "config": {"language": {"sourceLanguage": "en"}},
            "audio": [],
        }

    if t == TaskTypeEnum.tts.value:
        return {
            "input": [{"text": "validation"}],
            "config": {"language": {"targetLanguage": "en"}},
        }

    if t == TaskTypeEnum.llm.value:
        return {
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
        }

    if t == TaskTypeEnum.transliteration.value:
        return {
            "input": [{"source": "validation"}],
            "config": {"language": {"sourceLanguage": "hi", "targetLanguage": "hi"}},
        }

    if t in (TaskTypeEnum.language_detection.value, TaskTypeEnum.audio_lang_detection.value):
        return {"input": [{"text": "validation"}]}

    if t in (TaskTypeEnum.speaker_diarization.value, TaskTypeEnum.language_diarization.value):
        return {"config": {}, "audio": []}

    if t == TaskTypeEnum.ocr.value:
        return {"input": [{"image": ""}]}

    if t == TaskTypeEnum.ner.value:
        return {"input": [{"text": "validation"}]}

    # Unknown task: stable generic object
    return {"_probe": "validation"}


def merge_schema_request_defaults(schema_request: Dict[str, Any], task_type: str) -> Dict[str, Any]:
    """
    If the model defines ``schema.request`` as a non-empty object, deep-merge task defaults on top
    so required keys exist while preserving author-provided shapes.
    """
    base = _default_for_task(task_type)
    if not schema_request:
        return base
    out = copy.deepcopy(schema_request)
    if isinstance(out, dict) and isinstance(base, dict):
        for k, v in base.items():
            out.setdefault(k, v)
    return out if isinstance(out, dict) else base


def build_generic_probe_body(schema_request: Dict[str, Any], task_type: str) -> Dict[str, Any]:
    """Body for POST to a generic REST inference URL."""
    return merge_schema_request_defaults(schema_request or {}, task_type)
