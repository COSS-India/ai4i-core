"""Single-pass inference payload analysis for observability metrics.

Kept separate from span attribute helpers so tracing stays decoupled from
Prometheus / observability middleware.
"""

import base64
import io
import logging
import wave
from contextvars import ContextVar
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_payload_analysis: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "payload_analysis", default=None
)

_TASK_TYPE_TO_SERVICE = {
    "NMT": "translation",
    "TTS": "tts",
    "ASR": "asr",
    "OCR": "ocr",
    "NER": "ner",
    "TRANSLITERATION": "transliteration",
    "LANGUAGE_DETECTION": "language_detection",
    "AUDIO_LANGUAGE_DETECTION": "audio_lang_detection",
    "SPEAKER_DIARIZATION": "speaker_diarization",
    "LANGUAGE_DIARIZATION": "language_diarization",
    "LLM": "llm",
}


def analyze_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze the inference payload once and cache for the current request."""
    if not isinstance(payload, dict):
        return {}
    cached = _payload_analysis.get()
    if cached is not None and cached.get("_payload_id") == id(payload):
        return cached

    input_type = _detect_input_type(payload)
    input_items = _input_items(payload, input_type)

    if input_type == "text":
        input_tokens = _count_text_tokens(input_items)
    elif input_type == "audio":
        input_tokens = _count_audio_tokens(input_items)
    elif input_type == "image":
        input_tokens = _count_image_tokens(input_items)
    else:
        input_tokens = 0

    source_lang, target_lang = _extract_languages(payload)
    service_id = _extract_service_id(payload)

    analysis: Dict[str, Any] = {
        "_payload_id": id(payload),
        "input_type": input_type,
        "input_tokens": input_tokens,
        "characters": _sum_input_characters(payload),
        "ner_tokens": _sum_ner_tokens(payload),
        "audio_seconds": _sum_audio_seconds(payload),
        "ocr_characters": _sum_ocr_characters(payload),
        "ocr_image_kb": _sum_ocr_image_size_kb(payload),
        "source_lang": source_lang,
        "target_lang": target_lang,
        "service_id": service_id,
        "service_type": _service_type_from_payload(payload),
    }
    _payload_analysis.set(analysis)
    return analysis


def build_observability_metrics(
    payload: Dict[str, Any],
    span_attrs: Dict[str, Any],
    task_name: str,
) -> Dict[str, Any]:
    """Build the snapshot ObservabilityMiddleware reads after a successful request."""
    analysis = analyze_payload(payload) if isinstance(payload, dict) else {}
    service_type = analysis.get("service_type") or _service_type_from_task_name(task_name)
    metrics = {
        "service_type": service_type,
        "service_id": span_attrs.get("service_id") or analysis.get("service_id") or "",
        "source_lang": analysis.get("source_lang") or "",
        "target_lang": analysis.get("target_lang") or "",
        "characters": analysis.get("characters") or 0,
        "ner_tokens": analysis.get("ner_tokens") or 0,
        "audio_seconds": analysis.get("audio_seconds") or 0.0,
        "ocr_characters": analysis.get("ocr_characters") or 0,
        "ocr_image_kb": analysis.get("ocr_image_kb") or 0.0,
    }
    if service_type == "llm":
        metrics.update(_llm_observability_fields(payload, span_attrs))
    return metrics


def _llm_observability_fields(payload: Dict[str, Any], span_attrs: Dict[str, Any]) -> Dict[str, Any]:
    prompt = int(span_attrs.get("input_tokens") or 0)
    completion = int(span_attrs.get("output_tokens") or 0)
    if not (prompt or completion):
        return {}
    model = payload.get("model", "") if isinstance(payload, dict) else ""
    return {
        "llm_prompt_tokens": prompt,
        "llm_completion_tokens": completion,
        "llm_total_tokens": prompt + completion,
        "llm_model": model,
    }


def _detect_input_type(payload: Dict[str, Any]) -> str:
    if not payload or not isinstance(payload, dict):
        return "unknown"
    if payload.get("input"):
        return "text"
    if payload.get("audio"):
        return "audio"
    if payload.get("image"):
        return "image"
    return "unknown"


def _count_text_tokens(input_items: List[Any]) -> int:
    total = 0
    for item in input_items:
        if isinstance(item, dict):
            source = item.get("source", "")
        else:
            source = getattr(item, "source", "")
        if isinstance(source, str):
            total += len(source.split())
    return total


def _count_audio_tokens(input_items: List[Any]) -> int:
    total = 0
    for item in input_items:
        if isinstance(item, dict):
            num_samples = item.get("num_samples", 0)
            audio_content = item.get("audio_content", "")
        else:
            num_samples = getattr(item, "num_samples", 0)
            audio_content = getattr(item, "audio_content", "")
        if num_samples > 0:
            tokens = int((num_samples / 16000.0) * 100)
            total += max(tokens, 1)
        elif audio_content:
            tokens = max(len(str(audio_content)) // 100, 1)
            total += tokens
    return total


def _count_image_tokens(input_items: List[Any]) -> int:
    total = 0
    for item in input_items:
        if isinstance(item, dict):
            image_content = item.get("image_content", "")
        else:
            image_content = getattr(item, "image_content", "")
        if image_content:
            tokens = max(len(str(image_content)) // 1000, 1)
            total += tokens
    return total


def _nested_payload_list(payload: Dict[str, Any], key: str, input_data_key: Optional[str] = None) -> List[Any]:
    items = payload.get(key)
    if items is None and input_data_key:
        inp = payload.get("inputData")
        if isinstance(inp, dict):
            items = inp.get(input_data_key)
    return items if isinstance(items, list) else []


def _input_items(payload: Dict[str, Any], input_type: str) -> List[Any]:
    key_map = {
        "text": ("input", "input"),
        "audio": ("audio", "audio"),
        "image": ("image", None),
    }
    keys = key_map.get(input_type)
    if keys is None:
        return []
    top_key, nested_key = keys
    return _nested_payload_list(payload, top_key, nested_key)


def _service_type_from_payload(payload: Dict[str, Any]) -> str:
    task_type = str(payload.get("task_type") or "").upper()
    if task_type in _TASK_TYPE_TO_SERVICE:
        return _TASK_TYPE_TO_SERVICE[task_type]
    return "unknown"


def _service_type_from_task_name(task_name: str) -> str:
    normalized = (task_name or "").upper()
    if normalized in _TASK_TYPE_TO_SERVICE:
        return _TASK_TYPE_TO_SERVICE[normalized]
    if normalized.endswith("TASKSERVICE"):
        normalized = normalized.replace("TASKSERVICE", "")
    return _TASK_TYPE_TO_SERVICE.get(normalized, "unknown")


def _extract_languages(payload: Dict[str, Any]) -> tuple:
    cfg = payload.get("config")
    if not isinstance(cfg, dict):
        return "", ""
    lang = cfg.get("language")
    if not isinstance(lang, dict):
        return "", ""
    src = str(lang.get("sourceLanguage") or "").strip()
    tgt = str(lang.get("targetLanguage") or "").strip()
    return src, tgt


def _extract_service_id(payload: Dict[str, Any]) -> str:
    cfg = payload.get("config")
    if isinstance(cfg, dict):
        service_id = str(cfg.get("service_id") or cfg.get("serviceId") or "").strip()
        if service_id:
            return service_id
    return str(payload.get("serviceId") or payload.get("service_id") or "").strip()


def _sum_input_characters(payload: Dict[str, Any]) -> int:
    items = payload.get("input")
    if items is None:
        inp = payload.get("inputData")
        if isinstance(inp, dict):
            items = inp.get("input")
    if not isinstance(items, list):
        return 0
    return sum(
        len(item["source"])
        for item in items
        if isinstance(item, dict) and isinstance(item.get("source"), str)
    )


def _sum_ner_tokens(payload: Dict[str, Any]) -> int:
    items = payload.get("input")
    if not isinstance(items, list):
        return 0
    total = 0
    for item in items:
        if isinstance(item, dict):
            src = item.get("source")
            if isinstance(src, str):
                total += len(src.split())
    return total


def _sum_audio_seconds(payload: Dict[str, Any]) -> float:
    audio_list = payload.get("audio")
    if audio_list is None:
        inp = payload.get("inputData")
        if isinstance(inp, dict):
            audio_list = inp.get("audio")
    if not isinstance(audio_list, list):
        return 0.0
    total = 0.0
    for item in audio_list:
        if not isinstance(item, dict):
            continue
        content = item.get("audioContent") or item.get("audio_content")
        if isinstance(content, str):
            total += _audio_length_from_base64(content)
    return total


def _sum_ocr_characters(payload: Dict[str, Any]) -> int:
    images = payload.get("image")
    if not isinstance(images, list):
        return 0
    total = 0
    for item in images:
        if not isinstance(item, dict):
            continue
        content = item.get("imageContent") or item.get("image_content")
        if isinstance(content, str):
            total += len(content) // 200
    return total


def _sum_ocr_image_size_kb(payload: Dict[str, Any]) -> float:
    images = payload.get("image")
    if not isinstance(images, list):
        return 0.0
    total_kb = 0.0
    for item in images:
        if not isinstance(item, dict):
            continue
        content = item.get("imageContent") or item.get("image_content")
        if isinstance(content, str):
            total_kb += (len(content) * 3 / 4) / 1024
    return total_kb


def _audio_length_from_base64(base64_audio: str) -> float:
    try:
        audio_data = base64.b64decode(base64_audio)
        with wave.open(io.BytesIO(audio_data), "rb") as wav_file:
            return wav_file.getnframes() / float(wav_file.getframerate())
    except Exception:
        try:
            return len(base64.b64decode(base64_audio)) / 32000
        except Exception:
            return 0.0
