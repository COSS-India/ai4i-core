"""
Authentication dependencies for route injection.

JWT verification logic is now local to auth-service (no longer shared library).
"""

import logging
from typing import NamedTuple, Optional
from uuid import UUID

from cryptography.hazmat.primitives import serialization
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.jwt_verifier import JWTVerifier

from app.core.config import settings
from app.core.database import get_db
from app.core.security import key_manager
from app.core.exceptions import (
    AuthenticationRequiredError,
    UserInactiveError,
    UserNotFoundError,
)
from app.dependencies.services import get_cache_service
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.cache_service import CacheService

logger = logging.getLogger(__name__)

# Module-level shared verifier — initialized during lifespan via init_jwt_verifier()
_jwt_verifier = None


def get_jwt_verifier():
    """Return the shared JWTVerifier instance."""
    if _jwt_verifier is None:
        raise RuntimeError("JWTVerifier not initialized. Call init_jwt_verifier() during startup.")
    return _jwt_verifier


def init_jwt_verifier() -> None:
    """
    Initialize the shared JWTVerifier using the auth-service's own key manager.
    Called during app lifespan startup.
    """
    global _jwt_verifier
    verifier = JWTVerifier(
        issuer=settings.jwt_issuer,
        audience=settings.jwt_audience,
        http_timeout_seconds=settings.jwks_http_timeout_seconds,
    )

    for pair in key_manager.get_all_public_keys():
        pem = pair.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        verifier.load_public_key(pair.kid, pem)

    _jwt_verifier = verifier
    logger.info("Shared JWTVerifier initialized with %d public keys.", verifier.loaded_key_count)


async def check_token_revocation(
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


def get_current_user_id(request: Request) -> UUID:
    """Read X-User-ID header only. No DB call. Gateway controls token issuance."""
    user_id_str = request.headers.get("X-User-ID")
    if not user_id_str:
        raise AuthenticationRequiredError()
    try:
        return UUID(user_id_str)
    except (ValueError, TypeError):
        raise AuthenticationRequiredError()


class UserContext(NamedTuple):
    user_id: UUID
    tenant_id: str | None


def get_user_context(request: Request) -> UserContext:
    """Read X-User-ID + X-Tenant-ID headers only. No DB call."""
    user_id = get_current_user_id(request)
    tenant_id = request.headers.get("X-Tenant-ID")
    return UserContext(user_id=user_id, tenant_id=tenant_id)


async def get_optional_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Return the authenticated user when gateway headers are present, else None."""
    user_id_str = request.headers.get("X-User-ID")
    if not user_id_str:
        return None
    try:
        user_id = UUID(user_id_str)
    except (ValueError, TypeError):
        return None

    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user or not user.is_active:
        return None
    return user


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Resolve the authenticated user from the X-User-ID gateway header.
    The gateway has already validated the token; this just fetches the User ORM object.
    """
    user_id = get_current_user_id(request)

    repo = UserRepository(db)
    user = await repo.get_by_id(user_id)
    if not user:
        raise UserNotFoundError()
    if not user.is_active:
        raise UserInactiveError()
    return user
