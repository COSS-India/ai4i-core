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
        return int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
    except Exception as e:
        logger.error(f"Error extracting LLM usage: {e}")
        return 0, 0


def get_llm_cached_tokens(chunk: Any) -> int:
    """
    Extract the cached part of the prompt from an OpenAI/vLLM-shaped usage
    object: ``usage.prompt_tokens_details.cached_tokens``.

    Cached tokens are a subset of ``prompt_tokens``, not extra to them. vLLM
    only fills ``prompt_tokens_details`` when started with
    ``--enable-prompt-tokens-details``; without it the block is null. A
    missing or null block, a non-dict chunk, or a bad value all return 0, so
    every prompt token is then priced as ordinary input.
    ``created_cache_tokens`` (tokens this request wrote to the cache) is not
    a cache hit and is deliberately ignored.
    """
    try:
        usage = (chunk.get("usage") if isinstance(chunk, dict) else None) or {}
        details = usage.get("prompt_tokens_details")
        if not isinstance(details, dict):
            return 0
        return max(int(details.get("cached_tokens") or 0), 0)
    except Exception as e:
        logger.error(f"Error extracting LLM cached tokens: {e}")
        return 0
