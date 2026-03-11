"""Thin auth wrapper -- delegates to the shared ai4icore_auth library."""

from typing import Tuple

from fastapi import Request

from ai4icore_auth import (
    create_auth_provider,
    create_optional_auth_provider,
)


def determine_service_and_action(request: Request) -> Tuple[str, str]:
    """Pipeline-specific service/action resolution.

    Default action for POST is ``inference`` (not ``read``).
    """
    path = request.url.path.lower()
    method = request.method.upper()
    service = "pipeline"

    if "/inference" in path and method == "POST":
        action = "inference"
    elif method == "GET" or "/info" in path:
        action = "read"
    else:
        action = "inference" if method == "POST" else "read"

    return service, action


AuthProvider = create_auth_provider(
    service_name="pipeline",
    determine_service_and_action=determine_service_and_action,
)

OptionalAuthProvider = create_optional_auth_provider(
    service_name="pipeline",
    determine_service_and_action=determine_service_and_action,
)
