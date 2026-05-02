"""
Service dependency factories.

Routes use these via Depends() — never construct repos or services directly.
This is the ONLY place where repositories are imported and wired into services.
"""

from functools import lru_cache

from ai4icore_email import EmailClient
from ai4icore_email.providers.factory import build_provider
from ai4icore_email.settings import EmailSettings
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from app.core.database import get_db
from app.core.redis import get_redis
from app.repositories.api_key_repository import APIKeyRepository
from app.repositories.credentials_repository import CredentialsRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.repositories.verification_repository import VerificationRepository
from app.services.api_key_service import APIKeyService
from app.services.auth_service import AuthService
from app.services.cache_service import CacheService
from app.services.oauth_service import OAuthService
from app.services.role_service import RoleService
from app.services.tenant_service import TenantService
from app.services.token_service import TokenService
from app.services.user_service import UserService


@lru_cache(maxsize=1)
def _email_client_singleton() -> EmailClient:
    return EmailClient(build_provider(EmailSettings()))


def get_email_client() -> EmailClient:
    return _email_client_singleton()


async def get_cache_service(
    redis: aioredis.Redis = Depends(get_redis),
) -> CacheService:
    return CacheService(redis)


async def get_role_service(
    db: AsyncSession = Depends(get_db),
) -> RoleService:
    return RoleService(RoleRepository(db))


async def get_user_service(
    db: AsyncSession = Depends(get_db),
) -> UserService:
    return UserService(UserRepository(db), RoleRepository(db))


async def get_auth_service(
    db: AsyncSession = Depends(get_db),
    email_client: EmailClient = Depends(get_email_client),
) -> AuthService:
    return AuthService(
        user_repo=UserRepository(db),
        role_service=RoleService(RoleRepository(db)),
        token_service=TokenService(),
        credentials_repo=CredentialsRepository(db),
        refresh_token_repo=RefreshTokenRepository(db),
        verification_repo=VerificationRepository(db),
        tenant_repo=TenantRepository(db),
        email_client=email_client,
    )


async def get_api_key_service(
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache_service),
) -> APIKeyService:
    return APIKeyService(APIKeyRepository(db), cache)


async def get_tenant_service(
    db: AsyncSession = Depends(get_db),
    auth_service: AuthService = Depends(get_auth_service),
) -> TenantService:
    return TenantService(
        tenant_repo=TenantRepository(db),
        user_repo=UserRepository(db),
        role_repo=RoleRepository(db),
        auth_service=auth_service,
    )


async def get_oauth_service(
    db: AsyncSession = Depends(get_db),
    email_client: EmailClient = Depends(get_email_client),
) -> OAuthService:
    return OAuthService(
        user_repo=UserRepository(db),
        refresh_token_repo=RefreshTokenRepository(db),
        role_service=RoleService(RoleRepository(db)),
        token_service=TokenService(),
        email_client=email_client,
    )


