"""Thin auth wrapper -- delegates to the shared ai4icore_auth library."""

from typing import Tuple

from fastapi import Request

from ai4icore_auth import (
    create_auth_provider,
    create_optional_auth_provider,
)


def determine_service_and_action(request: Request) -> Tuple[str, str]:
    """LLM-specific service/action resolution.

    Extracts service name from URL path (e.g. ``/api/v1/llm/...`` -> ``llm``).
    Falls back to ``"llm"`` when no known service slug is found.
    """
    path = request.url.path.lower()
    method = request.method.upper()

    service = None
    for svc in ["asr", "nmt", "tts", "pipeline", "model-management", "llm"]:
        if f"/api/v1/{svc}/" in path or path.endswith(f"/api/v1/{svc}"):
            service = svc
            break
    if not service:
        service = "llm"

    if "/inference" in path and method == "POST":
        action = "inference"
    elif method == "GET" or "/services" in path or "/models" in path or "/languages" in path:
        action = "read"
    else:
        action = "read"

    return service, action


AuthProvider = create_auth_provider(
    service_name="llm",
    determine_service_and_action=determine_service_and_action,
)

OptionalAuthProvider = create_optional_auth_provider(
    service_name="llm",
    determine_service_and_action=determine_service_and_action,
)
