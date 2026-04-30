"""
Authentication Utilities
Utility functions for handling authentication headers and tokens
"""

import logging
from typing import Dict
from fastapi import Request

logger = logging.getLogger(__name__)


def extract_auth_headers(request: Request) -> Dict[str, str]:
    """
    Extract authentication headers from incoming request to forward to downstream services.

    This function extracts Authorization, X-API-Key, and X-Auth-Source headers from the
    incoming request in a case-insensitive manner. These headers are typically forwarded
    to the model management service or other downstream services that require authentication.

    Args:
        request: FastAPI Request object containing headers

    Returns:
        Dictionary containing extracted authentication headers with normalized keys:
        - "Authorization": Bearer token or API key
        - "X-API-Key": API key (if present)
        - "X-Auth-Source": Authentication source indicator (e.g., "AUTH_TOKEN", "API_KEY")
    """
    auth_headers: Dict[str, str] = {}

    # FastAPI headers are case-insensitive, but we normalize to standard case
    authorization = request.headers.get("Authorization") or request.headers.get("authorization")
    if authorization:
        auth_headers["Authorization"] = authorization

    x_api_key = request.headers.get("X-API-Key") or request.headers.get("x-api-key")
    if x_api_key:
        auth_headers["X-API-Key"] = x_api_key

    x_auth_source = request.headers.get("X-Auth-Source") or request.headers.get("x-auth-source")
    if x_auth_source:
        auth_headers["X-Auth-Source"] = x_auth_source

    # Fallback: iterate all headers for case-insensitive variants
    for key, value in request.headers.items():
        key_lower = key.lower()
        if key_lower == "authorization" and "Authorization" not in auth_headers:
            auth_headers["Authorization"] = value
        elif key_lower == "x-api-key" and "X-API-Key" not in auth_headers:
            auth_headers["X-API-Key"] = value
        elif key_lower == "x-auth-source" and "X-Auth-Source" not in auth_headers:
            auth_headers["X-Auth-Source"] = value

    if not auth_headers:
        logger.warning(
            "No auth headers found in request. Available headers: %s",
            list(request.headers.keys())
        )

    return auth_headers
