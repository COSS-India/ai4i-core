"""
API key creation, revocation, and validation.

The api_key.api_key column stores the token_id UUID used as the JWT
token_id claim. The full JWT is returned to the caller once and never
stored. Revocation is by deactivating the DB row and evicting the
Redis cache entry.
"""

import logging
import uuid
from datetime import timedelta
from typing import Optional
from uuid import UUID

from app.core.config import settings
from app.core.exceptions import EntityNotFoundError, ValidationError
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
        user_id: UUID,
        key_name: str,
        permissions: list[int],
        tenant_id: Optional[str] = None,
        expires_days: Optional[int] = None,
    ) -> tuple[str, APIKey]:
        """
        Create a JWT-based API key.
        The token_id UUID is stored in api_key.api_key for revocation lookups.
        Returns (full_jwt_string, api_key_record). JWT is shown once, never stored.
        """
        token_id = str(uuid.uuid4())
        days = expires_days or settings.api_key_expire_days
        expires_delta = timedelta(days=days)
        permission_ids = list(dict.fromkeys(permissions or []))

        id_to_name = await self._repo.get_permission_names_by_ids(permission_ids)
        missing_ids = [pid for pid in permission_ids if pid not in id_to_name]
        if missing_ids:
            raise ValidationError(
                message="Invalid permission IDs in request.",
                code="INVALID_PERMISSION_IDS",
                errors=[f"Unknown permission_id={pid}" for pid in missing_ids],
            )

        jwt_token = self._tokens.create_api_key_token(
            user_id=str(user_id),
            token_id=token_id,
            tenant_id=tenant_id,
            permission_ids=permission_ids,
            expires_delta=expires_delta,
        )

        api_key = APIKey(
            user_id=user_id,
            key_name=key_name,
            api_key=token_id,
            permissions={"permission": permission_ids},
            is_active=True,
        )
        await self._repo.create(api_key)

        ttl = int(expires_delta.total_seconds())
        await self._cache.store_api_key_token(token_id, ttl, metadata={
            "user_id": str(user_id),
            "key_name": key_name,
            "permission_ids": permission_ids,
        })

        await self._repo.commit()
        logger.info("API key created: name=%s token_id=%s user=%s", key_name, token_id, user_id)
        return jwt_token, api_key

    async def revoke_api_key(self, key_id: int, user_id: Optional[UUID] = None) -> None:
        api_key = await self._repo.get_by_id(key_id)
        if not api_key:
            raise EntityNotFoundError("API key")
        if user_id is not None and api_key.user_id != user_id:
            raise EntityNotFoundError("API key")

        await self._repo.deactivate(api_key)
        await self._cache.revoke_api_key_token(api_key.api_key)
        await self._repo.commit()
        logger.info("API key revoked: id=%d token_id=%s", key_id, api_key.api_key)

    async def validate_api_key_jwt(
        self,
        jwt_token: str,
        required_service: Optional[str] = None,
        required_action: Optional[str] = None,
        expected_user_id: Optional[UUID] = None,
    ) -> dict:
        """
        Validate an API key JWT. Returns dict with: valid, user_id, permissions, token_id, message.
        """
        from app.core.exceptions import TokenExpiredError, TokenInvalidError
        try:
            payload = self._tokens.validate_token(jwt_token)
        except TokenExpiredError:
            return {"valid": False, "message": "API key token has expired."}
        except TokenInvalidError as exc:
            return {"valid": False, "message": "Invalid API key token."}

        if payload.token_type != "api_key":
            return {"valid": False, "message": "Not an API key token."}
        if not payload.token_id:
            return {"valid": False, "message": "API key missing token_id."}

        db_key = await self._check_revocation(payload.token_id)
        if db_key is None:
            return {"valid": False, "message": "API key has been revoked."}

        permission_ids: list[int] = (db_key.permissions or {}).get("permission", [])

        if expected_user_id is not None and db_key.user_id != expected_user_id:
            return {"valid": False, "message": "API key does not belong to the specified user."}

        if required_service and required_action:
            id_to_name = await self._repo.get_permission_names_by_ids(permission_ids)
            permission_names = list(id_to_name.values())
            required_permission = f"{required_service}.{required_action}"
            inference_permission = f"{required_service}.inference"
            has_permission = (
                required_permission in permission_names
                or (required_action == "read" and inference_permission in permission_names)
            )
            if not has_permission:
                service_perms = [p for p in permission_names if p.startswith(f"{required_service}.")]
                if not service_perms:
                    return {
                        "valid": False,
                        "message": f"API key does not have access to {required_service.upper()} service.",
                        "user_id": str(db_key.user_id),
                        "permissions": permission_names,
                    }
                return {
                    "valid": False,
                    "message": f"API key missing '{required_permission}' permission.",
                    "user_id": str(db_key.user_id),
                    "permissions": permission_names,
                }

        return {
            "valid": True,
            "user_id": str(db_key.user_id),
            "permission_ids": permission_ids,
            "token_id": payload.token_id,
            "tenant_id": payload.tenant_id,
        }

    async def _check_revocation(self, token_id: str) -> Optional[APIKey]:
        is_cached = await self._cache.is_api_key_valid(token_id)
        if is_cached:
            db_key = await self._repo.get_by_api_key(token_id)
            return db_key if (db_key and db_key.is_active) else None

        db_key = await self._repo.get_by_api_key(token_id)
        if not db_key or not db_key.is_active:
            return None

        ttl = settings.api_key_expire_days * 86400
        await self._cache.store_api_key_token(token_id, ttl)
        return db_key

    async def list_by_user(self, user_id: UUID) -> list[APIKey]:
        return await self._repo.list_by_user(user_id)

    async def list_all_with_users(self, offset: int = 0, limit: int = 100) -> list:
        return await self._repo.list_all_with_users(offset, limit)

    async def get_by_id(self, key_id: int) -> Optional[APIKey]:
        return await self._repo.get_by_id(key_id)

    async def update_key(self, key_id: int, data: dict, user_id: Optional[UUID] = None) -> APIKey:
        api_key = await self._repo.get_by_id(key_id)
        if not api_key:
            raise EntityNotFoundError("API key")
        if user_id is not None and api_key.user_id != user_id:
            raise EntityNotFoundError("API key")
        await self._repo.update(api_key, data)
        await self._repo.commit()
        return api_key
