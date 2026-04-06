"""HTTP(S) URL validation for service endpoints."""

from __future__ import annotations

from urllib.parse import urlparse

# Reasonable upper bound for stored URLs (DB column is 500 chars; keep aligned).
_MAX_LEN = 500
_ALLOWED_SCHEMES = frozenset({"http", "https"})


def normalize_http_url(url: str) -> str:
    """
    Validate and return a normalized URL string (stripped).

    Raises:
        ValueError: with a short, user-facing reason.
    """
    if not url or not isinstance(url, str):
        raise ValueError("Endpoint URL is required")

    u = url.strip()
    if not u:
        raise ValueError("Endpoint URL is required")

    if len(u) > _MAX_LEN:
        raise ValueError(f"Endpoint URL exceeds maximum length ({_MAX_LEN} characters)")

    parsed = urlparse(u)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise ValueError("Endpoint URL must use http or https")

    if not parsed.netloc:
        raise ValueError("Endpoint URL must include a host (e.g. https://host:port)")

    return u


def validate_http_url(url: str) -> str:
    """Alias for :func:`normalize_http_url` (explicit naming for call sites)."""
    return normalize_http_url(url)
