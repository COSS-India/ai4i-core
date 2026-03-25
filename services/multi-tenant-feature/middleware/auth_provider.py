"""Thin auth wrapper — delegates to the shared ai4icore_auth library.

Multi-tenant preserves permissive behavior: requests without auth header are allowed.
"""

from fastapi import Request

from ai4icore_auth.providers import create_auth_providers


# def _allow_no_token(request: Request) -> bool:
#     """Allow anonymous access when no Authorization header is present."""
#     return not request.headers.get("authorization")


# AuthProvider, OptionalAuthProvider = create_auth_providers(
#     allow_anonymous=_allow_no_token,
# )

import logging
from dataclasses import dataclass
from typing import Optional

from ai4icore_auth.providers import create_auth_providers, build_jwt_verifier
from ai4icore_auth.jwt_verifier import JWTVerificationError, JWTExpiredError

logger = logging.getLogger(__name__)

AuthProvider, OptionalAuthProvider = create_auth_providers()


@dataclass
class APIKeyValidationResult:
    """Result of JWT API key validation for streaming."""
    user_id: int
    token_id: str
    permission_ids: list[int]


async def validate_api_key_jwt(api_key_jwt: str) -> APIKeyValidationResult:
    """Validate a JWT API key for WebSocket streaming connections.

    Args:
        api_key_jwt: The full JWT token string (issued by auth-service).

    Returns:
        APIKeyValidationResult with user_id, token_id, and permission_ids.

    Raises:
        JWTVerificationError: If the token is invalid or expired.
    """
    verifier = build_jwt_verifier()
    if verifier.loaded_key_count == 0:
        await verifier.initialize()

    claims = await verifier.verify(api_key_jwt)

    if claims.token_type != "api_key":
        raise JWTVerificationError("Not an API key token.")

    return APIKeyValidationResult(
        user_id=claims.user_id,
        token_id=claims.token_id or "",
        permission_ids=claims.permission_ids,
    )

