"""Thin auth wrapper -- delegates to the shared ai4icore_auth library.

NMT has a custom determine_service_and_action that extracts service name from
the URL path, and supports anonymous try-it requests.
"""

from typing import Tuple

from fastapi import Request

from ai4icore_auth import (
    create_auth_provider,
    create_optional_auth_provider,
)


def determine_service_and_action(request: Request) -> Tuple[str, str]:
    """NMT-specific service/action resolution.

    Extracts service name from URL path (e.g. ``/api/v1/nmt/...`` -> ``nmt``).
    Falls back to ``"nmt"`` when no known service slug is found.
    """
    path = request.url.path.lower()
    method = request.method.upper()

    service = None
    for svc in ["asr", "nmt", "tts", "pipeline", "model-management", "llm"]:
        if f"/api/v1/{svc}/" in path or path.endswith(f"/api/v1/{svc}"):
            service = svc
            break
    if not service:
        service = "nmt"

    if "/inference" in path and method == "POST":
        action = "inference"
    elif method == "GET" or "/services" in path or "/models" in path or "/languages" in path:
        action = "read"
    else:
        action = "read"

    return service, action


def is_try_it_request(request: Request) -> bool:
    """Allow anonymous Try-It access for NMT inference only."""
    if request.url.path.endswith("/api/v1/try-it"):
        return True
    try_it = request.headers.get("X-Try-It") or request.headers.get("x-try-it")
    if not try_it or str(try_it).lower() != "true":
        return False
    return request.method.upper() == "POST" and request.url.path.endswith("/api/v1/nmt/inference")


AuthProvider = create_auth_provider(
    service_name="nmt",
    determine_service_and_action=determine_service_and_action,
    allow_anonymous=True,  # supports try-it anonymous access
)

OptionalAuthProvider = create_optional_auth_provider(
    service_name="nmt",
    determine_service_and_action=determine_service_and_action,
    allow_anonymous=True,
)
