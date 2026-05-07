"""
Core authentication business logic: register, login, refresh, logout,
change-password, and email-activation (provision + set-password).
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional
from uuid import UUID

from ai4icore_email import EmailClient, EmailMessage
from fastapi import BackgroundTasks

from app.core.config import settings
from app.core.constants import TokenType
from app.models.role_name import RoleName
from app.core.exceptions import (
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
from app.services.role_service import RoleService
from app.services.token_service import TokenService

logger = logging.getLogger(__name__)


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
    ) -> None:
        self._users = user_repo
        self._roles = role_service
        self._tokens = token_service
        self._credentials = credentials_repo
        self._refresh_tokens = refresh_token_repo
        self._verifications = verification_repo
        self._tenants = tenant_repo
        self._email = email_client

    def _enqueue_email(
        self,
        background_tasks: Optional[BackgroundTasks],
        factory: Callable[[], EmailMessage],
    ) -> None:
        """Render and enqueue a send_safe call.

        ``factory`` is a zero-arg callable that returns an EmailMessage. Render
        is wrapped in try/except so a template/URL bug never 5xx's a request
        whose DB commit already succeeded — orphan-row prevention. Render
        failures are logged at ERROR for ops to catch via metrics.

        Silent no-op when no BackgroundTasks available (e.g. tests calling the
        service directly without a request).
        """
        if background_tasks is None:
            return
        try:
            message = factory()
        except Exception as exc:
            logger.error(
                "email render failed: error=%s",
                exc.__class__.__name__,
            )
            return
        background_tasks.add_task(self._email.send_safe, message)

    def _setup_token_expires_at(self) -> datetime:
        return datetime.now(timezone.utc) + timedelta(hours=settings.setup_token_expire_hours)

    def _validate_token_of_type(self, token: str, expected_type: str):
        """Validate a JWT and assert its type. Raises TokenExpiredError / TokenInvalidError on failure."""
        payload = self._tokens.validate_token(token)
        if payload.token_type != expected_type:
            raise TokenInvalidError(f"Expected a '{expected_type}' token.")
        return payload

    async def _resolve_tenant_id(self, explicit: Optional[int | str]) -> Optional[int]:
        """Honor an explicit tenant_id, otherwise fall back to the default tenant."""
        if explicit is not None:
            try:
                return int(explicit)
            except (TypeError, ValueError) as exc:
                raise ValidationError(
                    message="Invalid tenant_id.",
                    code="INVALID_TENANT_ID",
                    errors=[f"tenant_id must be an integer, got: {explicit!r}"],
                ) from exc
        default = await self._tenants.get_by_organisation(settings.default_tenant_org)
        if default is None:
            logger.warning(
                "Default tenant '%s' not found; user will be created without a tenant_id.",
                settings.default_tenant_org,
            )
            return None
        return default.id

    # ── Register (direct portal signup) ──

    async def register(
        self,
        email: str,
        username: str,
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

        if await self._users.get_by_email(email):
            raise DuplicateEntityError("User", "email")
        if await self._users.get_by_username(username):
            raise DuplicateEntityError("User", "username")

        parsed_tenant_id = await self._resolve_tenant_id(tenant_id)

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

        hash_result = password_manager.hash_password(password)
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
        verify_token = self._tokens.create_verify_token(
            user_id=user_id_str,
            email=email,
            expires_delta=timedelta(hours=settings.setup_token_expire_hours),
        )
        token_obj = TokenVerification(
            token=verify_token,
            is_active=True,
            expires_at=self._setup_token_expires_at(),
            created_by=user.id,
        )
        await self._verifications.create(token_obj)

        await self._users.commit()
        logger.info("User registered (pending verification): %s (id=%s)", email, user.id)
        self._enqueue_email(background_tasks, lambda: render_verify_email(user, verify_token))
        return user

    # ── Email verification (consumes verify_token) ──

    async def verify_email_token(
        self,
        token: str,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> None:
        """Consume a verify token and flip the user to active. The user already
        has credentials (set during register), so this is a pure activation —
        no password change. Sends a welcome email after activation.
        """
        payload = self._validate_token_of_type(token, TokenType.VERIFY)

        token_obj = await self._verifications.get_by_token(token)
        if not token_obj:
            raise TokenInvalidError("Invalid verification link.")
        if not token_obj.is_active:
            raise TokenInvalidError("Verification link has already been used.")

        user = await self._users.get_by_id(UUID(payload.sub))
        if not user:
            raise TokenInvalidError("Invalid verification link.")

        user.is_active = True
        await self._verifications.deactivate(token_obj)
        await self._users.commit()
        logger.info("Email verified for user id=%s", user.id)
        self._enqueue_email(background_tasks, lambda: render_welcome(user))

    # ── Email verification: Resend ──

    async def resend_verification(
        self,
        email: str,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> str:
        """Invalidate any active verify tokens for this user and issue a new one.

        Eligible only for users who registered via /auth/register but never
        clicked the verify link — i.e. user has credentials AND is_active=False.
        Distinct from resend_setup_link, which targets users with NO credentials.
        """
        user = await self._users.get_by_email(email)
        if not user:
            raise EntityNotFoundError("User")

        if user.is_active:
            raise ValidationError(
                message="Email already verified.",
                code="ALREADY_VERIFIED",
                errors=["This account is already active. Sign in instead."],
            )

        existing_creds = await self._credentials.get_by_user_id(user.id)
        if not existing_creds:
            # No credentials → this user came from the setup-link flow, not the
            # verify-email flow. Direct them to the right resend endpoint.
            raise ValidationError(
                message="This account has not set a password yet.",
                code="NO_CREDENTIALS",
                errors=["Use /auth/resend-setup-link to receive a setup link."],
            )

        user_id_str = str(user.id)
        await self._verifications.deactivate_all_for_user(user_id_str)

        verify_token = self._tokens.create_verify_token(
            user_id=user_id_str,
            email=email,
            expires_delta=timedelta(hours=settings.setup_token_expire_hours),
        )
        token_obj = TokenVerification(
            token=verify_token,
            is_active=True,
            expires_at=self._setup_token_expires_at(),
            created_by=user.id,
        )
        await self._verifications.create(token_obj)
        await self._users.commit()

        logger.info("Verification link resent for user id=%s", user.id)
        self._enqueue_email(background_tasks, lambda: render_verify_email(user, verify_token))
        return verify_token

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
        await self._verifications.deactivate_all_for_user(user_id_str)

        reset_token = self._tokens.create_reset_token(
            user_id=user_id_str,
            email=email,
            expires_delta=timedelta(minutes=settings.reset_token_expire_minutes),
        )
        token_obj = TokenVerification(
            token=reset_token,
            is_active=True,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.reset_token_expire_minutes),
            created_by=user.id,
        )
        await self._verifications.create(token_obj)
        await self._users.commit()

        logger.info("Password reset link issued for user id=%s", user.id)
        self._enqueue_email(background_tasks, lambda: render_password_reset(user, reset_token))

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

        payload = self._validate_token_of_type(token, TokenType.RESET)

        token_obj = await self._verifications.get_by_token(token)
        if not token_obj:
            raise TokenInvalidError("Invalid reset link.")
        if not token_obj.is_active:
            raise TokenInvalidError("Reset link has already been used.")

        user = await self._users.get_by_id(UUID(payload.sub))
        if not user:
            raise TokenInvalidError("Invalid reset link.")

        creds = await self._credentials.get_by_user_id(user.id)
        if not creds:
            # Should be impossible (request_password_reset only issues for users
            # with creds), but guard regardless.
            raise TokenInvalidError("Invalid reset link.")

        hash_result = password_manager.hash_password(new_password)
        await self._credentials.update_password(creds, hash_result.hashed, hash_result.salt)
        await self._verifications.deactivate(token_obj)
        # Sign out all other sessions per security spec.
        await self._refresh_tokens.delete_by_user_id(user.id)
        await self._credentials.commit()
        logger.info("Password reset for user id=%s; refresh tokens revoked", user.id)
        self._enqueue_email(background_tasks, lambda: render_password_changed(user))

    # ── Login ──

    async def login(self, email: str, password: str, background_tasks: Optional[BackgroundTasks] = None) -> LoginResponse:
        """Authenticate a user and return access + refresh tokens.

        Last login update is queued as background task — not critical for response.
        """
        user = await self._users.get_by_email(email)
        if not user:
            raise InvalidCredentialsError()

        if not user.is_active:
            raise UserInactiveError()

        creds = await self._credentials.get_by_user_id(user.id)
        if not creds or not creds.password_hash or not creds.password_salt:
            raise InvalidCredentialsError()

        if not password_manager.verify_password(password, creds.password_hash, creds.password_salt):
            raise InvalidCredentialsError()

        tenant_id = str(user.tenant_id) if user.tenant_id else None

        permission_ids = await self._roles.get_user_permission_ids(user.id)

        access_token = self._tokens.create_access_token(
            user_id=str(user.id),
            tenant_id=tenant_id,
            permission_ids=permission_ids,
        )
        refresh_token = self._tokens.create_refresh_token(
            user_id=str(user.id),
            tenant_id=tenant_id,
        )

        await self._refresh_tokens.upsert(user.id, refresh_token)
        await self._users.commit()

        # Queue last_login update as background task (not critical for immediate response)
        if background_tasks:
            async def update_login_time():
                user.last_login = datetime.now(timezone.utc)
                await self._users.commit()
            background_tasks.add_task(update_login_time)

        logger.info("User logged in: %s (id=%s)", email, user.id)
        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.access_token_expire_minutes * 60,
        )

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
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> None:
        password_manager.validate_and_confirm(new_password, confirm_password)

        creds = await self._credentials.get_by_user_id(user.id)
        if not creds:
            raise InvalidCredentialsError("No credentials found for user.")

        if not password_manager.verify_password(current_password, creds.password_hash, creds.password_salt):
            raise InvalidCredentialsError("Current password is incorrect.")

        hash_result = password_manager.hash_password(new_password)
        await self._credentials.update_password(creds, hash_result.hashed, hash_result.salt)
        await self._credentials.commit()
        logger.info("Password changed for user id=%s", user.id)
        self._enqueue_email(background_tasks, lambda: render_password_changed(user))

    # ── Email Activation: Provision User ──

    async def provision_user(
        self,
        email: str,
        username: str,
        full_name: Optional[str] = None,
        phone_number: Optional[str] = None,
        tenant_id: Optional[int | str] = None,
        creation_type: str = "default",
        role_name: str = RoleName.USER,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> tuple[str, str]:
        """
        Create an inactive user without credentials and generate a setup token.
        Used by the tenant-user provisioning route during tenant user onboarding.
        Returns (user_id_str, setup_token).

        ``role_name`` decides which role is assigned. Default ``RoleName.USER``
        for regular tenant members; pass ``RoleName.TENANT_ADMIN`` when
        provisioning the first admin user of a new tenant.
        """
        if await self._users.get_by_email(email):
            raise DuplicateEntityError("User", "email")
        if await self._users.get_by_username(username):
            raise DuplicateEntityError("User", "username")

        parsed_tenant_id = await self._resolve_tenant_id(tenant_id)
        # `CreationType` in the ORM currently supports only "default" and "google".
        # Treat any unknown creation_type input as DEFAULT.
        creation = CreationType(creation_type) if creation_type in CreationType._value2member_map_ else CreationType.DEFAULT

        user = User(
            email=email,
            username=username,
            full_name=full_name,
            phone_number=phone_number,
            tenant_id=parsed_tenant_id,
            is_active=False,
            creation_type=creation,
        )
        await self._users.create(user)

        try:
            await self._roles.assign_role(user.id, role_name)
        except EntityNotFoundError:
            logger.warning("Role %r not found, skipping role assignment.", role_name)

        user_id_str = str(user.id)
        setup_token = self._tokens.create_setup_token(
            user_id=user_id_str,
            email=email,
            expires_delta=timedelta(hours=settings.setup_token_expire_hours),
        )

        token_obj = TokenVerification(
            token=setup_token,
            is_active=True,
            expires_at=self._setup_token_expires_at(),
            created_by=user.id,
        )
        await self._verifications.create(token_obj)
        await self._users.commit()

        logger.info("User provisioned (no credentials): %s (id=%s)", email, user.id)
        self._enqueue_email(background_tasks, lambda: render_setup_link(user, setup_token))
        return user_id_str, setup_token

    # ── Email Activation: Set Password ──

    async def set_password_with_token(
        self,
        token: str,
        new_password: str,
        confirm_password: str,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> None:
        """Consume a setup token, create credentials, activate the user, send
        welcome email."""
        password_manager.validate_and_confirm(new_password, confirm_password)

        payload = self._validate_token_of_type(token, TokenType.SETUP)

        token_obj = await self._verifications.get_by_token(token)
        if not token_obj:
            raise TokenInvalidError("Invalid setup link.")
        if not token_obj.is_active:
            raise TokenInvalidError("Setup link has already been used.")

        user = await self._users.get_by_id(UUID(payload.sub))
        if not user:
            raise TokenInvalidError("Invalid setup link.")

        hash_result = password_manager.hash_password(new_password)
        creds = UserCredentials(
            user_id=user.id,
            password_hash=hash_result.hashed,
            password_salt=hash_result.salt,
        )
        await self._credentials.create(creds)

        user.is_active = True
        await self._verifications.deactivate(token_obj)
        await self._users.commit()
        logger.info("Password set via activation link for user id=%s", user.id)
        self._enqueue_email(background_tasks, lambda: render_welcome(user))

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

    async def resend_setup_link(
        self,
        email: str,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> str:
        """Invalidate old setup tokens and issue a new one."""
        user = await self._users.get_by_email(email)
        if not user:
            raise EntityNotFoundError("User")

        existing_creds = await self._credentials.get_by_user_id(user.id)
        if existing_creds:
            raise ValidationError(
                message="User has already set a password.",
                code="ALREADY_ACTIVATED",
                errors=["Cannot resend setup link for an already-activated account."],
            )

        user_id_str = str(user.id)
        await self._verifications.deactivate_all_for_user(user_id_str)

        setup_token = self._tokens.create_setup_token(
            user_id=user_id_str,
            email=email,
            expires_delta=timedelta(hours=settings.setup_token_expire_hours),
        )
        token_obj = TokenVerification(
            token=setup_token,
            is_active=True,
            expires_at=self._setup_token_expires_at(),
            created_by=user.id,
        )
        await self._verifications.create(token_obj)
        await self._users.commit()

        logger.info("Setup link resent for user id=%s", user.id)
        self._enqueue_email(background_tasks, lambda: render_setup_link(user, setup_token))
        return setup_token
