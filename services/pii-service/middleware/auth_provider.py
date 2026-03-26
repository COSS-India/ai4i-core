"""Thin auth wrapper — delegates to the shared ai4icore_auth library.

PII supports anonymous "try-it" access for redact in dev smoke tests.
"""

from fastapi import Request

from ai4icore_auth.providers import create_auth_providers


def is_try_it_request(request: Request) -> bool:
    # Always allow health checks without auth
    if request.url.path.endswith("/health"):
        return True

    try_it = request.headers.get("X-Try-It") or request.headers.get("x-try-it")
    if not try_it or str(try_it).lower() != "true":
        return False

    return request.method.upper() == "POST" and request.url.path.endswith("/redact")


AuthProvider, OptionalAuthProvider = create_auth_providers(
    allow_anonymous=is_try_it_request,
)

