"""Thin auth wrapper — delegates to the shared ai4icore_auth library."""

from fastapi import Request
from ai4icore_auth.providers import create_auth_providers


def is_try_it_request(request: Request) -> bool:
    """Allow anonymous access only when BOTH conditions are met:
    1. The request carries the X-Try-It: true header (set explicitly by NMT try-it router)
    2. The path is one of the specific read-only endpoints used by the NMT try-it flow

    This ensures that:
    - Only the NMT try-it API can trigger this bypass (it alone sets X-Try-It on the call)
    - Generic middleware in other services (ASR, TTS, etc.) does NOT forward X-Try-It,
      so their model-management calls still require proper auth
    - Direct external calls to model-management without X-Try-It: true are rejected normally
    """
    x_try_it = request.headers.get("X-Try-It") or request.headers.get("x-try-it")
    if not x_try_it or str(x_try_it).strip().lower() != "true":
        return False

    path = request.url.path
    method = request.method.upper()

    if method == "POST" and path.endswith("/api/v1/model-management/experiments/select-variant"):
        return True
    if method == "POST" and "/api/v1/model-management/services/" in path:
        return True
    if method == "POST" and path.endswith("/api/v1/model-management/experiments/track-metric"):
        return True

    return False


AuthProvider, OptionalAuthProvider = create_auth_providers(
    allow_anonymous=is_try_it_request
)
