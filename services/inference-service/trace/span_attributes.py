"""
Compute span attributes for inference tracing.

Trace-specific enrichment that Observability cannot provide via X-Tracing-*
headers: output type detection and output token counting after inference.
Input-side attributes are produced once by ObservabilityMiddleware and consumed
from headers in request_span.traced_inference.

count_input_tokens() is retained only for per_item call_mode, where each
ai-inference span covers a subset of the request and header values reflect
the full payload.
"""

import base64
import io
import logging
from typing import Any, Dict, List

import soundfile as sf

logger = logging.getLogger(__name__)


def get_output_type(response_data: List[Dict[str, Any]]) -> str:
    """
    Detect output modality type from Triton response data.

    Inspects response structure to determine modality.
    Returns: "text", "audio", "image", or "unknown"
    """
    try:
        if not response_data or not isinstance(response_data, list):
            return "unknown"

        first_item = response_data[0] if response_data else {}
        if not isinstance(first_item, dict):
            return "unknown"

        # Check for common output field names by modality
        keys = set(first_item.keys())

        # Text: target, output, transcription, translation, result, text
        if keys & {"target", "output", "transcription", "translation", "result", "text"}:
            return "text"

        # Audio: audio_content, audio, samples, waveform
        if keys & {"audio_content", "audio", "samples", "waveform"}:
            return "audio"

        # Image: image, image_content, image_base64, encoding
        if keys & {"image", "image_content", "image_base64", "encoding"}:
            return "image"

        return "unknown"
    except Exception as e:
        logger.warning(f"Error detecting output type: {e}")
        return "unknown"


def count_input_tokens(input_items: List[Any], input_type: str) -> float:
    """
    Per-group billed input units for per_item call_mode only.

    ObservabilityMiddleware injects full-payload billing units via
    X-Tracing-Input-Tokens; use this helper only when a single request
    produces multiple ai-inference spans (one per item).
    """
    try:
        if not input_items:
            return 0

        if input_type == "text":
            return _count_text_tokens(input_items)
        elif input_type == "audio":
            return _count_audio_tokens(input_items)
        elif input_type == "image":
            return _count_image_tokens(input_items)

        return 0
    except Exception as e:
        logger.warning(f"Error counting input tokens: {e}")
        return 0


def count_output_tokens(response_data: List[Dict[str, Any]], output_type: str) -> int:
    """
    Estimate token count for output based on modality.

    Text: character count of output text
    Audio: estimate from output samples
    Image: heuristic from encoded size

    Returns: estimated token count, or 0 on error
    """
    try:
        if not response_data or not isinstance(response_data, list):
            return 0

        if output_type == "text":
            return _count_output_text_tokens(response_data)
        elif output_type == "audio":
            return _count_output_audio_tokens(response_data)
        elif output_type == "image":
            return _count_output_image_tokens(response_data)

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
    language-detection — see inference_types.yaml) are declared as
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
    all bill on real audio duration (inference_types.yaml unit: minutes), not
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

    OCR (the only image-modality service today, see inference_types.yaml
    unit: images) bills per image, not per byte: a request with N images
    in payload["image"] bills N units regardless of each image's
    resolution or file size.
    """
    return len(input_items)


def _count_output_text_tokens(response_data: List[Dict[str, Any]]) -> int:
    """Count tokens from text output by character count (see _count_text_tokens)."""
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


def _count_output_image_tokens(response_data: List[Dict[str, Any]]) -> int:
    """
    Estimate tokens from image output by content size.
    """
    total = 0
    for item in response_data:
        if isinstance(item, dict):
            image_content = item.get("image_content") or item.get("image") or ""
            if image_content:
                tokens = max(len(str(image_content)) // 1000, 1)
                total += tokens

    return total
