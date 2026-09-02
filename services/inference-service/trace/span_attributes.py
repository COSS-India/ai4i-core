"""
Compute span attributes for inference tracing.

Functions to detect input/output types, count tokens, and calculate payload sizes.
All functions return safe defaults on error to prevent trace enrichment from breaking inference.
"""

import base64
import io
import logging
from typing import Any, Dict, List

import soundfile as sf

logger = logging.getLogger(__name__)


def get_input_type(payload: Dict[str, Any]) -> str:
    """
    Detect input modality type from payload.

    Returns: "text", "audio", "image", or "unknown"
    """
    try:
        if not payload or not isinstance(payload, dict):
            return "unknown"
        if payload.get("input"):
            return "text"
        elif payload.get("audio"):
            return "audio"
        elif payload.get("image"):
            return "image"
        return "unknown"
    except Exception as e:
        logger.warning(f"Error detecting input type: {e}")
        return "unknown"


# orchestrator.ALLOWED_TASK_TYPES values (as sent in payload["task_type"])
# spell multi-word task types with underscores; the catalogue's `name` column
# uses hyphens — get_unit_type normalizes that away below. This table is only
# for genuine WORDING differences that no amount of separator normalization
# fixes (audio_language_detection abbreviates "language" to "lang" in the
# catalogue). It is a dialect fact, not a YAML fact, so it outlives the YAML.
_TASK_TYPE_TO_CATALOGUE_NAME = {
    "audio-language-detection": "audio-lang-detection",
}


async def get_unit_type(task_type: str) -> str:
    """
    Billing unit for a Triton task type, sourced from the inference-type
    catalogue via ai4i_core.ppu (e.g. "asr" -> "audio_minutes",
    "tts" -> "characters", "ocr" -> "images").

    ``task_type`` must be the orchestrator's task type (e.g. payload
    ["task_type"], "NMT"/"ASR"/...) — NOT a class name like
    "NMTTaskService" (self.task_name), which never matches the yaml's
    `name:` keys and would silently resolve to "unknown" for every service.

    Driving unit_type from the catalogue's per-task-type config (rather than
    guessing modality from response field names, as get_output_type used to)
    avoids silently returning "unknown" for services whose adapter_config
    uses a non-standard output field name (e.g. speaker-diarization's
    "diarization_json").

    Matching is separator-insensitive (payload's "language_detection" vs. the
    catalogue's "language-detection") so new task types line up automatically
    without needing a table entry — only a genuine wording difference (see
    _TASK_TYPE_TO_CATALOGUE_NAME) needs one.

    Returns "unknown" if task_type isn't in the map, or on any lookup error.
    A catalogue outage therefore degrades to "unknown", which zeroes the billed
    counts for that span — exactly what an unmapped task type has always done,
    and never a failed inference.
    """
    try:
        from ai4i_core.ppu import get_catalogue
        normalized = task_type.lower().replace("_", "-")
        normalized = _TASK_TYPE_TO_CATALOGUE_NAME.get(normalized, normalized)
        unit_map = await get_catalogue().get_unit_map()
        return unit_map.get(normalized, "unknown")
    except Exception as e:
        logger.warning(f"Error resolving unit type for task_type={task_type}: {e}")
        return "unknown"


def count_input_tokens(input_items: List[Any], unit_type: str) -> float:
    """
    Billed input units, computed per unit_type (see the inference-type catalogue).

    characters: character count (len(text))
    audio_minutes: real duration in minutes, fractional (see _count_audio_tokens)
    images: count of images in the request (see _count_image_tokens)

    Returns: billed unit count, or 0 on error
    """
    try:
        if not input_items:
            return 0

        if unit_type == "characters":
            return _count_text_tokens(input_items)
        elif unit_type == "audio_minutes":
            return _count_audio_tokens(input_items)
        elif unit_type == "images":
            return _count_image_tokens(input_items)

        return 0
    except Exception as e:
        logger.warning(f"Error counting input tokens: {e}")
        return 0


def count_output_tokens(response_data: List[Dict[str, Any]], unit_type: str) -> int:
    """
    Estimate output unit count for observability, computed per unit_type
    (see the inference-type catalogue). Not used for billing — non-LLM PPU billing
    is input-only by design (see payperuse_consumer/handler.py).

    Returns: estimated unit count, or 0 on error
    """
    try:
        if not response_data or not isinstance(response_data, list):
            return 0

        if unit_type == "characters":
            return _count_output_text_tokens(response_data)
        elif unit_type == "audio_minutes":
            return _count_output_audio_tokens(response_data)
        elif unit_type == "images":
            # OCR (the only image-unit service, the catalogue's unit:
            # images) never outputs images — its output is extracted TEXT
            # (the mapper renames Surya's full_text to output[].source), so
            # output is counted the same way NER/NMT output is: characters.
            return _count_output_text_tokens(response_data)

        return 0
    except Exception as e:
        logger.warning(f"Error counting output tokens: {e}")
        return 0


# ============================================================================
# Private helpers
# ============================================================================

def _field(item: Any, *names: str, default: Any = None) -> Any:
    """First truthy value among ``names``, read from a dict key or object attribute.

    Handles the snake_case/camelCase aliasing of the same logical field
    (e.g. ``num_samples``/``numSamples``) that inference payloads use
    interchangeably, so callers don't repeat the dict-vs-attr boilerplate.
    """
    for name in names:
        value = item.get(name) if isinstance(item, dict) else getattr(item, name, None)
        if value:
            return value
    return default


def _count_text_tokens(input_items: List[Any]) -> int:
    """
    Count tokens from text input items by character count.

    All text-modality billing units (nmt, tts, ner, transliteration,
    language-detection — see the inference-type catalogue) are declared as
    "characters", so this must count characters, not words.
    """
    total = 0
    for item in input_items:
        source = _field(item, "source", default="")
        if isinstance(source, str):
            total += len(source)

    return total


def _count_audio_tokens(input_items: List[Any]) -> float:
    """
    Billed units for audio input items — real minutes of audio, fractional.

    asr, speaker-diarization, language-diarization, and audio-lang-detection
    all bill on real audio duration (the catalogue's unit: minutes), not
    a token/byte proxy. ASR's preprocessing already decodes audio and knows
    the exact num_samples/sample_rate; the other three pass audio through to
    Triton as base64 untouched (AudioBase), so duration is read from the
    encoded audio's own header via soundfile — any billing inaccuracy here
    directly under- or over-charges the tenant.

    Billed in fractional minutes (ppu_quota_usage.units_used and
    ppu_tier_quotas.monthly_quota are Numeric columns) — no per-clip minimum.
    """
    total = 0.0
    for item in input_items:
        num_samples = _field(item, "num_samples", "numSamples", default=0)
        sample_rate = _field(item, "sample_rate", "sampleRate", default=0)
        audio_content = _field(item, "audio_content", "audioContent", default="")

        duration_seconds = 0.0
        if num_samples > 0 and sample_rate > 0:
            duration_seconds = num_samples / float(sample_rate)
        elif audio_content:
            duration_seconds = _decode_audio_duration_seconds(audio_content)

        if duration_seconds > 0:
            total += duration_seconds / 60.0

    return total


def _decode_audio_duration_seconds(audio_content: Any) -> float:
    """Read exact duration (seconds) from a base64-encoded audio file's header.

    Uses soundfile.info — a metadata-only read, not a full decode — so this
    stays cheap even for long clips.

    Returns 0.0 if the audio can't be decoded — this runs inside trace
    enrichment, which must never break inference, so it can't raise. But a
    0.0 here means the request bills nothing, so the failure is logged at
    ERROR (not warning) as a billing-loss signal ops should alert on, rather
    than being swallowed silently.
    """
    try:
        raw = base64.b64decode(str(audio_content), validate=False)
        info = sf.info(io.BytesIO(raw))
        return info.frames / float(info.samplerate) if info.samplerate else 0.0
    except Exception as e:
        logger.error(
            "Audio duration decode failed — request will bill 0 units: %s", e
        )
        return 0.0


def _count_image_tokens(input_items: List[Any]) -> int:
    """
    Billed input units for image input items — count of images.

    OCR (the only image-modality service today, see the inference-type catalogue
    unit: images) bills per image, not per byte: a request with N images
    in payload["image"] bills N units regardless of each image's
    resolution or file size.
    """
    return len(input_items)


def _count_output_text_tokens(response_data: List[Dict[str, Any]]) -> int:
    """Count tokens from text output by character count (see _count_text_tokens).

    ``text`` covers OCR here too: OCR's adapter_config maps its output tensor
    to ``text`` (maps_to) at this point in the pipeline — the response_key
    rename to ``output[].source`` happens later, in postprocess_output's
    shape_output_items, which runs after this count is already taken.
    """
    total = 0
    for item in response_data:
        if isinstance(item, dict):
            # Try common output field names
            text = item.get("target") or item.get("output") or item.get("text") or ""
            if isinstance(text, bytes):
                text = text.decode("utf-8", errors="replace")
            total += len(str(text))

    return total


def _count_output_audio_tokens(response_data: List[Dict[str, Any]]) -> int:
    """
    Estimate tokens from audio output by content size.

    Similar to input: bytes / 1000 as proxy.
    """
    total = 0
    for item in response_data:
        if isinstance(item, dict):
            audio_content = item.get("audio_content") or item.get("audio") or ""
            if audio_content:
                tokens = max(len(str(audio_content)) // 100, 1)
                total += tokens

    return total
