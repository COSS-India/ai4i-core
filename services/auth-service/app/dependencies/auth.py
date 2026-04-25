"""
Authentication dependencies for route injection.

Uses the shared ai4icore_auth library for JWT verification — the SAME
verifier that every other microservice uses. Auth-service is a consumer
of the shared lib, not a parallel implementation.
"""

import logging
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from ai4icore_auth.jwt_verifier import (
    AuthClaims,
    JWTExpiredError,
    JWTVerificationError,
)

from app.core.database import get_db
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
from app.repositories.api_key_repository import APIKeyRepository
from app.repositories.user_repository import UserRepository
from app.services.cache_service import CacheService
from app.services.token_service import TokenPayload, TokenService

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
    from ai4icore_auth.jwt_verifier import JWTVerifier
    from cryptography.hazmat.primitives import serialization
    from app.core.config import settings
    from app.core.security import key_manager

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


def get_token_service() -> TokenService:
    """Token creation service — auth-service specific (not shared)."""
    return TokenService()


async def get_current_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    cache_service: CacheService = Depends(get_cache_service),
    db: AsyncSession = Depends(get_db),
) -> TokenPayload:
    """
    Validate the Bearer token using the shared ai4icore_auth JWTVerifier.
    API key tokens with a token_id are checked for revocation via Redis + DB fallback.
    """
    if credentials is None:
        raise AuthenticationRequiredError()

    token = credentials.credentials
    verifier = get_jwt_verifier()

    try:
        claims: AuthClaims = await verifier.verify(token)
    except JWTExpiredError:
        raise TokenExpiredError()
    except JWTVerificationError as exc:
        raise TokenInvalidError(exc.message)

    payload = TokenPayload({
        "sub": str(claims.user_id),
        "tenant_id": claims.tenant_id,
        "permission_ids": claims.permission_ids,
        "type": claims.token_type,
        "token_id": claims.token_id,
    })

    if payload.token_id and payload.token_type == "api_key":
        revoked = await _check_api_key_revocation(payload.token_id, cache_service, db)
        if revoked:
            raise TokenRevokedError()

    return payload


async def _check_api_key_revocation(
    token_id: str,
    cache_service: CacheService,
    db: AsyncSession,
) -> bool:
    """
    Check if an API key token_id has been revoked.
    Redis first (presence = valid), DB fallback on cache miss.
    Returns True if revoked, False if valid.
    """
    if await cache_service.is_api_key_valid(token_id):
        return False

    repo = APIKeyRepository(db)
    db_key = await repo.get_by_api_key(token_id)
    if not db_key or not db_key.is_active:
        return True

    ttl = await _remaining_api_key_ttl(db_key)
    if ttl > 0:
        await cache_service.store_api_key_token(token_id, ttl)
    return False


async def _remaining_api_key_ttl(db_key) -> int:
    from app.core.config import settings
    return settings.api_key_expire_days * 86400


async def get_current_user(
    payload: TokenPayload = Depends(get_current_token),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the authenticated user from the token payload."""
    repo = UserRepository(db)
    user = await repo.get_by_id(UUID(payload.sub))
    if not user:
        raise UserNotFoundError()
    if not user.is_active:
        raise UserInactiveError()
    return user


async def get_current_active_user(
    user: User = Depends(get_current_user),
) -> User:
    return user
