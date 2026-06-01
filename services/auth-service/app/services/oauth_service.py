"""
OAuth2 service — handles Google login flow.

Ported from auth-service-v2 (Sept 2025) and adapted for the consolidated
auth-service:
  * users.id is UUID (was Integer)
  * Token issuance uses TokenService (no `roles=` arg; permission_ids only)
  * Server-side sessions are gone — refresh-token is persisted via
    RefreshTokenRepository, mirroring the standard /auth/login path
  * No separate oauth_providers table — User.creation_type = GOOGLE marks
    OAuth-created accounts; existing users are matched by email (Google's
    userinfo carries the email so the provider's user-id is not needed
    for lookup). If we ever need to call Google APIs as the user we'll
    re-introduce a table for access/refresh-token storage at that time.
  * Welcome email sent for first-time OAuth users (not for re-logins)

GitHub support was intentionally dropped in this port — re-add a config
block + `fetch_user_info` branch + an entry in `_PROVIDER_METADATA` if
needed.
"""

import logging
from typing import Any, Optional

import httpx
from ai4icore_core.email import EmailClient
from fastapi import BackgroundTasks

from app.core.config import settings
from app.services.email_helpers import enqueue_email, issue_session, resolve_tenant_id
from app.core.exceptions import AuthenticationRequiredError, EntityNotFoundError
from app.core.messages import (
    OAUTH_PROVIDER_UNKNOWN,
    OAUTH_PROVIDER_UNREACHABLE,
    OAUTH_CODE_EXCHANGE_FAILED,
    OAUTH_USERINFO_FETCH_FAILED,
    OAUTH_EMAIL_UNVERIFIED,
    LOG_DEFAULT_ROLE_MISSING,
    LOG_OAUTH_USER_CREATED,
    LOG_OAUTH_LOGIN,
    LOG_ERROR_OAUTH_TOKEN_EXCHANGE,
    LOG_ERROR_OAUTH_TOKEN_EXCHANGE_STATUS,
    LOG_ERROR_OAUTH_USERINFO,
)
from app.models.role_name import RoleName
from app.models.user import CreationType, User
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_email_templates import render_welcome
from app.services.role_service import RoleService
from app.services.token_service import TokenService

logger = logging.getLogger(__name__)


# Provider configs are static metadata. Client_id / client_secret come from
# settings at lookup time so a runtime config reload would pick them up.
_PROVIDER_METADATA = {
    "google": {
        "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://www.googleapis.com/oauth2/v2/userinfo",
        "scope": ["openid", "email", "profile"],
    },
}


class OAuthService:
    def __init__(
        self,
        user_repo: UserRepository,
        refresh_token_repo: RefreshTokenRepository,
        tenant_repo: TenantRepository,
        role_service: RoleService,
        token_service: TokenService,
        email_client: EmailClient,
    ) -> None:
        self._users = user_repo
        self._refresh_tokens = refresh_token_repo
        self._tenants = tenant_repo
        self._roles = role_service
        self._tokens = token_service
        self._email = email_client

    # ── Provider config ──

    def get_provider_config(self, provider: str) -> dict:
        """Return OAuth provider configuration; raise if unknown."""
        if provider == "google":
            return {
                "provider": "google",
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                **_PROVIDER_METADATA["google"],
            }
        raise EntityNotFoundError(OAUTH_PROVIDER_UNKNOWN)

    def list_configured_providers(self) -> list[dict]:
        """Return configs only for providers that have credentials wired up.

        Walks the canonical ``_PROVIDER_METADATA`` here so the route layer
        doesn't need its own provider list — single source of truth.
        """
        configured = []
        for name in _PROVIDER_METADATA:
            config = self.get_provider_config(name)
            if config.get("client_id"):
                configured.append(config)
        return configured

    # ── Provider HTTP ──

    async def exchange_code_for_tokens(
        self, provider: str, code: str, redirect_uri: str
    ) -> dict:
        """Exchange authorization code for OAuth tokens."""
        config = self.get_provider_config(provider)
        try:
            async with httpx.AsyncClient(timeout=settings.oauth_http_timeout_seconds) as client:
                resp = await client.post(
                    config["token_url"],
                    data={
                        "client_id": config["client_id"],
                        "client_secret": config["client_secret"],
                        "code": code,
                        "redirect_uri": redirect_uri,
                        "grant_type": "authorization_code",
                    },
                    headers={"Accept": "application/json"},
                )
        except httpx.RequestError as exc:
            logger.error(LOG_ERROR_OAUTH_TOKEN_EXCHANGE, provider, exc)
            raise AuthenticationRequiredError(OAUTH_PROVIDER_UNREACHABLE) from exc
        if resp.status_code != 200:
            # Provider error body may include client_secret in some configs
            # (e.g. echoed redirect_uri). Don't leak the body — log status only.
            logger.error(LOG_ERROR_OAUTH_TOKEN_EXCHANGE_STATUS, resp.status_code)
            raise AuthenticationRequiredError(OAUTH_CODE_EXCHANGE_FAILED)

        token_data = resp.json()
        if not token_data.get("access_token"):
            raise AuthenticationRequiredError(OAUTH_PROVIDER_UNREACHABLE)
        return token_data

    async def fetch_user_info(self, provider: str, access_token: str) -> dict[str, Any]:
        """Fetch user profile from OAuth provider. ``get_provider_config``
        already validates the provider, so only Google reaches this path
        today; the response shape mapping below assumes Google's userinfo."""
        config = self.get_provider_config(provider)
        try:
            async with httpx.AsyncClient(timeout=settings.oauth_http_timeout_seconds) as client:
                resp = await client.get(
                    config["userinfo_url"],
                    headers={"Authorization": f"Bearer {access_token}"},
                )
        except httpx.RequestError as exc:
            logger.error(LOG_ERROR_OAUTH_USERINFO, provider, exc)
            raise AuthenticationRequiredError(OAUTH_PROVIDER_UNREACHABLE) from exc
        if resp.status_code != 200:
            raise AuthenticationRequiredError(OAUTH_USERINFO_FETCH_FAILED)

        userinfo = resp.json()
        return {
            "email": userinfo.get("email"),
            "full_name": userinfo.get("name"),
            "avatar_url": userinfo.get("picture"),
            "email_verified": userinfo.get("verified_email", userinfo.get("email_verified", False)),
        }

    # ── Account resolution ──

    async def _find_or_create_user(
        self,
        email: str,
        full_name: Optional[str],
        avatar_url: Optional[str],
        provider_name: str,
    ) -> tuple[User, bool]:
        """Resolve an existing local user by email, or create a new one
        marked with CreationType.<provider>.

        Returns (user, was_created). ``was_created`` lets the caller decide
        whether to enqueue the welcome email.
        """
        existing_user = await self._users.get_by_email(email)
        if existing_user:
            return existing_user, False

        # Username derived from email local part with numeric suffix to avoid
        # collisions (admins/seeded users may already hold the bare local part).
        username = email.split("@")[0]
        base_username = username
        counter = 1
        while await self._users.get_by_username(username):
            username = f"{base_username}{counter}"
            counter += 1

        # Map provider to CreationType. Known providers get their own enum
        # value; unknown providers fall back to DEFAULT until an OTHERS
        # variant is added to the creation_type_enum in the DB.
        try:
            creation_type = CreationType(provider_name.lower())
        except ValueError:
            creation_type = CreationType.DEFAULT

        tenant_id = await resolve_tenant_id(None, self._tenants)

        user = User(
            email=email,
            username=username,
            full_name=full_name,
            avatar_url=avatar_url,
            is_active=True,  # OAuth identity = email already verified by provider
            creation_type=creation_type,
            tenant_id=tenant_id,
        )
        await self._users.create(user)

        try:
            await self._roles.assign_role(user.id, RoleName.USER)
        except EntityNotFoundError:
            logger.warning(LOG_DEFAULT_ROLE_MISSING)

        logger.info(LOG_OAUTH_USER_CREATED, email, provider_name, user.id)
        return user, True

    async def complete_oauth_login(
        self,
        provider: str,
        code: str,
        redirect_uri: str,
        background_tasks: Optional[BackgroundTasks] = None,
    ) -> dict:
        """End-to-end callback flow:
        exchange code → fetch user → resolve/create → issue JWT pair.

        Returns the same shape as a normal /auth/login response so the FE
        callback page doesn't need branching.
        """
        token_data = await self.exchange_code_for_tokens(provider, code, redirect_uri)
        access_token = token_data["access_token"]

        userinfo = await self.fetch_user_info(provider, access_token)
        email = userinfo.get("email")
        if not email:
            raise AuthenticationRequiredError(OAUTH_USERINFO_FETCH_FAILED)
        if not userinfo.get("email_verified"):
            raise AuthenticationRequiredError(OAUTH_EMAIL_UNVERIFIED)

        user, was_created = await self._find_or_create_user(
            email=email,
            full_name=userinfo.get("full_name"),
            avatar_url=userinfo.get("avatar_url"),
            provider_name=provider,
        )

        # Issue JWT pair via the same path used by /auth/login.
        login_response = await issue_session(
            user,
            self._roles,
            self._tokens,
            self._refresh_tokens,
            self._users,
        )

        if was_created:
            enqueue_email(background_tasks, self._email, lambda: render_welcome(user))

        logger.info(LOG_OAUTH_LOGIN, email, provider, user.id)
        return login_response.model_dump()
