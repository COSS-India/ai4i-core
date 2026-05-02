"""
Authentication dependencies for route injection.

Uses the shared ai4icore_auth library for JWT verification — the SAME
verifier that every other microservice uses. Auth-service is a consumer
of the shared lib, not a parallel implementation.
"""

import logging
from uuid import UUID

from cryptography.hazmat.primitives import serialization
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from ai4icore_auth.jwt_verifier import (
    AuthClaims,
    JWTExpiredError,
    JWTVerificationError,
    JWTVerifier,
)

from app.core.config import settings
from app.core.database import get_db
from app.core.security import key_manager
from app.core.exceptions import (
    AuthenticationRequiredError,
    TokenExpiredError,
    TokenInvalidError,
    TokenRevokedError,
    UserInactiveError,
    UserNotFoundError,
)
from app.dependencies.services import get_cache_service
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.cache_service import CacheService
from app.services.token_service import TokenPayload

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)

# Module-level shared verifier — initialized during lifespan via init_jwt_verifier()
_jwt_verifier = None


def get_jwt_verifier():
    """Return the shared JWTVerifier instance."""
    if _jwt_verifier is None:
        raise RuntimeError("JWTVerifier not initialized. Call init_jwt_verifier() during startup.")
    return _jwt_verifier


async def init_jwt_verifier() -> None:
    """
    Initialize the shared JWTVerifier using the auth-service's own key manager.
    Called during app lifespan startup.
    """
    global _jwt_verifier
    verifier = JWTVerifier(
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
    )

    for pair in key_manager.get_all_public_keys():
        pem = pair.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        verifier.load_public_key(pair.kid, pem)

    _jwt_verifier = verifier
    logger.info("Shared JWTVerifier initialized with %d public keys.", verifier.loaded_key_count)


async def get_current_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    cache_service: CacheService = Depends(get_cache_service),
) -> TokenPayload:
    """
    Validate the Bearer token using the shared ai4icore_auth JWTVerifier.
    API key tokens with a token_id are checked for revocation via Redis only —
    cache miss = revoked (no DB fallback on the hot path).
    """
    if credentials is None:
        raise AuthenticationRequiredError()

    token = credentials.credentials
    verifier = get_jwt_verifier()

    try:
        claims: AuthClaims = await verifier.verify(token)
    except JWTExpiredError as exc:
        raise TokenExpiredError() from exc
    except JWTVerificationError as exc:
        raise TokenInvalidError(exc.message) from exc

    payload = TokenPayload({
        "sub": str(claims.user_id),
        "tenant_id": claims.tenant_id,
        "permission_ids": claims.permission_ids,
        "type": claims.token_type,
        "token_id": claims.token_id,
    })

    if payload.token_id:
        revoked = await _check_token_revocation(
            payload.token_id, payload.token_type, cache_service,
        )
        if revoked:
            raise TokenRevokedError()

    return payload


async def _check_token_revocation(
    token_id: str,
    token_type: str | None,
    cache_service: CacheService,
) -> bool:
    """
    Generic revocation check. Currently only api_key tokens are tracked;
    other token types are considered non-revocable here.
    """
    if token_type == "api_key":
        return await _check_api_key_revocation(token_id, cache_service)
    return False


async def _check_api_key_revocation(
    token_id: str,
    cache_service: CacheService,
) -> bool:
    """
    Check if an API key token_id has been revoked.

    Redis-only — cache is the runtime source of truth. Keys are SETEX'd at
    creation and DEL'd on revoke; cache miss means the key was never issued,
    revoked, or its TTL expired — all of which we treat as revoked. No DB
    fallback: the validate hot path stays Postgres-free, and a flushed
    Redis fail-closes (forces re-issuance) instead of silently re-allowing
    keys that had been revoked.
    """
    return await cache_service.get_api_key_cache(token_id) is None


async def get_current_user(
    payload: TokenPayload = Depends(get_current_token),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the authenticated user (full ORM row) from the token payload."""
    repo = UserRepository(db)
    user = await repo.get_by_id(UUID(payload.sub))
    if not user:
        raise UserNotFoundError()
    if not user.is_active:
        raise UserInactiveError()
    return user
