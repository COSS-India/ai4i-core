"""
JWT-based API key creation, revocation, and validation.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.config import settings
from app.core.exceptions import EntityNotFoundError
from app.models.api_key import APIKey
from app.repositories.api_key_repository import APIKeyRepository
from app.services.cache_service import CacheService
from app.services.token_service import TokenService

logger = logging.getLogger(__name__)


class APIKeyService:
    def __init__(
        self,
        api_key_repo: APIKeyRepository,
        token_service: TokenService,
        cache_service: CacheService,
    ) -> None:
        self._repo = api_key_repo
        self._tokens = token_service
        self._cache = cache_service

    async def create_api_key(
        self,
        user_id: int,
        key_name: str,
        permissions: list[str],
        tenant_id: Optional[str] = None,
        expires_days: Optional[int] = None,
    ) -> tuple[str, APIKey]:
        """
        Create a JWT-based API key.
        Returns (full_jwt_string, api_key_record).
        The JWT is shown once and never stored.
        """
        token_id = str(uuid.uuid4())
        days = expires_days or settings.api_key_expire_days
        expires_delta = timedelta(days=days)

        # Create the JWT
        jwt_token = self._tokens.create_api_key_token(
            user_id=user_id,
            token_id=token_id,
            tenant_id=tenant_id,
            permission_ids=[],  # Permission IDs resolved at validation time
            expires_delta=expires_delta,
        )

        # Store only the token_id in PostgreSQL
        api_key = APIKey(
            user_id=user_id,
            key_name=key_name,
            token_id=token_id,
            permissions=permissions,
            is_active=True,
            is_revoked=False,
            status="active",
            expires_at=datetime.now(timezone.utc) + expires_delta,
        )
        await self._repo.create(api_key)

        # Cache token_id in Redis
        ttl = int(expires_delta.total_seconds())
        await self._cache.store_api_key_token(token_id, ttl, metadata={
            "user_id": user_id,
            "key_name": key_name,
            "permissions": permissions,
        })

        await self._repo.commit()
        logger.info("API key created: name=%s, token_id=%s, user=%d", key_name, token_id, user_id)

        return jwt_token, api_key

    async def revoke_api_key(self, key_id: int, user_id: Optional[int] = None) -> None:
        """Revoke an API key — removes from Redis for instant invalidation."""
        api_key = await self._repo.get_by_id(key_id)
        if not api_key:
            raise EntityNotFoundError("API key")

        # Ownership check (non-admins)
        if user_id is not None and api_key.user_id != user_id:
            raise EntityNotFoundError("API key")

        await self._repo.revoke(api_key)
        await self._cache.revoke_api_key_token(api_key.token_id)
        await self._repo.commit()
        logger.info("API key revoked: id=%d, token_id=%s", key_id, api_key.token_id)

    async def validate_api_key_jwt(
        self,
        jwt_token: str,
        required_service: Optional[str] = None,
        required_action: Optional[str] = None,
        expected_user_id: Optional[int] = None,
    ) -> dict:
        """
        Validate an API key JWT with full service/action/ownership enforcement.

        Returns dict with: valid, user_id, permissions, token_id, message.
        """
        # 1. Decode and verify JWT signature + expiry
        from app.core.exceptions import TokenExpiredError, TokenInvalidError
        try:
            payload = self._tokens.validate_token(jwt_token)
        except TokenExpiredError:
            return {"valid": False, "message": "API key token has expired."}
        except TokenInvalidError as exc:
            logger.debug("API key JWT validation failed: %s", exc.message)
            return {"valid": False, "message": "Invalid API key token."}
        except ValueError as exc:
            logger.debug("API key JWT value error: %s", exc)
            return {"valid": False, "message": "Invalid API key token."}

        if payload.token_type != "api_key":
            return {"valid": False, "message": "Not an API key token."}

        if not payload.token_id:
            return {"valid": False, "message": "API key missing token_id."}

        # 2. Revocation check: Redis first, DB fallback
        db_key = await self._check_revocation(payload.token_id)
        if db_key is None:
            return {"valid": False, "message": "API key has been revoked."}

        permissions = db_key.permissions or []

        # 3. Ownership enforcement (when caller provides user_id)
        if expected_user_id is not None and db_key.user_id != expected_user_id:
            return {
                "valid": False,
                "message": "API key does not belong to the specified user.",
            }

        # 4. Service + action permission check
        if required_service and required_action:
            required_permission = f"{required_service}.{required_action}"
            # Also accept inference permission for read actions (v1 compat)
            inference_permission = f"{required_service}.inference"

            has_permission = (
                required_permission in permissions
                or (required_action == "read" and inference_permission in permissions)
            )

            if not has_permission:
                service_perms = [p for p in permissions if p.startswith(f"{required_service}.")]
                if not service_perms:
                    return {
                        "valid": False,
                        "message": f"API key does not have access to {required_service.upper()} service.",
                        "user_id": db_key.user_id,
                        "permissions": permissions,
                    }
                return {
                    "valid": False,
                    "message": f"API key missing '{required_permission}' permission. "
                               f"Available: {', '.join(service_perms)}",
                    "user_id": db_key.user_id,
                    "permissions": permissions,
                }

        # 5. Update last_used
        await self._repo.update_last_used(db_key)
        await self._repo.commit()

        return {
            "valid": True,
            "user_id": db_key.user_id,
            "permissions": permissions,
            "token_id": payload.token_id,
            "tenant_id": payload.tenant_id,
        }

    async def _check_revocation(self, token_id: str) -> Optional[APIKey]:
        """
        Check if an API key token_id is valid.
        Checks Redis first, falls back to DB if Redis key expired/evicted.
        Returns the APIKey record if valid, None if revoked.
        """
        is_cached = await self._cache.is_api_key_valid(token_id)

        if is_cached:
            # Fast path: present in Redis = not revoked
            db_key = await self._repo.get_by_token_id(token_id)
            return db_key if (db_key and db_key.is_active and not db_key.is_revoked) else None

        # Slow path: not in Redis — could be evicted or actually revoked
        db_key = await self._repo.get_by_token_id(token_id)
        if not db_key or db_key.is_revoked or not db_key.is_active:
            return None

        # Check expiry
        if db_key.expires_at and db_key.expires_at < datetime.now(timezone.utc):
            return None

        # Re-cache if found active in DB (Redis had evicted it)
        if db_key.expires_at:
            remaining = (db_key.expires_at - datetime.now(timezone.utc)).total_seconds()
            if remaining > 0:
                await self._cache.store_api_key_token(token_id, int(remaining))

        return db_key

    async def list_by_user(self, user_id: int) -> list[APIKey]:
        return await self._repo.list_by_user(user_id)

    async def list_all_with_users(self, offset: int = 0, limit: int = 100) -> list:
        return await self._repo.list_all_with_users(offset, limit)

    async def get_by_id(self, key_id: int) -> Optional[APIKey]:
        return await self._repo.get_by_id(key_id)

    async def update_key(self, key_id: int, data: dict, user_id: Optional[int] = None) -> APIKey:
        api_key = await self._repo.get_by_id(key_id)
        if not api_key:
            raise EntityNotFoundError("API key")
        if user_id is not None and api_key.user_id != user_id:
            raise EntityNotFoundError("API key")
        await self._repo.update(api_key, data)
        await self._repo.commit()
        return api_key
