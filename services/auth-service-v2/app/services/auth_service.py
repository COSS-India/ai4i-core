"""
Core authentication business logic: register, login, refresh, logout.
"""

import logging
from typing import Optional

import httpx
from ai4icore_env import app_env

from app.core.config import settings
from app.core.exceptions import (
    DuplicateEntityError,
    AuthorizationError,
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

from app.services.tenant_service import TenantService, is_suspended_or_deactivated

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
        tenant_service=TenantService,
    ) -> None:
        self._users = user_repo
        self._roles = role_service
        self._tokens = token_service
        self._passwords = password_service
        self._sessions = session_service
        self._cache = cache_service
        self._tenants = tenant_service

    def _format_tenant_inactive_message(self) -> str:
        return "Tenant access is restricted. Contact your administrator."

    def _format_user_inactive_message(self, user_status: str) -> str:
        # Keep spelling exactly as requested (including "cotact").
        return f"User is {user_status.lower()} , please contact your admin"

    async def _enforce_login_tenant_status(self, user: User) -> None:
        """
        Block login when:
        - tenant is SUSPENDED/DEACTIVATED (tenant admin + tenant users blocked)
        - tenant is ACTIVE but tenant user is SUSPENDED/DEACTIVATED
        """
        tenant_id = user.tenant_id_cached
        if not tenant_id:
            # Only tenant users/admins should have a tenant_id; normal users are expected to bypass enforcement.
            if getattr(user, "is_tenant", None) is not None:
                logger.warning(
                    "Tenant status enforcement skipped: tenant_id missing (tenant_service_enabled=%s) for user_id=%s is_tenant=%s",
                    bool(self._tenants),
                    user.id,
                    bool(getattr(user, "is_tenant", None)),
                )
            return

        if not self._tenants:
            logger.warning(
                "Tenant status enforcement skipped: tenant service not configured for user_id=%s tenant_id=%s is_tenant=%s",
                user.id,
                tenant_id,
                bool(getattr(user, "is_tenant", None)),
            )
            return

        logger.debug(
            "Enforcing tenant status for login (tenant_id=%s user_id=%s is_tenant=%s)",
            tenant_id,
            user.id,
            bool(getattr(user, "is_tenant", None)),
        )
        tenant_status = await self._tenants.get_tenant_status(tenant_id)
        tenant_status_attempted_fallback = False
        resolved_tenant_id = None

        if tenant_status is None:
            # tenant_id_cached can be stale across auth DB updates; attempt to re-resolve once.
            tenant_status_attempted_fallback = True
            is_tenant_flag = bool(getattr(user, "is_tenant", None))
            resolved_tenant_id = await self._tenants.resolve_and_cache_tenant_id(user.id, is_tenant_flag)
            if resolved_tenant_id and resolved_tenant_id != tenant_id:
                logger.debug(
                    "Tenant status retry: tenant_id_cached=%s resolved_tenant_id=%s (user_id=%s is_tenant=%s)",
                    tenant_id,
                    resolved_tenant_id,
                    user.id,
                    is_tenant_flag,
                )
                user.tenant_id_cached = resolved_tenant_id
                tenant_id = resolved_tenant_id
                tenant_status = await self._tenants.get_tenant_status(tenant_id)

            # As a last resort, look up status directly by user_id + is_tenant.
            if tenant_status is None:
                tenant_status = await self._tenants.get_tenant_status_by_user_id(
                    user.id, is_tenant_flag
                )

            if tenant_status is None:
                debug_info = {}
                try:
                    debug_info = await self._tenants.debug_tenant_mappings(
                        tenant_id, user.id, is_tenant_flag
                    )
                except Exception:
                    debug_info = {"debug_error": "failed to fetch tenant mapping debug info"}
                logger.warning(
                    "Tenant status lookup returned None (tenant_id=%s tenant_id_resolved=%s user_id=%s is_tenant=%s fallback_attempted=%s debug=%s) — login will not be blocked by tenant status",
                    tenant_id,
                    resolved_tenant_id,
                    user.id,
                    is_tenant_flag,
                    tenant_status_attempted_fallback,
                    debug_info,
                )
        if is_suspended_or_deactivated(tenant_status):
            logger.info(
                "Blocking login: tenant suspended/deactivated (tenant_id=%s status=%s user_id=%s)",
                tenant_id,
                tenant_status,
                user.id,
            )
            raise AuthorizationError(
                message=self._format_tenant_inactive_message(),
                code="TENANT_INACTIVE",
            )

        # Only tenant users have TenantUser.status; tenant admin only needs tenant.status.
        if user.is_tenant:
            return

        tenant_user_status = await self._tenants.get_tenant_user_status(tenant_id, user.id)
        if user.is_tenant is False and tenant_user_status is None:
            logger.warning(
                "Tenant-user status lookup returned None (tenant_id=%s user_id=%s) — login will not be blocked by tenant-user status",
                tenant_id,
                user.id,
            )
        if is_suspended_or_deactivated(tenant_user_status):
            logger.info(
                "Blocking login: tenant user suspended/deactivated (tenant_id=%s tenant_user_status=%s user_id=%s)",
                tenant_id,
                tenant_user_status,
                user.id,
            )
            raise AuthorizationError(
                message=self._format_user_inactive_message(str(tenant_user_status)),
                code="TENANT_USER_INACTIVE",
            )

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
        tenant_id: Optional[str] = None,
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
            tenant_id_cached=tenant_id,
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
        logger.debug(
            "AuthService.login tenant enforcement precheck (tenant_id=%s tenant_service_enabled=%s user_id=%s is_tenant=%s)",
            tenant_id,
            bool(self._tenants),
            user.id,
            bool(user.is_tenant),
        )
        
        await self._enforce_login_tenant_status(user)
        # tenant-status enforcement may have updated user.tenant_id_cached
        tenant_id = user.tenant_id_cached

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

        await self._enforce_login_tenant_status(user)
        # tenant-status enforcement may have updated user.tenant_id_cached
        tenant_id = user.tenant_id_cached

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
