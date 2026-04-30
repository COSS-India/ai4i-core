"""Authentication dependencies."""
from fastapi import Request

from ai4icore_auth.providers import create_auth_providers


def _allow_anonymous(request: Request) -> bool:
    """Allow anonymous access for the dedicated try-it endpoint only."""
    return request.url.path.rstrip("/") == "/api/v1/try-it"


AuthProvider, OptionalAuthProvider = create_auth_providers(
    allow_anonymous=_allow_anonymous
)
