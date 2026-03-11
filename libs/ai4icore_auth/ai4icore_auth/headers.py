"""Common header extraction utilities."""

import hashlib
from typing import Optional


def get_api_key_from_header(authorization: Optional[str]) -> Optional[str]:
    """Extract API key from Authorization header.

    Supports: "ApiKey <key>", plain "<key>".
    Bearer tokens are NOT treated as API keys — returns None for "Bearer <token>".
    """
    if not authorization:
        return None
    if authorization.startswith("ApiKey "):
        return authorization[7:]
    if authorization.startswith("Bearer "):
        return None
    return authorization


def hash_api_key(api_key: str) -> str:
    """Hash API key using SHA256."""
    return hashlib.sha256(api_key.encode()).hexdigest()
