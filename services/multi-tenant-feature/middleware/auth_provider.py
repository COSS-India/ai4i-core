"""Thin auth wrapper — delegates to the shared ai4icore_auth library.

Multi-tenant preserves permissive behavior: requests without auth header are allowed.
"""

from fastapi import Request

from ai4icore_auth.providers import create_auth_providers


def _allow_no_token(request: Request) -> bool:
    """Allow anonymous access when no Authorization header is present."""
    return not request.headers.get("authorization")


AuthProvider, OptionalAuthProvider = create_auth_providers(
    allow_anonymous=_allow_no_token,
)
