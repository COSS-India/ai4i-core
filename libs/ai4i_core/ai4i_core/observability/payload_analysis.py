"""Single-pass inference payload analysis for observability and tracing headers.

Runs in ObservabilityMiddleware before handlers execute. Produces one analysis
snapshot that is (a) injected as ``X-Tracing-*`` headers for the Trace module
and (b) projected into Prometheus metrics. Trace layers must consume headers
rather than re-parsing the payload for the same fields.
"""

import base64
import io
import logging
import wave
from typing import Any, Dict, List, Optional

from .inference_tasks import INFERENCE_TASKS, service_type_from_task_type

logger = logging.getLogger(__name__)


def analyze_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze an inference JSON payload once."""
    if not isinstance(payload, dict):
        return {}

    input_type = _detect_input_type(payload)
    input_items = _input_items(payload, input_type)
    task_type = _resolve_task_type(payload)

    if input_type == "text":
        input_tokens = _count_text_billing_units(input_items)
    elif input_type == "audio":
        input_tokens = _count_audio_billing_units(input_items)
    elif input_type == "image":
        input_tokens = _count_image_billing_units(input_items)
    else:
        input_tokens = 0

    source_lang, target_lang = _extract_languages(payload)
    service_id = _extract_service_id(payload)

    return {
        "task_type": task_type,
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
        "service_type": _service_type_from_payload(payload, task_type),
    }


def build_observability_metrics(
    analysis: Dict[str, Any],
    *,
    path_service_type: str = "unknown",
) -> Dict[str, Any]:
    """Build the Prometheus snapshot stored on request.state after analysis."""
    service_type = analysis.get("service_type") or path_service_type
    return {
        "service_type": service_type,
        "service_id": analysis.get("service_id") or "",
        "source_lang": analysis.get("source_lang") or "",
        "target_lang": analysis.get("target_lang") or "",
        "characters": analysis.get("characters") or 0,
        "ner_tokens": analysis.get("ner_tokens") or 0,
        "audio_seconds": analysis.get("audio_seconds") or 0.0,
        "ocr_characters": analysis.get("ocr_characters") or 0,
        "ocr_image_kb": analysis.get("ocr_image_kb") or 0.0,
    }


def _resolve_task_type(payload: Dict[str, Any]) -> str:
    task_type = str(payload.get("task_type") or "").upper()
    if task_type in INFERENCE_TASKS:
        return task_type
    if payload.get("messages") is not None:
        return "LLM"
    return ""


def _detect_input_type(payload: Dict[str, Any]) -> str:
    if not payload or not isinstance(payload, dict):
        return "unknown"
    if payload.get("input"):
        return "text"
    if payload.get("audio"):
        return "audio"
    if payload.get("image"):
        return "image"
    if payload.get("messages"):
        return "text"
    return "unknown"


def _field(item: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        value = item.get(name) if isinstance(item, dict) else getattr(item, name, None)
        if value:
            return value
    return default


def _count_text_billing_units(input_items: List[Any]) -> int:
    """PPU billing unit for text modalities: character count."""
    total = 0
    for item in input_items:
        source = _field(item, "source", default="")
        if isinstance(source, str):
            total += len(source)
    return total


def _count_audio_billing_units(input_items: List[Any]) -> float:
    """PPU billing unit for audio modalities: fractional minutes."""
    total = 0.0
    for item in input_items:
        num_samples = _field(item, "num_samples", "numSamples", default=0)
        sample_rate = _field(item, "sample_rate", "sampleRate", default=0)
        audio_content = _field(item, "audio_content", "audioContent", default="")

        duration_seconds = 0.0
        if num_samples > 0 and sample_rate > 0:
            duration_seconds = num_samples / float(sample_rate)
        elif audio_content:
            duration_seconds = _audio_length_from_base64(str(audio_content))

        if duration_seconds > 0:
            total += duration_seconds / 60.0
    return total


def _count_image_billing_units(input_items: List[Any]) -> int:
    """PPU billing unit for image modalities: image count."""
    return len(input_items)


def _nested_payload_list(payload: Dict[str, Any], key: str, input_data_key: Optional[str] = None) -> List[Any]:
    items = payload.get(key)
    if items is None and input_data_key:
        inp = payload.get("inputData")
        if isinstance(inp, dict):
            items = inp.get(input_data_key)
    return items if isinstance(items, list) else []


def _input_items(payload: Dict[str, Any], input_type: str) -> List[Any]:
    if input_type == "text" and payload.get("messages"):
        return payload.get("messages") or []
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


def _service_type_from_payload(payload: Dict[str, Any], task_type: str) -> str:
    if task_type:
        mapped = service_type_from_task_type(task_type)
        if mapped != "unknown":
            return mapped
    if payload.get("messages") is not None:
        return INFERENCE_TASKS["LLM"].service_type
    return "unknown"


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
    model = str(payload.get("model") or "").strip()
    if model:
        return model
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
    """Prometheus NER metric: word count (observability-only, not PPU billing)."""
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
