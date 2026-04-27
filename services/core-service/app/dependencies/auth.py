"""
Authentication dependencies for route injection.

Core-service is a *consumer* of the shared ai4icore_auth library — it
verifies tokens issued by auth-service via JWKS / RS256. Permission
checks read the endpoint→permission map from Redis (DB 0), populated
by auth-service at startup.
"""

import logging
from typing import Optional

from fastapi import Request

from ai4icore_auth.jwt_verifier import AuthClaims
from ai4icore_auth.providers import build_jwt_verifier, create_auth_providers

logger = logging.getLogger(__name__)


# ── Module-level shared verifier ──
# Constructed lazily; key material is loaded from JWKS during the first
# request via providers.create_auth_providers().
_jwt_verifier = None


def get_jwt_verifier():
    """Return the shared JWTVerifier (built lazily on first call)."""
    global _jwt_verifier
    if _jwt_verifier is None:
        _jwt_verifier = build_jwt_verifier()
    return _jwt_verifier


# ── Permission-checked auth dependencies ──
#
# AuthProvider:         enforces that a valid token is present AND has the
#                       endpoint's required permission (loaded from Redis).
# OptionalAuthProvider: same, but returns None for missing tokens.

AuthProvider, OptionalAuthProvider = create_auth_providers()


# ── Helpers used by route handlers ──


def get_user_id(request: Request) -> Optional[str]:
    """Extract the calling user's id (string) from request.state.

    Returns None for anonymous requests.
    """
    user_id = getattr(request.state, "user_id", None)
    return str(user_id) if user_id is not None else None


def get_auth_claims(request: Request) -> Optional[AuthClaims]:
    """Return the parsed AuthClaims from request.state, if any."""
    return getattr(request.state, "jwt_claims", None)
