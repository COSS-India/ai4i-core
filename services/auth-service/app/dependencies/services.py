"""
Service dependency factories.

Routes use these via Depends() — never construct repos or services directly.
This is the ONLY place where repositories are imported and wired into services.
"""

from functools import lru_cache

from ai4icore_core.email import EmailClient
from ai4icore_core.email.providers.factory import build_provider
from ai4icore_core.email.settings import EmailSettings
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


def get_token_service() -> TokenService:
    return TokenService()


async def get_role_service(
    db: AsyncSession = Depends(get_db),
) -> RoleService:
    return RoleService(RoleRepository(db))


async def get_user_service(
    db: AsyncSession = Depends(get_db),
) -> UserService:
    return UserService(UserRepository(db), RoleRepository(db))


async def get_api_key_service(
    db: AsyncSession = Depends(get_db),
    cache: CacheService = Depends(get_cache_service),
) -> APIKeyService:
    return APIKeyService(
        APIKeyRepository(db),
        cache,
        user_repo=UserRepository(db),
        tenant_repo=TenantRepository(db),
    )


async def get_auth_service(
    db: AsyncSession = Depends(get_db),
    role_service: RoleService = Depends(get_role_service),
    token_service: TokenService = Depends(get_token_service),
    email_client: EmailClient = Depends(get_email_client),
    api_key_service: APIKeyService = Depends(get_api_key_service),
) -> AuthService:
    return AuthService(
        user_repo=UserRepository(db),
        role_service=role_service,
        token_service=token_service,
        credentials_repo=CredentialsRepository(db),
        refresh_token_repo=RefreshTokenRepository(db),
        verification_repo=VerificationRepository(db),
        tenant_repo=TenantRepository(db),
        email_client=email_client,
        api_key_service=api_key_service,
    )


async def get_tenant_service(
    db: AsyncSession = Depends(get_db),
    role_service: RoleService = Depends(get_role_service),
    token_service: TokenService = Depends(get_token_service),
    email_client: EmailClient = Depends(get_email_client),
    api_key_service: APIKeyService = Depends(get_api_key_service),
) -> TenantService:
    """Lightweight tenant service — only injects what's needed for user provisioning.

    Avoids pulling in entire AuthService (8 dependencies) when we only need
    6 of them for provision_user(). Routes never called this to use other
    AuthService methods, so this optimization is safe.
    """
    return TenantService(
        tenant_repo=TenantRepository(db),
        user_repo=UserRepository(db),
        role_service=role_service,
        verification_repo=VerificationRepository(db),
        credentials_repo=CredentialsRepository(db),
        token_service=token_service,
        email_client=email_client,
        api_key_service=api_key_service,
    )


async def get_oauth_service(
    db: AsyncSession = Depends(get_db),
    role_service: RoleService = Depends(get_role_service),
    token_service: TokenService = Depends(get_token_service),
    email_client: EmailClient = Depends(get_email_client),
) -> OAuthService:
    return OAuthService(
        user_repo=UserRepository(db),
        refresh_token_repo=RefreshTokenRepository(db),
        tenant_repo=TenantRepository(db),
        role_service=role_service,
        token_service=token_service,
        email_client=email_client,
    )
