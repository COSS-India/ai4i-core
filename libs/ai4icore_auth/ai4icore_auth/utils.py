import hashlib
from typing import Optional

from fastapi import Header


def get_api_key_from_header(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """Extract API key from Authorization header."""
    if not authorization:
        return None

    if authorization.startswith("Bearer "):
        return authorization[7:]
    if authorization.startswith("ApiKey "):
        return authorization[7:]
    return authorization


def hash_api_key(api_key: str) -> str:
    """Hash API key using SHA256."""
    return hashlib.sha256(api_key.encode()).hexdigest()

