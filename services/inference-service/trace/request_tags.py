"""
Caller-supplied attribution tags for LLM requests (OpenAI `user` / `metadata`).

Tenants tag a request with their own end user (`user`) and free-form
key-value pairs (`metadata`). The LLM route validates them and stores them in
ai4i_core.context for the life of the request; get_context_attributes() copies
them onto every span (request, model, ai-inference) — so they reach OpenSearch
and the PPU consumer without being threaded through each function signature.

This module holds the OpenAI-request rules (validation, what's stripped before
forwarding, span attribute names). Storage lives in ai4i_core.context alongside
the other per-request values; app_id is gateway identity, set there by
RequestMiddleware like tenantId.
"""

from typing import Any, Dict, Optional, Tuple

from ai4i_core.context import get_request_tags

# Limits from the ticket (they mirror OpenAI's own `metadata` rules); the
# `user` cap is ours, since the ticket sets none.
MAX_METADATA_KEYS = 16
MAX_METADATA_KEY_LENGTH = 64
MAX_METADATA_VALUE_LENGTH = 512
MAX_USER_LENGTH = 256
RESERVED_KEY_PREFIX = "orch_"

# Span attribute names. `enduser.id` is the OTel semantic-convention name for
# the caller's end user — deliberately not `userId`, which means the platform
# user (the API key's creator, from X-User-ID).
END_USER_ATTR = "enduser.id"
METADATA_ATTR_PREFIX = "metadata."

# Fields stripped from the payload before it is forwarded upstream: vLLM
# doesn't use them, and the tenant's end-user ID has no reason to reach its logs.
CALLER_TAG_FIELDS = ("user", "metadata")


def validate_request_tags(payload: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """
    Check the caller's `user` and `metadata` against the ticket's rules.

    Returns ``(param, message)`` for the first violation, or None when both are
    valid or absent. A null value counts as absent.
    """
    user = payload.get("user")
    if user is not None:
        if not isinstance(user, str):
            return "user", "'user' must be a string."
        if len(user) > MAX_USER_LENGTH:
            return "user", f"'user' must be at most {MAX_USER_LENGTH} characters."

    metadata = payload.get("metadata")
    if metadata is None:
        return None
    if not isinstance(metadata, dict):
        return "metadata", "'metadata' must be an object of string keys to string values."
    if len(metadata) > MAX_METADATA_KEYS:
        return "metadata", (
            f"'metadata' must have at most {MAX_METADATA_KEYS} keys, got {len(metadata)}."
        )
    for key, value in metadata.items():
        # An empty key would become the span attribute "metadata.", which
        # OpenSearch rejects as an empty field name — the whole span would be lost.
        if not key:
            return "metadata", "'metadata' keys must not be empty."
        if len(key) > MAX_METADATA_KEY_LENGTH:
            return "metadata", (
                f"'metadata' keys must be at most {MAX_METADATA_KEY_LENGTH} characters."
            )
        # OpenSearch reads a dot in a field name as nesting, so "order.id"
        # turns `order` into an object — and every later span (from any
        # tenant) with a plain "order" key fails to index for that whole
        # daily traces-* index.
        if "." in key:
            return "metadata", f"'metadata' key '{key}' must not contain '.'."
        if key.startswith(RESERVED_KEY_PREFIX):
            return "metadata", (
                f"'metadata' key '{key}' uses the reserved prefix '{RESERVED_KEY_PREFIX}'."
            )
        if not isinstance(value, str):
            return "metadata", f"'metadata' value for key '{key}' must be a string."
        if len(value) > MAX_METADATA_VALUE_LENGTH:
            return "metadata", (
                f"'metadata' value for key '{key}' must be at most "
                f"{MAX_METADATA_VALUE_LENGTH} characters."
            )
    return None


def get_request_tag_attributes() -> Dict[str, str]:
    """Span attributes for the current request's caller tags; {} when none were set."""
    tags = get_request_tags()
    if not tags:
        return {}
    attrs: Dict[str, str] = {}
    if tags.get("user"):
        attrs[END_USER_ATTR] = tags["user"]
    for key, value in tags.get("metadata", {}).items():
        attrs[f"{METADATA_ATTR_PREFIX}{key}"] = value
    return attrs


def strip_caller_tags(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Copy of the payload without `user` / `metadata`, for forwarding upstream."""
    return {k: v for k, v in payload.items() if k not in CALLER_TAG_FIELDS}
