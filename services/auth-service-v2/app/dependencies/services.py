"""
Service dependency factories.

Routes use these via Depends() — never construct repos or services directly.
This is the ONLY place where repositories are imported and wired into services.
"""

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from app.core.database import get_db
from app.core.redis import (
    get_redis_api_keys,
    get_redis_api_permissions,
    get_redis_refresh_tokens,
    get_redis_role_permissions,
)
from app.repositories.api_key_repository import APIKeyRepository
from app.repositories.oauth_repository import OAuthRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository
from app.services.api_key_service import APIKeyService
from app.services.auth_service import AuthService
from app.services.cache_service import CacheService
from app.services.oauth_service import OAuthService
from app.services.password_service import PasswordService
from app.services.role_service import RoleService
from app.services.session_service import SessionService
from app.services.token_service import TokenService
from app.services.user_service import UserService


async def get_cache_service(
    redis_api_keys: aioredis.Redis = Depends(get_redis_api_keys),
    redis_refresh_tokens: aioredis.Redis = Depends(get_redis_refresh_tokens),
    redis_role_permissions: aioredis.Redis = Depends(get_redis_role_permissions),
    redis_api_permissions: aioredis.Redis = Depends(get_redis_api_permissions),
) -> CacheService:
    return CacheService(
        redis_api_keys=redis_api_keys,
        redis_refresh_tokens=redis_refresh_tokens,
        redis_role_permissions=redis_role_permissions,
        redis_api_permissions=redis_api_permissions,
    )


async def get_role_service(
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache_service),
) -> RoleService:
    return RoleService(RoleRepository(db), cache)


async def get_user_service(
    db: AsyncSession = Depends(get_db),
) -> UserService:
    return UserService(UserRepository(db), RoleRepository(db))


async def get_auth_service(
    request: Request,
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache_service),
) -> AuthService:
    # Optional: TenantService for resolving tenant_id on login
    tenant_service = None
    mt_factory = getattr(request.app.state, "multi_tenant_session_factory", None)
    if mt_factory:
        from app.services.tenant_service import TenantService
        tenant_service = TenantService(mt_factory)

    return AuthService(
        user_repo=UserRepository(db),
        role_service=RoleService(RoleRepository(db), cache),
        token_service=TokenService(),
        password_service=PasswordService(),
        session_service=SessionService(SessionRepository(db), cache),
        cache_service=cache,
        tenant_service=tenant_service,
    )


async def get_api_key_service(
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache_service),
) -> APIKeyService:
    return APIKeyService(APIKeyRepository(db), TokenService(), cache)


async def get_oauth_service(
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache_service),
) -> OAuthService:
    return OAuthService(
        user_repo=UserRepository(db),
        oauth_repo=OAuthRepository(db),
        role_repo=RoleRepository(db),
        token_service=TokenService(),
        session_service=SessionService(SessionRepository(db), cache),
        cache_service=cache,
    )
