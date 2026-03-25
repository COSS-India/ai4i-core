"""
Core authentication business logic: register, login, refresh, logout.
"""

import logging
from typing import Optional

from app.core.config import settings
from app.core.exceptions import (
    DuplicateEntityError,
    InvalidCredentialsError,
    TokenExpiredError,
    TokenInvalidError,
    TokenRevokedError,
    UserInactiveError,
)
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginResponse, TokenRefreshResponse
from app.services.cache_service import CacheService
from app.services.password_service import PasswordService
from app.services.role_service import RoleService
from app.services.session_service import SessionService
from app.services.token_service import TokenService

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(
        self,
        user_repo: UserRepository,
        role_service: RoleService,
        token_service: TokenService,
        password_service: PasswordService,
        session_service: SessionService,
        cache_service: CacheService,
        tenant_service=None,
    ) -> None:
        self._users = user_repo
        self._roles = role_service
        self._tokens = token_service
        self._passwords = password_service
        self._sessions = session_service
        self._cache = cache_service
        self._tenants = tenant_service

    # ── Register ──

    async def register(
        self,
        email: str,
        username: str,
        password: str,
        confirm_password: str,
        full_name: Optional[str] = None,
        phone_number: Optional[str] = None,
        tz: str = "UTC",
        language: str = "en",
        is_tenant: Optional[bool] = None,
    ) -> User:
        """Register a new user."""
        self._passwords.validate_and_confirm(password, confirm_password)

        if await self._users.get_by_email(email):
            raise DuplicateEntityError("User", "email")
        if await self._users.get_by_username(username):
            raise DuplicateEntityError("User", "username")

        hash_result = self._passwords.hash_password(password)

        user = User(
            email=email,
            username=username,
            password_hash=hash_result.hashed,
            password_salt=hash_result.salt,
            hash_rounds=hash_result.rounds,
            full_name=full_name,
            phone_number=phone_number,
            timezone=tz,
            language=language,
            is_tenant=is_tenant,
            is_active=True,
            is_verified=False,
        )
        await self._users.create(user)

        from app.core.exceptions import EntityNotFoundError
        try:
            await self._roles.assign_role(user.id, "USER")
        except EntityNotFoundError:
            logger.warning("Default USER role not found, skipping role assignment.")

        await self._users.commit()
        logger.info("User registered: %s (id=%d)", email, user.id)
        return user

    # ── Login ──

    async def login(
        self,
        email: str,
        password: str,
        device_info: Optional[dict] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> LoginResponse:
        """Authenticate a user and return tokens."""
        user = await self._users.get_by_email(email)
        if not user or not user.password_hash or not user.password_salt:
            raise InvalidCredentialsError()

        if not user.is_active:
            raise UserInactiveError()

        if not self._passwords.verify_password(password, user.password_hash, user.password_salt):
            raise InvalidCredentialsError()

        # Resolve tenant_id if not cached on user row
        tenant_id = user.tenant_id_cached
        if not tenant_id and self._tenants:
            tenant_id = await self._tenants.resolve_and_cache_tenant_id(
                user.id, bool(user.is_tenant),
            )
            if tenant_id:
                user.tenant_id_cached = tenant_id
                logger.info("Cached tenant_id=%s for user %d", tenant_id, user.id)

        roles = await self._roles.get_user_roles(user.id)
        permission_ids = await self._roles.get_user_permission_ids_cached(user.id)

        access_token = self._tokens.create_access_token(
            user_id=user.id,
            tenant_id=tenant_id,
            permission_ids=permission_ids,
            roles=roles,
        )
        refresh_token, token_id = self._tokens.create_refresh_token(
            user_id=user.id,
            tenant_id=tenant_id,
            roles=roles,
        )

        await self._sessions.create_session(
            user_id=user.id,
            access_token=access_token,
            refresh_token=refresh_token,
            token_id=token_id,
            device_info=device_info,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        await self._users.update_last_login(user)
        await self._users.commit()

        logger.info("User logged in: %s (id=%d)", email, user.id)
        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
        )

    # ── Refresh ──

    async def refresh_token(self, refresh_token_str: str) -> TokenRefreshResponse:
        """Validate a refresh token and issue a new access token."""
        try:
            payload = self._tokens.validate_token(refresh_token_str)
        except TokenExpiredError:
            raise
        except TokenInvalidError:
            raise

        if payload.token_type != "refresh":
            raise TokenInvalidError("Not a refresh token.")

        if payload.token_id:
            is_active = await self._sessions.is_refresh_token_active(payload.token_id)
            if not is_active:
                raise TokenRevokedError()

        user = await self._users.get_by_id(int(payload.sub))
        if not user or not user.is_active:
            raise UserInactiveError()

        # Resolve tenant_id if not cached
        tenant_id = user.tenant_id_cached
        if not tenant_id and self._tenants:
            tenant_id = await self._tenants.resolve_and_cache_tenant_id(
                user.id, bool(user.is_tenant),
            )
            if tenant_id:
                user.tenant_id_cached = tenant_id
                await self._users.commit()

        roles = await self._roles.get_user_roles(user.id)
        permission_ids = await self._roles.get_user_permission_ids_cached(user.id)

        access_token = self._tokens.create_access_token(
            user_id=user.id,
            tenant_id=tenant_id,
            permission_ids=permission_ids,
            roles=roles,
        )

        return TokenRefreshResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
        )

    # ── Logout ──

    async def logout(
        self,
        user_id: int,
        refresh_token_str: Optional[str] = None,
    ) -> None:
        """Invalidate the user's session."""
        if refresh_token_str:
            session = await self._sessions.get_session_by_refresh_token(refresh_token_str)
            if session:
                await self._sessions.invalidate_session(session)
        await self._sessions.commit()
        logger.info("User logged out: id=%d", user_id)

    # ── Change password ──

    async def change_password(
        self,
        user: User,
        current_password: str,
        new_password: str,
        confirm_password: str,
    ) -> None:
        """Change the user's password."""
        self._passwords.validate_and_confirm(new_password, confirm_password)

        if not self._passwords.verify_password(current_password, user.password_hash, user.password_salt):
            raise InvalidCredentialsError("Current password is incorrect.")

        hash_result = self._passwords.hash_password(new_password)
        await self._users.update_password(user, hash_result.hashed, hash_result.salt, hash_result.rounds)
        await self._users.commit()
        logger.info("Password changed for user id=%d", user.id)
