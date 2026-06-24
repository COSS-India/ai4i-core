"""
Core authentication business logic: register, login, refresh, logout,
change-password, and email-activation (provision + set-password).
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from ai4i_core.email import EmailClient
from fastapi import BackgroundTasks

from app.core.config import settings
from app.core.constants import TokenType
from app.models.role_name import RoleName
from app.core.exceptions import (
    AuthorizationError,
    DuplicateEntityError,
    EntityNotFoundError,
    InvalidCredentialsError,
    TokenExpiredError,
    TokenInvalidError,
    TokenRevokedError,
    UserInactiveError,
    ValidationError,
)
from app.models.credentials import UserCredentials
from app.models.tenant import Tenant, TenantStatus
from app.services.tenant_lifecycle import (
    assert_valid_tenant_status_transition,
    sync_tenant_users_for_status,
)
from app.models.user import User, CreationType
from app.models.verification import TokenVerification
from app.repositories.credentials_repository import CredentialsRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.repositories.verification_repository import VerificationRepository
from app.schemas.auth import LoginResponse, TokenRefreshResponse
from app.services.auth_email_templates import (
    render_password_changed,
    render_password_reset,
    render_setup_link,
    render_verify_email,
    render_welcome,
)
from app.core.security import password_manager
from app.services.email_helpers import (
    enqueue_email,
    issue_session,
    persist_token_verification,
    reissue_setup_token,
    resolve_tenant_id,
    setup_token_expires_at,
)
from app.services.api_key_service import APIKeyService
from app.services.role_service import RoleService
from app.services.token_service import TokenService
from app.utils.username import allocate_unique_username, derive_username_from_email

logger = logging.getLogger(__name__)


def assert_tenant_allows_authentication(tenant: Optional[Tenant]) -> None:
    """Reject sign-in when the tenant is not ACTIVE."""
    if tenant is None:
        return

    if tenant.status == TenantStatus.ACTIVE:
        return

    if tenant.status == TenantStatus.PENDING:
        raise AuthorizationError(
            message="Tenant status is pending. Complete tenant activation before signing in.",
            code="TENANT_INACTIVE",
        )
    if tenant.status == TenantStatus.SUSPENDED:
        raise AuthorizationError(
            message="Your account access has been suspended. Please contact support.",
            code="TENANT_SUSPENDED",
        )
    raise AuthorizationError(
        message="Tenant is deactivated.",
        code="TENANT_INACTIVE",
    )


def assert_tenant_allows_onboarding(tenant: Optional[Tenant]) -> None:
    """Allow email verification and password setup while tenant is PENDING or ACTIVE."""
    if tenant is None:
        return

    if tenant.status in (TenantStatus.PENDING, TenantStatus.ACTIVE):
        return

    if tenant.status == TenantStatus.SUSPENDED:
        raise AuthorizationError(
            message="Your account access has been suspended. Please contact support.",
            code="TENANT_SUSPENDED",
        )
    raise AuthorizationError(
        message="Tenant is deactivated.",
        code="TENANT_INACTIVE",
    )


class AuthService:
    def __init__(
        self,
        user_repo: UserRepository,
        role_service: RoleService,
        token_service: TokenService,
        credentials_repo: CredentialsRepository,
        refresh_token_repo: RefreshTokenRepository,
        verification_repo: VerificationRepository,
        tenant_repo: TenantRepository,
        email_client: EmailClient,
        api_key_service: Optional[APIKeyService] = None,
    ) -> None:
        self._users = user_repo
        self._roles = role_service
        self._tokens = token_service
        self._credentials = credentials_repo
        self._refresh_tokens = refresh_token_repo
        self._verifications = verification_repo
        self._tenants = tenant_repo
        self._email = email_client
        self._api_keys = api_key_service

    def _validate_token_of_type(self, token: str, expected_type: str):
        """Validate a JWT and assert its type. Raises TokenExpiredError / TokenInvalidError on failure."""
        payload = self._tokens.validate_token(token)
        if payload.token_type != expected_type:
            raise TokenInvalidError(f"Expected a '{expected_type}' token.")
        return payload

    async def _resolve_verified_token(
        self, token: str, token_type: str, link_name: str
    ) -> tuple[TokenVerification, User]:
        """Validate token and resolve both token record and user.

        Args:
            token: The JWT token string
            token_type: Expected token type (VERIFY, RESET, SETUP, etc.)
            link_name: User-friendly name for error messages (e.g., "verification link")

        Returns:
            Tuple of (TokenVerification record, User)

        Raises:
            TokenInvalidError: If token validation fails, record not found, already used, or user not found
        """
        payload = self._validate_token_of_type(token, token_type)

        token_obj = await self._verifications.get_by_token(token)
        if not token_obj:
            raise TokenInvalidError(f"Invalid {link_name}.")
        if not token_obj.is_active:
            raise TokenInvalidError(f"{link_name.capitalize()} has already been used.")

        user = await self._users.get_by_id(UUID(payload.sub))
        if not user:
            raise TokenInvalidError(f"Invalid {link_name}.")

        return token_obj, user

    # ── Register (direct portal signup) ──

    async def register(
        self,
        email: str,
        password: str,
        confirm_password: str,
        full_name: Optional[str] = None,
        phone_number: Optional[str] = None,
        tz: str = "UTC",
        tenant_id: Optional[int | str] = None,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> User:
        """Create an inactive user with credentials and issue a verify-email
        token. The user CANNOT log in until they click the verification link
        and the account is activated via verify_email_token().

        Direct portal sign-up follows the password-at-signup + email-verify
        pattern: the user types the password they want, but the account stays
        inactive until they prove ownership of the email address.
        """
        password_manager.validate_and_confirm(password, confirm_password)

        # Normalize email to lowercase for consistent storage and lookup
        email = email.lower().strip()

        if await self._users.email_exists(email):
            raise DuplicateEntityError("User", "email")

        username = await allocate_unique_username(
            self._users.list_usernames_in_collision_family,
            derive_username_from_email(email),
        )

        parsed_tenant_id = await resolve_tenant_id(tenant_id, self._tenants)

        user = User(
            email=email,
            username=username,
            full_name=full_name,
            phone_number=phone_number,
            timezone=tz,
            tenant_id=parsed_tenant_id,
            is_active=False,
            # ORM enum currently supports only "default" and "google".
            creation_type=CreationType.DEFAULT,
        )
        await self._users.create(user)

        hash_result = await password_manager.hash_password_async(password)
        creds = UserCredentials(
            user_id=user.id,
            password_hash=hash_result.hashed,
            password_salt=hash_result.salt,
        )
        await self._credentials.create(creds)

        try:
            await self._roles.assign_role(user.id, RoleName.USER)
        except EntityNotFoundError:
            logger.warning("Default USER role not found, skipping role assignment.")

        user_id_str = str(user.id)
        verify_token = self._tokens.create_verify_token(user_id=user_id_str, email=email)
        await persist_token_verification(
            self._verifications,
            verify_token,
            user.id,
            setup_token_expires_at(),
        )

        await self._users.commit()
        logger.info("User registered (pending verification): id=%s", user.id)
        enqueue_email(background_tasks, self._email, lambda: render_verify_email(user, verify_token))
        return user

    # ── Email verification (consumes verify_token) ──

    async def verify_email_token(
        self,
        token: str,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> None:
        """Consume a verify token and activate the user (/auth/register flow).

        Tenant admins use setup-password links instead; they must not rely on
        verify-email for onboarding.
        """
        token_obj, user = await self._resolve_verified_token(token, TokenType.VERIFY, "verification link")
        await self._assert_user_tenant_onboarding(user)

        user.is_active = True
        await self._verifications.deactivate(token_obj)
        await self._users.commit()
        logger.info("Email verified for user id=%s", user.id)
        enqueue_email(background_tasks, self._email, lambda: render_welcome(user))

    # ── Email verification: Resend ──

    async def resend_verification(
        self,
        email: str,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> None:
        """Invalidate any active verify tokens for this user and issue a new one.

        Anti-enumeration: this method ALWAYS returns successfully (consistent
        with /auth/forgot-password and /auth/resend-setup-link). Unknown emails
        are a silent no-op. Only sends email to users who registered via
        /auth/register (have credentials, inactive). Tenant contact admins must
        use /auth/resend-setup-link instead.
        """
        user = await self._users.get_by_email(email)
        if not user:
            return  # silent no-op (anti-enumeration)
        if user.is_active:
            return  # already verified: silent no-op

        existing_creds = await self._credentials.get_by_user_id(user.id)
        if not existing_creds:
            return  # passwordless onboarding — use /auth/resend-setup-link

        user_id_str = str(user.id)
        await self._verifications.deactivate_all_for_user(user_id_str, token_type=TokenType.VERIFY)

        verify_token = self._tokens.create_verify_token(user_id=user_id_str, email=email)
        await persist_token_verification(
            self._verifications,
            verify_token,
            user.id,
            setup_token_expires_at(),
        )
        await self._users.commit()

        logger.info("Verification link resent for user id=%s", user.id)
        enqueue_email(background_tasks, self._email, lambda: render_verify_email(user, verify_token))

    # ── Password reset (forgot-password flow) ──

    async def request_password_reset(
        self,
        email: str,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> None:
        """Issue a reset token + email if the user exists and is active.

        Anti-enumeration: this method ALWAYS returns successfully. The route
        handler should also always return the same generic message regardless
        of whether the email matched a real, active user. We only enqueue the
        actual email when the user is eligible (active, has credentials).
        """
        user = await self._users.get_by_email(email)
        if not user or not user.is_active:
            return  # silent no-op (anti-enumeration)

        existing_creds = await self._credentials.get_by_user_id(user.id)
        if not existing_creds:
            return  # silent no-op — passwordless account, can't reset

        user_id_str = str(user.id)
        await self._verifications.deactivate_all_for_user(user_id_str, token_type=TokenType.RESET)

        reset_token = self._tokens.create_reset_token(user_id=user_id_str, email=email)
        reset_expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.reset_token_expire_minutes)
        await persist_token_verification(
            self._verifications,
            reset_token,
            user.id,
            reset_expires_at,
        )
        await self._users.commit()

        logger.info("Password reset link issued for user id=%s", user.id)
        enqueue_email(background_tasks, self._email, lambda: render_password_reset(user, reset_token))

    async def reset_password_with_token(
        self,
        token: str,
        new_password: str,
        confirm_password: str,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> None:
        """Consume a RESET token and replace the user's password. Token is
        single-use; refresh tokens are revoked so other sessions are signed
        out per security spec. Sends a password_changed notification."""
        password_manager.validate_and_confirm(new_password, confirm_password)

        token_obj, user = await self._resolve_verified_token(token, TokenType.RESET, "reset link")

        creds = await self._credentials.get_by_user_id(user.id)
        if not creds:
            # Should be impossible (request_password_reset only issues for users
            # with creds), but guard regardless.
            raise TokenInvalidError("Invalid reset link.")

        hash_result = await password_manager.hash_password_async(new_password)
        await self._credentials.update_password(creds, hash_result.hashed, hash_result.salt)
        await self._verifications.deactivate(token_obj)
        # Sign out all other sessions per security spec.
        await self._refresh_tokens.delete_by_user_id(user.id)
        await self._credentials.commit()
        logger.info("Password reset for user id=%s; refresh tokens revoked", user.id)
        enqueue_email(background_tasks, self._email, lambda: render_password_changed(user))

    # ── Login ──

    async def _assert_user_tenant_active(self, user: User) -> None:
        if user.tenant_id is None:
            return
        # Per-user tenant access flag. Cleared (is_tenant_active=False) when the
        # tenant is suspended/deactivated — either tenant-wide via
        # sync_tenant_users_for_status, or for a single user via
        # PATCH /tenants/{tenant_id}/users/{user_id}/status. The latter does not
        # change tenant.status, so it must be enforced here independently of the
        # tenant-status check below. None/True (legacy default) means allowed.
        if user.is_tenant_active is False:
            raise AuthorizationError(
                message="Your account access has been suspended. Please contact support.",
                code="TENANT_SUSPENDED",
            )
        tenant = await self._tenants.get_by_id(user.tenant_id)
        assert_tenant_allows_authentication(tenant)

    async def _assert_user_tenant_onboarding(self, user: User) -> None:
        if user.tenant_id is None:
            return
        tenant = await self._tenants.get_by_id(user.tenant_id)
        assert_tenant_allows_onboarding(tenant)

    async def _is_pending_tenant_contact_admin(self, user: User) -> bool:
        """True when user is the provisioned admin for a PENDING tenant."""
        if user.tenant_id is None:
            return False
        tenant = await self._tenants.get_by_id(user.tenant_id)
        if not tenant or tenant.status != TenantStatus.PENDING:
            return False
        return tenant.email.lower().strip() == user.email.lower().strip()

    async def _activate_pending_tenant_for_contact_admin(self, user: User) -> None:
        """After contact admin sets password, move tenant PENDING → ACTIVE."""
        if not await self._is_pending_tenant_contact_admin(user):
            return
        tenant = await self._tenants.get_by_id(user.tenant_id)
        if tenant is None:
            raise EntityNotFoundError(f"Tenant {user.tenant_id}")
        await self._tenants.update(tenant, {"status": TenantStatus.ACTIVE})
        await sync_tenant_users_for_status(
            self._users, tenant.id, TenantStatus.ACTIVE, updated_by=user.id
        )
        if self._api_keys is not None:
            await self._api_keys.refresh_keys_cache_for_tenant(tenant.id)
        logger.info(
            "Tenant %s activated after contact admin set password (user id=%s)",
            tenant.id,
            user.id,
        )

    async def login(self, email: str, password: str) -> LoginResponse:
        """Authenticate a user and return access + refresh tokens."""
        user = await self._users.get_by_email(email)
        if not user:
            raise InvalidCredentialsError()

        if not user.is_active:
            raise UserInactiveError()

        await self._assert_user_tenant_active(user)

        creds = await self._credentials.get_by_user_id(user.id)
        if not creds or not creds.password_hash or not creds.password_salt:
            raise InvalidCredentialsError()

        if not await password_manager.verify_password_async(password, creds.password_hash, creds.password_salt):
            raise InvalidCredentialsError()

        login_response = await issue_session(
            user,
            self._roles,
            self._tokens,
            self._refresh_tokens,
            self._users,
        )

        logger.info("User logged in: id=%s, tenant=%s", user.id, user.tenant_id)
        return login_response

    # ── Refresh ──

    async def refresh_token(self, refresh_token_str: str) -> TokenRefreshResponse:
        """Validate a refresh token via DB and issue a new access token.

        Optimized: Uses lightweight is_active check instead of full user fetch.
        Tenant ID comes from the original JWT payload (already validated by gateway).
        """
        payload = self._validate_token_of_type(refresh_token_str, TokenType.REFRESH)

        db_token = await self._refresh_tokens.get_by_token(refresh_token_str)
        if not db_token:
            raise TokenRevokedError()

        user_id = UUID(payload.sub)
        if not await self._users.is_active(user_id):
            raise UserInactiveError()

        user = await self._users.get_by_id(user_id)
        if user:
            await self._assert_user_tenant_active(user)

        # Tenant ID is already in the payload (set at login/token creation)
        tenant_id = payload.tenant_id
        permission_ids = await self._roles.get_user_permission_ids(user_id)

        access_token = self._tokens.create_access_token(
            user_id=str(user_id),
            tenant_id=tenant_id,
            permission_ids=permission_ids,
        )

        return TokenRefreshResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
        )

    # ── Logout ──

    async def logout(self, user_id: UUID) -> None:
        """Delete the user's refresh token from DB."""
        await self._refresh_tokens.delete_by_user_id(user_id)
        await self._refresh_tokens.commit()
        logger.info("User logged out: id=%s", user_id)

    # ── Change password ──

    async def change_password(
        self,
        user: User,
        current_password: str,
        new_password: str,
        confirm_password: str,
        current_refresh_token: Optional[str] = None,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> None:
        password_manager.validate_and_confirm(new_password, confirm_password)

        creds = await self._credentials.get_by_user_id(user.id)
        if not creds:
            raise InvalidCredentialsError("No credentials found for user.")

        if not await password_manager.verify_password_async(current_password, creds.password_hash, creds.password_salt):
            raise InvalidCredentialsError("Current password is incorrect.")

        if await password_manager.verify_password_async(new_password, creds.password_hash, creds.password_salt):
            raise ValidationError(
                message="New password cannot be the same as the current password.",
                code="SAME_PASSWORD",
            )

        # Preserve current session's refresh token (client-provided or fetch from DB)
        token_to_preserve = current_refresh_token
        if not token_to_preserve:
            existing = await self._refresh_tokens.get_by_user_id(user.id)
            token_to_preserve = existing.refresh_token if existing else None

        hash_result = await password_manager.hash_password_async(new_password)
        await self._credentials.update_password(creds, hash_result.hashed, hash_result.salt)
        await self._refresh_tokens.delete_by_user_id(user.id)
        if token_to_preserve:
            await self._refresh_tokens.upsert(user.id, token_to_preserve)
        await self._credentials.commit()
        await self._refresh_tokens.commit()
        logger.info("Password changed for user id=%s; refresh tokens revoked except current session", user.id)
        enqueue_email(background_tasks, self._email, lambda: render_password_changed(user))

    # ── Email Activation: Set Password ──

    async def set_password_with_token(
        self,
        token: str,
        new_password: str,
        confirm_password: str,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> None:
        """Consume a setup token, create credentials, activate the user.

        Tenant contact admins: tenant moves PENDING → ACTIVE here, then welcome email.
        """
        password_manager.validate_and_confirm(new_password, confirm_password)

        token_obj, user = await self._resolve_verified_token(token, TokenType.SETUP, "setup link")
        await self._assert_user_tenant_onboarding(user)

        hash_result = await password_manager.hash_password_async(new_password)
        creds = UserCredentials(
            user_id=user.id,
            password_hash=hash_result.hashed,
            password_salt=hash_result.salt,
        )
        await self._credentials.create(creds)

        was_inactive = not user.is_active
        user.is_active = True
        await self._verifications.deactivate(token_obj)
        await self._activate_pending_tenant_for_contact_admin(user)
        await self._users.commit()
        if self._api_keys is not None:
            await self._api_keys.refresh_keys_cache_for_user(user)
        logger.info("Password set via activation link for user id=%s", user.id)
        if was_inactive:
            enqueue_email(background_tasks, self._email, lambda: render_welcome(user))

    # ── Email Activation: Token Status ──

    async def get_setup_token_status(self, token: str) -> dict:
        """Check whether a setup token is valid, expired, or already used."""
        try:
            payload = self._tokens.validate_token(token)
        except TokenExpiredError:
            return {"valid": False, "status": "expired", "message": "Setup link has expired. Request a new one."}
        except TokenInvalidError:
            return {"valid": False, "status": "invalid", "message": "Setup link is invalid."}

        if payload.token_type != TokenType.SETUP:
            return {"valid": False, "status": "invalid", "message": "Setup link is invalid."}

        token_obj = await self._verifications.get_by_token(token)
        if not token_obj:
            return {"valid": False, "status": "invalid", "message": "Setup link is invalid."}
        if not token_obj.is_active:
            return {"valid": False, "status": "used", "message": "Setup link has already been used."}

        return {"valid": True, "status": "valid", "message": "Setup link is valid."}

    # ── Email Activation: Resend ──

    async def check_email_exists(self, email: str) -> bool:
        return await self._users.email_exists(email.lower().strip())

    async def resend_setup_link(
        self,
        email: str,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> None:
        """Invalidate old setup tokens and issue a new welcome/set-password email.

        Anti-enumeration: always returns successfully. Only sends email to users
        who have NOT yet set a password (no credentials). Works for tenant contact
        admins while the tenant is still PENDING.

        Token issuance is delegated to ``reissue_setup_token`` so the SETUP
        token-type scoping and credentials-already-set guard stay in lockstep
        with the tenant email-update flow (see ``TenantService.update_tenant``).
        """
        user = await self._users.get_by_email(email)
        if not user:
            return  # anti-enumeration: silent no-op

        setup_token = await reissue_setup_token(
            user,
            credentials_repo=self._credentials,
            verifications_repo=self._verifications,
            token_service=self._tokens,
            background_tasks=background_tasks,
        )
        if setup_token is None:
            return  # helper guarded — credentials set or no bg tasks

        await self._users.commit()
        logger.info("Setup link resent for user id=%s", user.id)
        # Enqueue AFTER commit so a commit failure can't leak an email whose
        # token has been rolled back.
        enqueue_email(
            background_tasks, self._email,
            lambda: render_setup_link(user, setup_token),
        )
