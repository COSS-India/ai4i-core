"""Tracing header contract between ObservabilityMiddleware and service trace layers.

ObservabilityMiddleware injects ``X-Tracing-*`` headers into the request scope
before handlers run. Downstream tracing code reads them via ``read_tracing_headers``.
"""

import math
from typing import Any, Dict, Mapping, Optional, Tuple

from starlette.requests import Request

# Prefix for all tracing headers injected by ObservabilityMiddleware.
TRACING_HEADER_PREFIX = "X-Tracing-"

# Canonical header names (HTTP header names are case-insensitive).
HEADER_INPUT_TYPE = f"{TRACING_HEADER_PREFIX}Input-Type"
HEADER_INPUT_TOKENS = f"{TRACING_HEADER_PREFIX}Input-Tokens"
HEADER_SERVICE_TYPE = f"{TRACING_HEADER_PREFIX}Service-Type"
HEADER_SERVICE_ID = f"{TRACING_HEADER_PREFIX}Service-Id"
HEADER_SOURCE_LANG = f"{TRACING_HEADER_PREFIX}Source-Lang"
HEADER_TARGET_LANG = f"{TRACING_HEADER_PREFIX}Target-Lang"
HEADER_CHARACTERS = f"{TRACING_HEADER_PREFIX}Characters"
HEADER_AUDIO_SECONDS = f"{TRACING_HEADER_PREFIX}Audio-Seconds"
HEADER_NER_TOKENS = f"{TRACING_HEADER_PREFIX}Ner-Tokens"
HEADER_OCR_CHARACTERS = f"{TRACING_HEADER_PREFIX}Ocr-Characters"
HEADER_OCR_IMAGE_KB = f"{TRACING_HEADER_PREFIX}Ocr-Image-Kb"

HEADER_TASK_TYPE = f"{TRACING_HEADER_PREFIX}Task-Type"

_TRACING_HEADER_MAP = {
    "task_type": HEADER_TASK_TYPE,
    "input_type": HEADER_INPUT_TYPE,
    "input_tokens": HEADER_INPUT_TOKENS,
    "service_type": HEADER_SERVICE_TYPE,
    "service_id": HEADER_SERVICE_ID,
    "source_lang": HEADER_SOURCE_LANG,
    "target_lang": HEADER_TARGET_LANG,
    "characters": HEADER_CHARACTERS,
    "audio_seconds": HEADER_AUDIO_SECONDS,
    "ner_tokens": HEADER_NER_TOKENS,
    "ocr_characters": HEADER_OCR_CHARACTERS,
    "ocr_image_kb": HEADER_OCR_IMAGE_KB,
}


def is_empty_tracing_value(value: Any) -> bool:
    """Return True when a tracing/metric value should be omitted (unset or zero)."""
    if value is None or value == "":
        return True
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value == 0
    if isinstance(value, float):
        return math.isclose(value, 0.0, abs_tol=1e-12)
    return False


def build_tracing_header_pairs(analysis: Dict[str, Any]) -> Tuple[Tuple[str, str], ...]:
    """Return (header_name, value) pairs for a payload analysis snapshot."""
    pairs = []
    for field, header_name in _TRACING_HEADER_MAP.items():
        value = analysis.get(field)
        if is_empty_tracing_value(value):
            continue
        pairs.append((header_name, str(value)))
    return tuple(pairs)


def inject_tracing_headers(scope: dict, analysis: Dict[str, Any]) -> None:
    """Append tracing headers to the ASGI scope before the handler runs."""
    headers = list(scope.get("headers") or [])
    for header_name, value in build_tracing_header_pairs(analysis):
        headers.append((header_name.lower().encode("latin-1"), value.encode("latin-1")))
    scope["headers"] = headers


def read_tracing_headers(headers: Mapping[str, str]) -> Dict[str, Any]:
    """Parse ``X-Tracing-*`` headers into a normalized attribute dict."""
    result: Dict[str, Any] = {}

    def _get(name: str) -> Optional[str]:
        return headers.get(name) or headers.get(name.lower())

    raw_input_type = _get(HEADER_INPUT_TYPE)
    if raw_input_type:
        result["input_type"] = raw_input_type

    raw_task_type = _get(HEADER_TASK_TYPE)
    if raw_task_type:
        result["task_type"] = raw_task_type

    raw_service_type = _get(HEADER_SERVICE_TYPE)
    if raw_service_type:
        result["service_type"] = raw_service_type

    raw_service_id = _get(HEADER_SERVICE_ID)
    if raw_service_id:
        result["service_id"] = raw_service_id

    raw_source_lang = _get(HEADER_SOURCE_LANG)
    if raw_source_lang:
        result["source_lang"] = raw_source_lang

    raw_target_lang = _get(HEADER_TARGET_LANG)
    if raw_target_lang:
        result["target_lang"] = raw_target_lang

    for int_field, header in (
        ("characters", HEADER_CHARACTERS),
        ("ner_tokens", HEADER_NER_TOKENS),
        ("ocr_characters", HEADER_OCR_CHARACTERS),
    ):
        raw = _get(header)
        if raw is not None and raw != "":
            try:
                result[int_field] = int(raw)
            except ValueError:
                pass

    raw_input_tokens = _get(HEADER_INPUT_TOKENS)
    if raw_input_tokens is not None and raw_input_tokens != "":
        try:
            result["input_tokens"] = float(raw_input_tokens)
        except ValueError:
            pass

    for float_field, header in (("audio_seconds", HEADER_AUDIO_SECONDS), ("ocr_image_kb", HEADER_OCR_IMAGE_KB)):
        raw = _get(header)
        if raw is not None and raw != "":
            try:
                result[float_field] = float(raw)
            except ValueError:
                pass

    return result


def read_tracing_headers_from_request(request: Optional[Request]) -> Dict[str, Any]:
    """Read tracing attributes from a FastAPI/Starlette request, if present."""
    if request is None:
        return {}
    return read_tracing_headers(request.headers)
