"""
API key creation, revocation, and validation.

Keys are 32-char hex strings generated via secrets.token_hex(16).
The raw hex key is stored directly in Postgres (api_key column = primary key).
Redis is the sole validation path at inference time — zero DB calls per request.
Revocation immediately deletes the Redis entry; subsequent lookups find nothing.

Tenant/user access changes only evict or refresh Redis. ``api_key.is_active`` is for
explicit revoke only; ``user.is_tenant_active`` / tenant status gate auth via cache refresh.
"""

import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from ai4i_core.ppu import get_inference_types

from app.core.config import settings
from app.core.exceptions import AuthorizationError, EntityNotFoundError, InvalidAPIKeyError, ValidationError
from app.models.api_key import APIKey
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User
from app.repositories.api_key_repository import APIKeyRepository
from app.repositories.tenant_repository import TenantRepository
from app.repositories.user_repository import UserRepository
from app.services.cache_service import CacheService

logger = logging.getLogger(__name__)

_HEX_KEY_RE = re.compile(r"[0-9a-f]{32}")
_USERS_PAGE_SIZE = 500


class APIKeyService:
    def __init__(
        self,
        api_key_repo: Optional[APIKeyRepository],
        cache_service: CacheService,
        user_repo: Optional[UserRepository] = None,
        tenant_repo: Optional[TenantRepository] = None,
    ) -> None:
        self._repo = api_key_repo
        self._cache = cache_service
        self._users = user_repo
        self._tenants = tenant_repo

    @staticmethod
    def user_may_use_api_keys(user: User, tenant: Optional[Tenant]) -> bool:
        """True when the user and tenant allow API key authentication."""
        if user.is_delete:
            return False
        if not user.is_active:
            return False
        if user.is_tenant_active is False:
            return False
        if tenant is None:
            return True
        return tenant.status == TenantStatus.ACTIVE

    @staticmethod
    def effective_is_active(
        api_key: APIKey, user: User, tenant: Optional[Tenant]
    ) -> bool:
        """Runtime validity: owner-enabled, not expired, user/tenant allow access."""
        return bool(
            api_key.is_active
            and not api_key.is_expired()
            and APIKeyService.user_may_use_api_keys(user, tenant)
        )

    @staticmethod
    def generate_api_key() -> str:
        return secrets.token_hex(16)

    @staticmethod
    def _is_api_key(token: str) -> bool:
        return bool(_HEX_KEY_RE.fullmatch(token))

    async def _validate_permission_ids(self, permission_ids: list[int]) -> None:
        """Raise ValidationError if any permission IDs do not exist in the DB."""
        id_to_name = await self._repo.get_permission_names_by_ids(permission_ids)
        missing_ids = [pid for pid in permission_ids if pid not in id_to_name]
        if missing_ids:
            raise ValidationError(
                message="Invalid permission IDs in request.",
                code="INVALID_PERMISSION_IDS",
                errors=[f"Unknown permission_id={pid}" for pid in missing_ids],
            )

    async def _refresh_redis_cache(
        self, db_key: APIKey, tenant_id: Optional[str]
    ) -> None:
        expires_at = db_key.expires_at
        if expires_at:
            ttl = max(0, int((expires_at - datetime.now(timezone.utc)).total_seconds()))
        else:
            ttl = int(timedelta(days=settings.api_key_expire_days).total_seconds())
        if ttl <= 0:
            return
        # Preserve PPU exhaustion flags from the existing hash so a cache
        # refresh doesn't unblock a tenant whose budget/quota is actually gone.
        existing = await self._cache.get_api_key_cache(db_key.api_key)
        budget_exhausted = (existing or {}).get("budget-exhausted", "0")
        preserved_quota = {
            k: v
            for k, v in (existing or {}).items()
            if k.startswith("quota-") and v == "1"
        }
        await self._cache.set_api_key_cache(
            db_key.api_key,
            ttl,
            {
                "api_key": db_key.api_key,
                "permissions": db_key.permissions or [],
                "user_id": str(db_key.user_id),
                "tenant_id": tenant_id,
                "tier_id": "",
                "budget-exhausted": budget_exhausted,
                **{f"quota-{entry['name']}": "0" for entry in get_inference_types()},
                **preserved_quota,
            },
        )

    async def evict_keys_for_user(self, user_id: UUID) -> None:
        """Remove Redis entries for all keys owned by ``user_id``. No DB writes."""
        if self._repo is None:
            return
        for key in await self._repo.list_by_user(user_id):
            await self._cache.delete_api_key_cache(key.api_key)

    async def evict_keys_for_tenant(self, tenant_id: int) -> None:
        """Evict Redis cache for all tenant users' keys. No DB writes."""
        if self._repo is None or self._users is None:
            logger.warning(
                "evict_keys_for_tenant skipped: missing repositories (tenant_id=%s)",
                tenant_id,
            )
            return
        offset = 0
        while True:
            users = await self._users.list_by_tenant(
                tenant_id, offset=offset, limit=_USERS_PAGE_SIZE
            )
            if not users:
                break
            for user in users:
                await self.evict_keys_for_user(user.id)
            if len(users) < _USERS_PAGE_SIZE:
                break
            offset += _USERS_PAGE_SIZE

    async def refresh_keys_cache_for_user(
        self,
        user: User,
        tenant: Optional[Tenant] = None,
    ) -> None:
        """Repopulate Redis for keys that remain valid for the user's access state."""
        if self._repo is None:
            return
        if tenant is None and user.tenant_id is not None and self._tenants is not None:
            tenant = await self._tenants.get_by_id(user.tenant_id)
        if not self.user_may_use_api_keys(user, tenant):
            await self.evict_keys_for_user(user.id)
            return
        tenant_id_str = str(user.tenant_id) if user.tenant_id else None
        for key in await self._repo.list_by_user(user.id):
            if key.is_active and not key.is_expired():
                await self._refresh_redis_cache(key, tenant_id_str)

    async def refresh_keys_cache_for_tenant(self, tenant_id: int) -> None:
        """Repopulate Redis for all eligible keys in the tenant."""
        if self._repo is None or self._users is None or self._tenants is None:
            logger.warning(
                "refresh_keys_cache_for_tenant skipped: missing repositories (tenant_id=%s)",
                tenant_id,
            )
            return
        tenant = await self._tenants.get_by_id(tenant_id)
        if not tenant:
            return
        offset = 0
        while True:
            users = await self._users.list_by_tenant(
                tenant_id, offset=offset, limit=_USERS_PAGE_SIZE
            )
            if not users:
                break
            for user in users:
                await self.refresh_keys_cache_for_user(user, tenant)
            if len(users) < _USERS_PAGE_SIZE:
                break
            offset += _USERS_PAGE_SIZE

    async def _patch_all_tenant_key_caches(
        self, tenant_id: int, field: str, value: str
    ) -> None:
        """Patch a single Redis hash field on every cached API key for the tenant."""
        if self._repo is None or self._users is None:
            return
        offset = 0
        while True:
            users = await self._users.list_by_tenant(
                tenant_id, offset=offset, limit=_USERS_PAGE_SIZE
            )
            if not users:
                break
            for user in users:
                for key in await self._repo.list_by_user(user.id):
                    if key.is_active and not key.is_expired():
                        await self._cache.patch_api_key_cache_field(key.api_key, field, value)
            if len(users) < _USERS_PAGE_SIZE:
                break
            offset += _USERS_PAGE_SIZE

    async def set_budget_exhausted_for_tenant(self, tenant_id: int, exhausted: bool) -> None:
        """Flip budget-exhausted on all cached API key hashes for the tenant."""
        await self._patch_all_tenant_key_caches(
            tenant_id, "budget-exhausted", "1" if exhausted else "0"
        )

    async def reset_all_quota_fields(self) -> None:
        """HDEL every quota-* field from all active API key hashes across all tenants.
        Called by the monthly cron on the 1st of each month.
        """
        if self._repo is None or self._users is None or self._tenants is None:
            logger.warning("reset_all_quota_fields skipped: missing repositories")
            return
        inference_fields = [f"quota-{entry['name']}" for entry in get_inference_types()]
        offset = 0
        while True:
            # list_by_tenant with tenant_id=None isn't available; iterate all users via repo
            users = await self._users.list_all(offset=offset, limit=_USERS_PAGE_SIZE)
            if not users:
                break
            for user in users:
                for key in await self._repo.list_by_user(user.id):
                    if key.is_active and not key.is_expired():
                        await self._cache.delete_api_key_cache_fields(key.api_key, inference_fields)
            if len(users) < _USERS_PAGE_SIZE:
                break
            offset += _USERS_PAGE_SIZE

    async def set_quota_exhausted_for_tenant(
        self, tenant_id: int, inference_name: str
    ) -> None:
        """Mark quota-{inference_name} exhausted on all cached API key hashes for the tenant."""
        await self._patch_all_tenant_key_caches(
            tenant_id, f"quota-{inference_name}", "1"
        )

    async def create_api_key(
        self,
        user_id: UUID,
        key_name: str,
        permissions: list[int],
        expires_days: Optional[int] = None,
        tenant_id: Optional[str] = None,
    ) -> tuple[str, APIKey]:
        """
        Generate a hex API key, persist to DB, cache in Redis.
        Returns (raw_hex_key, api_key_record). Raw key is shown once and never stored again.
        """
        # Validate expires_days if provided
        if expires_days is not None:
            if not isinstance(expires_days, int) or expires_days < 1:
                raise ValidationError(
                    message="Invalid expires_days. Must be a positive integer.",
                    code="INVALID_EXPIRES_DAYS",
                )

        permission_ids = list(dict.fromkeys(permissions or []))

        # Validate permission IDs
        if permission_ids:
            await self._validate_permission_ids(permission_ids)

        raw_key = self.generate_api_key()
        days = expires_days or settings.api_key_expire_days
        expires_at = datetime.now(timezone.utc) + timedelta(days=days)
        ttl = int(timedelta(days=days).total_seconds())

        if self._users is None:
            raise ValidationError(
                message="API key service is missing user repository; cannot verify owner state.",
                code="API_KEY_SERVICE_MISCONFIGURED",
            )

        owner = await self._users.get_by_id(user_id)
        if not owner:
            raise EntityNotFoundError("User")

        tenant = None
        if owner.tenant_id is not None:
            if self._tenants is None:
                raise ValidationError(
                    message="API key service is missing tenant repository; cannot verify tenant state.",
                    code="API_KEY_SERVICE_MISCONFIGURED",
                )
            tenant = await self._tenants.get_by_id(owner.tenant_id)
        owner_active = self.user_may_use_api_keys(owner, tenant)

        api_key = APIKey(
            api_key=raw_key,
            user_id=user_id,
            key_name=key_name,
            permissions=permission_ids,
            expires_at=expires_at,
            is_active=True,
            created_by=str(user_id),
            updated_by=str(user_id),
        )
        await self._repo.create(api_key)
        await self._repo.commit()

        if owner_active:
            await self._cache.set_api_key_cache(
                raw_key,
                ttl,
                {
                    "api_key": raw_key,
                    "permissions": permission_ids,
                    "user_id": str(user_id),
                    "tenant_id": tenant_id,
                    "tier_id": "",
                    "budget-exhausted": "0",
                    **{f"quota-{entry['name']}": "0" for entry in get_inference_types()},
                },
            )

        logger.info("API key created: name=%s user=%s permissions=%s", key_name, user_id, permission_ids)
        return raw_key, api_key

    async def validate_api_key(self, token: str) -> dict:
        """
        Validate a hex API key. Redis-only — zero DB calls.
        Raises InvalidAPIKeyError when the key is absent from Redis (revoked or never existed).
        """
        if not self._is_api_key(token):
            return {"valid": False, "message": "Invalid API key format."}

        cached = await self._cache.get_api_key_cache(token)
        if cached is None:
            raise InvalidAPIKeyError()

        return {
            **cached,
            "valid": True,
            "permission_ids": cached.get("permissions", []),
        }

    async def revoke_api_key(
        self,
        api_key_value: str,
        user_id: Optional[UUID] = None,
    ) -> None:
        # Validate API key format
        if not self._is_api_key(api_key_value):
            raise ValidationError(
                message="Invalid API key format. Must be a 32-character hex string.",
                code="INVALID_API_KEY_FORMAT",
            )

        # Check if API key exists
        db_key = await self._repo.get_by_api_key(api_key_value)
        if not db_key:
            raise EntityNotFoundError("API key")

        # Check authorization (owner can only revoke own keys unless admin)
        if user_id is not None and db_key.user_id != user_id:
            raise AuthorizationError(
                message="You do not have permission to revoke this API key. API keys can only be revoked by their owner.",
                code="UNAUTHORIZED_API_KEY_REVOCATION",
            )

        await self._repo.revoke(db_key)
        await self._repo.commit()

        # Evict from Redis AFTER DB commit to ensure atomicity
        await self._cache.delete_api_key_cache(api_key_value)
        logger.info("API key revoked: api_key=%s user=%s", api_key_value, db_key.user_id)

    async def update_key(
        self,
        api_key_value: str,
        data: dict,
        user_id: Optional[UUID] = None,
    ) -> APIKey:
        # Validate API key format
        if not self._is_api_key(api_key_value):
            raise ValidationError(
                message="Invalid API key format. Must be a 32-character hex string.",
                code="INVALID_API_KEY_FORMAT",
            )

        # Check if API key exists
        db_key = await self._repo.get_by_api_key(api_key_value)
        if not db_key:
            raise EntityNotFoundError("API key")

        # Check authorization (owner can only update own keys)
        if user_id is not None and db_key.user_id != user_id:
            raise AuthorizationError(
                message="You do not have permission to update this API key. API keys can only be updated by their owner.",
                code="UNAUTHORIZED_API_KEY_UPDATE",
            )

        # Validate permissions if provided
        permissions = data.get("permissions")
        if permissions is not None:
            await self._validate_permission_ids(permissions)

        # Validate expires_days if provided
        expires_days = data.pop("expires_days", None)
        if expires_days is not None:
            if not isinstance(expires_days, int) or expires_days < 1:
                raise ValidationError(
                    message="Invalid expires_days. Must be a positive integer.",
                    code="INVALID_EXPIRES_DAYS",
                )
            data["expires_at"] = datetime.now(timezone.utc) + timedelta(days=expires_days)

        # Set updated_by
        if user_id is not None:
            data["updated_by"] = str(user_id)

        # Update in database
        await self._repo.update(db_key, data)
        await self._repo.refresh(db_key)

        await self._repo.commit()

        tenant_id_str: Optional[str] = None
        if self._users is not None:
            owner = await self._users.get_by_id(db_key.user_id)
            tenant = None
            if owner and owner.tenant_id is not None and self._tenants is not None:
                tenant = await self._tenants.get_by_id(owner.tenant_id)
                tenant_id_str = str(owner.tenant_id)
            if owner:
                should_cache = self.effective_is_active(db_key, owner, tenant)
                if should_cache:
                    await self._refresh_redis_cache(db_key, tenant_id_str)
                else:
                    await self._cache.delete_api_key_cache(api_key_value)
            else:
                await self._cache.delete_api_key_cache(api_key_value)
        elif data.get("is_active") is False:
            await self._cache.delete_api_key_cache(api_key_value)
        logger.info("API key updated: api_key=%s user=%s", api_key_value, db_key.user_id)
        return db_key

    async def list_by_user(self, user_id: UUID) -> list[APIKey]:
        return await self._repo.list_by_user(user_id)

    async def list_all_with_users(self, offset: int = 0, limit: int = 100) -> list:
        return await self._repo.list_all_with_users(offset, limit)

    async def get_by_api_key(self, api_key_value: str) -> Optional[APIKey]:
        return await self._repo.get_by_api_key(api_key_value)
