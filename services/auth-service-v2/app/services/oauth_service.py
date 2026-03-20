"""
OAuth2 service — handles Google/GitHub login flows.
"""

import logging
import secrets
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.core.exceptions import AuthenticationRequiredError, EntityNotFoundError
from app.models.oauth import OAuthProvider
from app.models.user import User
from app.repositories.oauth_repository import OAuthRepository
from app.repositories.role_repository import RoleRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginResponse
from app.services.cache_service import CacheService
from app.services.session_service import SessionService
from app.services.token_service import TokenService

logger = logging.getLogger(__name__)


class OAuthService:
    def __init__(
        self,
        user_repo: UserRepository,
        oauth_repo: OAuthRepository,
        role_repo: RoleRepository,
        token_service: Optional[TokenService] = None,
        session_service: Optional[SessionService] = None,
        cache_service: Optional[CacheService] = None,
    ) -> None:
        self._users = user_repo
        self._oauth = oauth_repo
        self._roles = role_repo
        self._tokens = token_service
        self._sessions = session_service
        self._cache = cache_service

    def get_provider_config(self, provider: str) -> dict:
        """Return OAuth provider configuration."""
        configs = {
            "google": {
                "provider": "google",
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
                "token_url": "https://oauth2.googleapis.com/token",
                "userinfo_url": "https://www.googleapis.com/oauth2/v2/userinfo",
                "scope": ["openid", "email", "profile"],
            },
            "github": {
                "provider": "github",
                "client_id": settings.github_client_id,
                "client_secret": settings.github_client_secret,
                "authorization_url": "https://github.com/login/oauth/authorize",
                "token_url": "https://github.com/login/oauth/access_token",
                "userinfo_url": "https://api.github.com/user",
                "scope": ["user:email"],
            },
        }
        if provider not in configs:
            raise EntityNotFoundError(f"OAuth provider '{provider}'")
        return configs[provider]

    async def exchange_code_for_tokens(self, provider: str, code: str, redirect_uri: str) -> dict:
        """Exchange authorization code for OAuth tokens."""
        config = self.get_provider_config(provider)
        async with httpx.AsyncClient(timeout=10.0) as client:
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
        if resp.status_code != 200:
            logger.error("OAuth token exchange failed: %s %s", resp.status_code, resp.text)
            raise AuthenticationRequiredError("Failed to exchange authorization code.")

        token_data = resp.json()
        if not token_data.get("access_token"):
            raise AuthenticationRequiredError("No access token received from provider.")
        return token_data

    async def fetch_user_info(self, provider: str, access_token: str) -> dict[str, Any]:
        """Fetch user profile from OAuth provider."""
        config = self.get_provider_config(provider)
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                config["userinfo_url"],
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if resp.status_code != 200:
            raise AuthenticationRequiredError("Failed to fetch user info from provider.")

        userinfo = resp.json()

        if provider == "google":
            return {
                "email": userinfo.get("email"),
                "full_name": userinfo.get("name"),
                "avatar_url": userinfo.get("picture"),
                "provider_user_id": userinfo.get("id") or userinfo.get("email"),
            }
        elif provider == "github":
            email = userinfo.get("email")
            if not email:
                email = await self._fetch_github_primary_email(access_token)
            return {
                "email": email,
                "full_name": userinfo.get("name"),
                "avatar_url": userinfo.get("avatar_url"),
                "provider_user_id": str(userinfo.get("id", "")),
            }
        raise EntityNotFoundError(f"OAuth provider '{provider}'")

    async def _fetch_github_primary_email(self, access_token: str) -> Optional[str]:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.github.com/user/emails",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if resp.status_code == 200:
            for e in resp.json():
                if e.get("primary") and e.get("verified"):
                    return e["email"]
        return None

    async def create_or_link_user(
        self,
        email: str,
        full_name: Optional[str],
        avatar_url: Optional[str],
        provider_name: str,
        provider_user_id: str,
        oauth_tokens: dict[str, Any],
        username: Optional[str] = None,
    ) -> User:
        """Create a new user from OAuth data or link to existing user."""
        existing_oauth = await self._oauth.get_by_provider(provider_name, provider_user_id)
        if existing_oauth:
            await self._oauth.update_tokens(
                existing_oauth, oauth_tokens.get("access_token", ""), oauth_tokens.get("refresh_token"),
            )
            await self._oauth.commit()
            user = await self._users.get_by_id(existing_oauth.user_id)
            if user:
                return user
            raise AuthenticationRequiredError("Linked user not found.")

        existing_user = await self._users.get_by_email(email)
        if existing_user:
            await self._link_oauth(existing_user.id, provider_name, provider_user_id, oauth_tokens)
            return existing_user

        if not username:
            username = email.split("@")[0]
            base_username = username
            counter = 1
            while await self._users.get_by_username(username):
                username = f"{base_username}{counter}"
                counter += 1

        user = User(
            email=email, username=username, password_hash=None,
            full_name=full_name, avatar_url=avatar_url,
            is_verified=True, is_active=True,
        )
        await self._users.create(user)

        role = await self._roles.get_role_by_name("USER")
        if role:
            await self._roles.assign_role(user.id, role.id)

        await self._link_oauth(user.id, provider_name, provider_user_id, oauth_tokens)
        await self._users.commit()
        logger.info("OAuth user created: %s via %s", email, provider_name)
        return user

    async def complete_oauth_login(self, provider: str, code: str, redirect_uri: str) -> dict:
        """
        Full OAuth callback flow: exchange code → fetch user → create/link → issue tokens.
        Returns dict with access_token, refresh_token, user info.
        """
        token_data = await self.exchange_code_for_tokens(provider, code, redirect_uri)
        access_token = token_data["access_token"]

        userinfo = await self.fetch_user_info(provider, access_token)
        email = userinfo.get("email")
        if not email:
            raise AuthenticationRequiredError("Could not retrieve email from OAuth provider.")

        user = await self.create_or_link_user(
            email=email,
            full_name=userinfo.get("full_name"),
            avatar_url=userinfo.get("avatar_url"),
            provider_name=provider,
            provider_user_id=userinfo["provider_user_id"],
            oauth_tokens=token_data,
        )

        # Issue JWT tokens
        roles = await self._roles.get_user_roles(user.id)
        permission_ids = await self._roles.get_user_permission_ids(user.id)

        jwt_access = self._tokens.create_access_token(
            user_id=user.id, tenant_id=user.tenant_id_cached,
            permission_ids=permission_ids, roles=roles,
        )
        jwt_refresh, refresh_token_id = self._tokens.create_refresh_token(
            user_id=user.id, tenant_id=user.tenant_id_cached, roles=roles,
        )

        # Create session
        if self._sessions:
            await self._sessions.create_session(
                user_id=user.id, access_token=jwt_access,
                refresh_token=jwt_refresh, token_id=refresh_token_id,
            )

        # Update last login
        from datetime import datetime, timezone
        user.last_login = datetime.now(timezone.utc)
        await self._users.commit()

        logger.info("OAuth login: %s via %s (user_id=%d)", email, provider, user.id)
        return {
            "access_token": jwt_access,
            "refresh_token": jwt_refresh,
            "token_type": "bearer",
            "expires_in": settings.access_token_expire_minutes * 60,
            "user": {"id": user.id, "email": user.email, "username": user.username, "full_name": user.full_name},
        }

    async def _link_oauth(self, user_id: int, provider_name: str, provider_user_id: str, oauth_tokens: dict) -> None:
        provider = OAuthProvider(
            user_id=user_id, provider_name=provider_name,
            provider_user_id=provider_user_id,
            access_token=oauth_tokens.get("access_token"),
            refresh_token=oauth_tokens.get("refresh_token"),
        )
        await self._oauth.create(provider)
