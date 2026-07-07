"""
Compute span attributes for inference tracing.

Functions to detect input/output types, count tokens, and calculate payload sizes.
All functions return safe defaults on error to prevent trace enrichment from breaking inference.
"""

import logging
from typing import Any, Dict, List

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
        if payload.get("audio"):
            return "audio"
        if payload.get("image"):
            return "image"
        return "unknown"
    except Exception as e:
        logger.warning(f"Error detecting input type: {e}")
        return "unknown"


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


def count_input_tokens(input_items: List[Any], input_type: str) -> int:
    """
    Estimate token count for input based on modality.

    Text: word count (len(text.split()))
    Audio: estimate from sample count (samples / 16000 * 100)
    Image: heuristic from file size or resolution

    Returns: estimated token count, or 0 on error
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

    Text: word count of output text
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

def _count_text_tokens(input_items: List[Any]) -> int:
    """Count tokens from text input items by word splitting."""
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
    """
    Estimate tokens from audio input items.

    Use num_samples if available, or heuristic from audio data size.
    Estimation: 100 tokens per second of audio at 16kHz.
    """
    total = 0
    for item in input_items:
        if isinstance(item, dict):
            num_samples = item.get("num_samples", 0)
            audio_content = item.get("audio_content", "")
        else:
            num_samples = getattr(item, "num_samples", 0)
            audio_content = getattr(item, "audio_content", "")

        if num_samples > 0:
            # Assume 16kHz sample rate: 100 tokens per second
            tokens = int((num_samples / 16000.0) * 100)
            total += max(tokens, 1)
        elif audio_content:
            # Heuristic: base64 string length / 100 as proxy
            tokens = max(len(str(audio_content)) // 100, 1)
            total += tokens

    return total


def _count_image_tokens(input_items: List[Any]) -> int:
    """
    Estimate tokens from image input items.

    Heuristic: use image_content size (bytes) / 1000 as token estimate.
    """
    total = 0
    for item in input_items:
        if isinstance(item, dict):
            image_content = item.get("image_content", "")
        else:
            image_content = getattr(item, "image_content", "")

        if image_content:
            # Base64 string length / 1000 as heuristic
            tokens = max(len(str(image_content)) // 1000, 1)
            total += tokens

    return total


def _count_output_text_tokens(response_data: List[Dict[str, Any]]) -> int:
    """Count tokens from text output by word splitting."""
    total = 0
    for item in response_data:
        if isinstance(item, dict):
            # Try common output field names
            text = item.get("target") or item.get("output") or item.get("text") or ""
            if isinstance(text, bytes):
                text = text.decode("utf-8", errors="replace")
            total += len(str(text).split())

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
