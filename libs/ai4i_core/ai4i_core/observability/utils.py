"""
Utility functions for computing trace/span attributes for ai4i_core observability.

Pure extractors over already-parsed JSON structures (LLM response bodies,
streamed SSE chunks, etc.). All functions return safe defaults on error so
that span enrichment can never break request handling. Import these from
wherever a span attribute needs to be calculated instead of re-deriving the
logic locally.
"""

import logging
from typing import Any, Tuple

logger = logging.getLogger(__name__)


def get_llm_usage(chunk: Any) -> Tuple[int, int]:
    """
    Extract (input_tokens, output_tokens) from an OpenAI/vLLM-shaped usage object.

    Accepts either a full chat-completion response body or a single streamed
    SSE chunk — both carry a ``usage`` block the same way once the caller has
    requested ``stream_options.include_usage``. Returns (0, 0) when ``chunk``
    isn't a dict or carries no ``usage``, so callers can apply this
    unconditionally without a type check first.
    """
    try:
        usage = (chunk.get("usage") if isinstance(chunk, dict) else None) or {}
        return usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
    except Exception as e:
        logger.warning(f"Error extracting LLM usage: {e}")
        return 0, 0
