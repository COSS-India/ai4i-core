"""Thin auth wrapper — delegates to the shared ai4icore_auth library."""

import re

from fastapi import Request
from ai4icore_auth.providers import create_auth_providers

# Exact-match patterns for the three read-only endpoints used by the NMT try-it flow.
# Using anchored regex prevents sub-path bypass (e.g. /services/{id}/delete).
_ALLOWED_TRY_IT_PATHS = (
    re.compile(r"^/api/v1/model-management/services/[^/]+$"),           # GET service details
    re.compile(r"^/api/v1/model-management/experiments/select-variant$"),
    re.compile(r"^/api/v1/model-management/experiments/track-metric$"),
)


def is_try_it_request(request: Request) -> bool:
    """Allow anonymous access only when BOTH conditions are met:
    1. X-Try-It: true header is present (injected by APISIX on the try-it route,
       stripped by APISIX on all other routes including model-management)
    2. Path exactly matches one of the read-only try-it endpoints — anchored regex
       prevents sub-path bypass (e.g. /services/{id}/admin)
    """
    x_try_it = request.headers.get("X-Try-It") or request.headers.get("x-try-it")
    if not x_try_it or str(x_try_it).strip().lower() != "true":
        return False

    if request.method.upper() != "POST":
        return False

    return any(pattern.match(request.url.path) for pattern in _ALLOWED_TRY_IT_PATHS)


AuthProvider, OptionalAuthProvider = create_auth_providers(
    allow_anonymous=is_try_it_request
)
