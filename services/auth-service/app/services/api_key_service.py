"""
API key creation, revocation, and validation.

Keys are 32-char hex strings generated via secrets.token_hex(16).
The raw hex key is stored directly in Postgres (api_key column = primary key).
Redis is the sole validation path at inference time — zero DB calls per request.
Revocation immediately deletes the Redis entry; subsequent lookups find nothing.
"""

import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from app.core.config import settings
from app.core.exceptions import EntityNotFoundError, InvalidAPIKeyError, ValidationError
from app.models.api_key import APIKey
from app.repositories.api_key_repository import APIKeyRepository
from app.services.cache_service import CacheService

logger = logging.getLogger(__name__)

_HEX_KEY_RE = re.compile(r"[0-9a-f]{32}")


class APIKeyService:
    def __init__(
        self,
        api_key_repo: APIKeyRepository,
        cache_service: CacheService,
    ) -> None:
        self._repo = api_key_repo
        self._cache = cache_service

    @staticmethod
    def generate_api_key() -> str:
        return secrets.token_hex(16)

    @staticmethod
    def _is_api_key(token: str) -> bool:
        return bool(_HEX_KEY_RE.fullmatch(token))

    async def create_api_key(
        self,
        user_id: UUID,
        key_name: str,
        permissions: list[int],
        expires_days: Optional[int] = None,
    ) -> tuple[str, APIKey]:
        """
        Generate a hex API key, persist to DB, cache in Redis.
        Returns (raw_hex_key, api_key_record). Raw key is shown once and never stored again.
        """
        permission_ids = list(dict.fromkeys(permissions or []))

        id_to_name = await self._repo.get_permission_names_by_ids(permission_ids)
        missing_ids = [pid for pid in permission_ids if pid not in id_to_name]
        if missing_ids:
            raise ValidationError(
                message="Invalid permission IDs in request.",
                code="INVALID_PERMISSION_IDS",
                errors=[f"Unknown permission_id={pid}" for pid in missing_ids],
            )

        raw_key = self.generate_api_key()
        days = expires_days or settings.api_key_expire_days
        expires_at = datetime.now(timezone.utc) + timedelta(days=days)
        ttl = int(timedelta(days=days).total_seconds())

        api_key = APIKey(
            api_key=raw_key,
            user_id=user_id,
            key_name=key_name,
            permissions=permission_ids,
            expires_at=expires_at,
            created_by=str(user_id),
            updated_by=str(user_id),
        )
        await self._repo.create(api_key)

        await self._cache.set_api_key_cache(
            raw_key,
            ttl,
            {"api_key": raw_key, "permissions": permission_ids, "user_id": str(user_id)},
        )

        await self._repo.commit()
        logger.info("API key created: name=%s user=%s", key_name, user_id)
        return raw_key, api_key

    async def validate_api_key(
        self,
        token: str,
        required_service: Optional[str] = None,
        required_action: Optional[str] = None,
    ) -> dict:
        """
        Validate a hex API key. Redis-only — zero DB calls.
        Raises InvalidAPIKeyError when the key is absent from Redis (revoked or never existed).
        """
        if not self._is_api_key(token):
            return {"valid": False, "message": "Invalid API key format."}

        cached = await self._cache.get_api_key_cache(token)
        if cached is None:
            raise InvalidAPIKeyError()

        permission_ids: list[int] = cached.get("permissions", [])

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
                return {
                    "valid": False,
                    "message": f"API key missing '{required_permission}' permission.",
                    "user_id": cached.get("user_id"),
                    "permissions": permission_names,
                }

        return {
            "valid": True,
            "user_id": cached.get("user_id"),
            "permission_ids": permission_ids,
        }

    async def revoke_api_key(
        self,
        api_key_value: str,
        user_id: Optional[UUID] = None,
    ) -> None:
        db_key = await self._repo.get_by_api_key(api_key_value)
        if not db_key:
            raise EntityNotFoundError("API key")
        if user_id is not None and db_key.user_id != user_id:
            raise EntityNotFoundError("API key")

        await self._repo.revoke(db_key)
        await self._cache.delete_api_key_cache(api_key_value)
        await self._repo.commit()
        logger.info("API key revoked: api_key=%s", api_key_value)

    async def update_key(
        self,
        api_key_value: str,
        data: dict,
        user_id: Optional[UUID] = None,
    ) -> APIKey:
        db_key = await self._repo.get_by_api_key(api_key_value)
        if not db_key:
            raise EntityNotFoundError("API key")
        if user_id is not None and db_key.user_id != user_id:
            raise EntityNotFoundError("API key")

        expires_days = data.pop("expires_days", None)
        if expires_days is not None:
            data["expires_at"] = datetime.now(timezone.utc) + timedelta(days=expires_days)
        if user_id is not None:
            data["updated_by"] = str(user_id)

        await self._repo.update(db_key, data)
        await self._repo.refresh(db_key)

        # Refresh Redis with updated data
        updated_permissions = data.get("permissions") or db_key.permissions or []
        expires_at = db_key.expires_at
        if expires_at:
            ttl = max(0, int((expires_at - datetime.now(timezone.utc)).total_seconds()))
        else:
            ttl = settings.api_key_expire_days * 86400
        if ttl > 0:
            await self._cache.set_api_key_cache(
                api_key_value,
                ttl,
                {"api_key": api_key_value, "permissions": updated_permissions, "user_id": str(db_key.user_id)},
            )

        await self._repo.commit()
        return db_key

    async def list_by_user(self, user_id: UUID) -> list[APIKey]:
        return await self._repo.list_by_user(user_id)

    async def list_all_with_users(self, offset: int = 0, limit: int = 100) -> list:
        return await self._repo.list_all_with_users(offset, limit)

    async def get_by_api_key(self, api_key_value: str) -> Optional[APIKey]:
        return await self._repo.get_by_api_key(api_key_value)
