"""
API key creation, revocation, and validation.

Keys are 32-char hex strings generated via secrets.token_hex(16).
The raw hex key is stored directly in Postgres (api_key column = primary key).
Redis is the sole validation path at inference time — zero DB calls per request.
Revocation immediately deletes the Redis entry; subsequent lookups find nothing.

Effective key status (no separate DB status column):
  * Active   — ``is_active=True`` and user/tenant allow access (Redis cached)
  * Inactive — ``is_active=True`` but tenant SUSPENDED / user locked (Redis evicted;
               auto-resumes to Active on reactivation via cache refresh)
  * Revoked  — ``is_active=False`` (tenant DEACTIVATED or explicit revoke;
               reactivation does not restore the key)
"""

import logging
import re
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from ai4i_core.ppu import get_inference_types

from app.core.config import settings
from app.core.database import get_db
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

# Ad hoc, short-lived session for validate_api_key's DB fallback — opened only
# on an actual Redis miss, independent of any repository injected into a
# given APIKeyService instance. Wraps the same session factory/rollback logic
# FastAPI's own Depends(get_db) uses; borrows a connection from the app's one
# already-initialized engine, not a separate pool.
_open_db_session = asynccontextmanager(get_db)


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

    async def _resolve_permission_names(self, permission_names: list[str]) -> list[int]:
        """Resolve stable permission names to DB IDs; raise ValidationError for unknown names."""
        unique_names = list(dict.fromkeys(permission_names or []))
        if not unique_names:
            return []
        name_to_id = await self._repo.get_permission_ids_by_names(unique_names)
        missing = [name for name in unique_names if name not in name_to_id]
        if missing:
            raise ValidationError(
                message="Invalid permission names in request.",
                code="INVALID_PERMISSION_NAMES",
                errors=[f"Unknown permission: {name}" for name in missing],
            )
        return [name_to_id[name] for name in unique_names]

    async def permission_ids_to_names(
        self, permission_ids: list[int], *, api_key_id: int | None = None
    ) -> list[str]:
        """Map stored permission IDs to stable names for client-facing responses."""
        if not permission_ids:
            return []
        id_to_name = await self._repo.get_permission_names_by_ids(permission_ids)
        names = []
        for pid in permission_ids:
            name = id_to_name.get(pid)
            if name is None:
                if api_key_id is not None:
                    logger.warning(
                        "api_key id=%s references unknown permission id=%s",
                        api_key_id,
                        pid,
                    )
                else:
                    logger.warning("unknown permission id=%s (no name mapping)", pid)
                continue
            names.append(name)
        return names

    async def permission_name_map_for_keys(self, keys: list[APIKey]) -> dict[int, str]:
        """Batch-fetch id→name for all permission IDs referenced by the given keys."""
        all_ids: set[int] = set()
        for key in keys:
            all_ids.update(key.permissions or [])
        if not all_ids:
            return {}
        return await self._repo.get_permission_names_by_ids(list(all_ids))

    @staticmethod
    def _compute_cache_ttl(db_key: APIKey) -> int:
        """Seconds until ``db_key`` expires, or the configured default TTL
        when it never expires. Never negative."""
        if db_key.expires_at:
            return max(0, int((db_key.expires_at - datetime.now(timezone.utc)).total_seconds()))
        return int(timedelta(days=settings.api_key_expire_days).total_seconds())

    @staticmethod
    def _build_cache_payload(
        db_key: APIKey, tenant_id: Optional[str], extra_fields: Optional[dict] = None
    ) -> dict:
        """The canonical Redis-hash shape for an API key — defined once so
        every writer (create, refresh, DB-fallback rehydrate) stays in sync."""
        return {
            "api_key": db_key.api_key,
            "permissions": db_key.permissions or [],
            "user_id": str(db_key.user_id),
            "tenant_id": tenant_id,
            **(extra_fields or {}),
        }

    @staticmethod
    async def _persist_cache_snapshot(
        repo: APIKeyRepository, db_key: APIKey, payload: dict
    ) -> None:
        """Mirror ``payload`` (minus transient billing flags) onto
        ``api_key.cached_data`` so a future Redis miss can repopulate the
        cache without rejoining users/tenants."""
        snapshot = {
            k: v
            for k, v in payload.items()
            if k != "budget-exhausted" and not k.startswith("quota-")
        }
        await repo.update(db_key, {"cached_data": snapshot})
        await repo.commit()

    async def _refresh_redis_cache(
        self, db_key: APIKey, tenant_id: Optional[str]
    ) -> None:
        ttl = self._compute_cache_ttl(db_key)
        if ttl <= 0:
            return
        existing = await self._cache.get_api_key_cache(db_key.api_key)
        preserved = {
            k: v
            for k, v in (existing or {}).items()
            if v == "1" and (k == "budget-exhausted" or k.startswith("quota-"))
        }
        payload = self._build_cache_payload(db_key, tenant_id, preserved)
        await self._cache.set_api_key_cache(db_key.api_key, ttl, payload)
        await self._persist_cache_snapshot(self._repo, db_key, payload)

    async def evict_keys_for_user(self, user_id: UUID) -> None:
        """Remove Redis entries for all keys owned by ``user_id``. No DB writes."""
        if self._repo is None:
            return
        for key in await self._repo.list_by_user(user_id):
            await self._cache.delete_api_key_cache(key.api_key)

    async def evict_keys_for_tenant(self, tenant_id: int) -> None:
        """Evict Redis cache for all tenant users' keys. No DB writes.

        Used for tenant SUSPENDED: keys stay ``is_active=True`` (Inactive) so
        reactivation can repopulate Redis without issuing a new key.
        """
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

    async def revoke_keys_for_tenant(self, tenant_id: int) -> None:
        """Permanently revoke all active API keys for a tenant (DEACTIVATED).

        Bulk-sets ``is_active=False``, commits, then deletes Redis entries.
        Commit-before-Redis matches ``revoke_by_obj`` ordering so a failed
        commit cannot leave Redis empty while keys remain active (which would
        let a later reactivation refresh restore them). Reactivating the
        tenant will not restore revoked keys — an admin must create new ones.
        """
        if self._repo is None or self._users is None:
            logger.warning(
                "revoke_keys_for_tenant skipped: missing repositories (tenant_id=%s)",
                tenant_id,
            )
            return
        revoked_keys: list[str] = []
        offset = 0
        while True:
            users = await self._users.list_by_tenant(
                tenant_id, offset=offset, limit=_USERS_PAGE_SIZE
            )
            if not users:
                break
            page_keys = await self._repo.revoke_active_for_users(
                [user.id for user in users]
            )
            revoked_keys.extend(page_keys)
            if len(users) < _USERS_PAGE_SIZE:
                break
            offset += _USERS_PAGE_SIZE
        if not revoked_keys:
            logger.info(
                "Revoked 0 API key(s) for deactivated tenant_id=%s",
                tenant_id,
            )
            return
        await self._repo.commit()
        for api_key in revoked_keys:
            await self._cache.delete_api_key_cache(api_key)
        logger.info(
            "Revoked %s API key(s) for deactivated tenant_id=%s",
            len(revoked_keys),
            tenant_id,
        )

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

    async def _for_each_active_tenant_key(self, tenant_id: Optional[int], op) -> None:
        """Apply ``op(key)`` to every active, non-expired API key for a tenant
        (or across all tenants when ``tenant_id`` is None). Callers must check
        for missing repositories before calling."""
        offset = 0
        while True:
            if tenant_id is not None:
                users = await self._users.list_by_tenant(
                    tenant_id, offset=offset, limit=_USERS_PAGE_SIZE
                )
            else:
                users = await self._users.list_all(offset=offset, limit=_USERS_PAGE_SIZE)
            if not users:
                break
            for user in users:
                for key in await self._repo.list_by_user(user.id):
                    if key.is_active and not key.is_expired():
                        await op(key)
            if len(users) < _USERS_PAGE_SIZE:
                break
            offset += _USERS_PAGE_SIZE

    async def _patch_all_tenant_key_caches(
        self, tenant_id: int, field: str, value: str
    ) -> None:
        """Patch a single Redis hash field on every cached API key for the tenant."""
        if self._repo is None or self._users is None:
            return
        await self._for_each_active_tenant_key(
            tenant_id,
            lambda key: self._cache.patch_api_key_cache_field(key.api_key, field, value),
        )

    async def set_budget_exhausted_for_tenant(self, tenant_id: int, exhausted: bool) -> None:
        """Flip budget-exhausted on all cached API key hashes for the tenant."""
        await self._patch_all_tenant_key_caches(
            tenant_id, "budget-exhausted", "1" if exhausted else "0"
        )

    async def reset_all_quota_fields(self) -> None:
        """HDEL every quota-* field from all active API key hashes across all tenants.
        Called by the monthly cron on the 1st of each month.

        Reads api_keys directly, paginated by key id — no join through users
        (list_active_keys), and clears each page via one pipelined Redis call
        (delete_api_key_cache_fields_bulk) instead of one HDEL per key. This
        was previously one DB query per user plus one serial HDEL per key,
        which doesn't scale to a large (lakhs-of-keys) tenant population.
        """
        if self._repo is None:
            logger.warning("reset_all_quota_fields skipped: missing repositories")
            return
        inference_fields = [f"quota-{entry['name']}" for entry in get_inference_types()]
        offset = 0
        while True:
            keys = await self._repo.list_active_keys(offset=offset, limit=_USERS_PAGE_SIZE)
            if not keys:
                break
            await self._cache.delete_api_key_cache_fields_bulk(
                [key.api_key for key in keys], inference_fields
            )
            if len(keys) < _USERS_PAGE_SIZE:
                break
            offset += _USERS_PAGE_SIZE

    async def set_quota_exhausted_for_tenant(
        self, tenant_id: int, inference_name: str
    ) -> None:
        """Mark quota-{inference_name} exhausted on all cached API key hashes for the tenant."""
        await self._patch_all_tenant_key_caches(
            tenant_id, f"quota-{inference_name}", "1"
        )

    async def clear_quota_flags_for_tenant(self, tenant_id: int) -> None:
        """HDEL every quota-* field from this tenant's cached API key hashes.

        Used when a tenant is reassigned to a new tier: ppu_quota_usage starts
        a fresh row under the new tier_id, so any quota-exhausted flag set
        under the previous tier is stale and must not keep 429'ing requests
        until the monthly cron runs.
        """
        if self._repo is None or self._users is None:
            logger.warning(
                "clear_quota_flags_for_tenant skipped: missing repositories (tenant_id=%s)",
                tenant_id,
            )
            return
        inference_fields = [f"quota-{entry['name']}" for entry in get_inference_types()]
        await self._for_each_active_tenant_key(
            tenant_id,
            lambda key: self._cache.delete_api_key_cache_fields(key.api_key, inference_fields),
        )

    async def create_api_key(
        self,
        user_id: UUID,
        key_name: str,
        permissions: list[str],
        expires_days: Optional[int] = None,
        tenant_id: Optional[str] = None,
        platform_core_db: Optional[AsyncSession] = None,
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

        permission_ids = await self._resolve_permission_names(permissions)

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

        if not tenant_id:
            raise ValidationError(
                message="A tenant ID is required to create an API key.",
                code="TENANT_ID_REQUIRED",
            )

        if platform_core_db is None:
            raise ValidationError(
                message="Tier assignment cannot be verified: platform-core DB is not configured.",
                code="PLATFORM_CORE_DB_NOT_CONFIGURED",
            )

        tier_id = ""
        try:
            row = (await platform_core_db.execute(
                text(
                    "SELECT tier_id FROM ppu_tenant_tier_assignments"
                    " WHERE tenant_id = :tenant_id"
                    "   AND effective_from <= now()"
                    "   AND effective_to   >  now()"
                    " LIMIT 1"
                ),
                {"tenant_id": tenant_id},
            )).first()
            if row:
                tier_id = str(row.tier_id)
        except Exception as exc:
            logger.warning("Failed to fetch tier_id for tenant %s: %s", tenant_id, exc)
            raise ValidationError(
                message="Failed to verify tier assignment for the tenant.",
                code="TIER_LOOKUP_FAILED",
            ) from exc

        if not tier_id:
            raise ValidationError(
                message="API key cannot be created: tenant has no active tier assignment.",
                code="NO_ACTIVE_TIER",
            )

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
            payload = self._build_cache_payload(api_key, tenant_id, {"tier_id": tier_id})
            await self._cache.set_api_key_cache(raw_key, ttl, payload)
            await self._persist_cache_snapshot(self._repo, api_key, payload)

        logger.info("API key created: name=%s user=%s permissions=%s", key_name, user_id, permission_ids)
        return raw_key, api_key

    @staticmethod
    def _is_cache_entry_invalid(cached: dict) -> bool:
        """True for a negatively-cached (tombstoned) token."""
        return cached.get("is_already_invalid") == "1" if isinstance(cached, dict) else False

    @staticmethod
    def _shape_validation_result(payload: dict) -> dict:
        return {
            **payload,
            "valid": True,
            "permission_ids": payload.get("permissions", []),
        }

    @staticmethod
    async def _get_api_key_from_db(repo: APIKeyRepository, token: str) -> Optional[APIKey]:
        """DB fallback for a Redis miss. ``repo`` eager-loads user/tenant so
        eligibility can be checked without further queries."""
        return await repo.get_by_api_key_if_valid(token)

    def _is_key_eligible(self, db_key: APIKey) -> bool:
        """Beyond is_active/expiry (already filtered in the DB query): the
        owning user and tenant must still allow API-key authentication."""
        if db_key.user is None:
            logger.warning(
                "API key %s has no owning user row; treating as ineligible", db_key.api_key
            )
            return False
        return self.user_may_use_api_keys(db_key.user, db_key.user.tenant)

    async def _rehydrate_cache_from_db(self, db_key: APIKey) -> dict:
        """Repopulate Redis for an eligible key found on a cache miss —
        verbatim from its persisted ``cached_data`` snapshot, the only source
        of truth for this path (write-through: cached_data is kept in sync on
        every create/update; never synthesized here — the PPU tier lookup it
        can carry isn't safe to redo on this hot path)."""
        if not db_key.cached_data:
            raise InvalidAPIKeyError()
        payload = db_key.cached_data
        ttl = self._compute_cache_ttl(db_key)
        if ttl <= 0:
            return payload
        await self._cache.set_api_key_cache(db_key.api_key, ttl, payload)
        return payload

    async def _tombstone_invalid_token(self, token: str) -> None:
        """Negative-cache a token confirmed absent/ineligible, so repeat
        requests fail fast from Redis instead of re-querying the DB."""
        await self._cache.set_api_key_cache(
            token, settings.invalid_api_key_cache_ttl_seconds, {"is_already_invalid": "1"}
        )

    async def _resolve_from_db_or_tombstone(self, token: str) -> dict:
        """Owns the DB session for the whole miss-handling flow — opened here
        lazily (only on an actual cache miss), not injected via the
        constructor, so the validation hot path never carries a DB
        dependency unless one is genuinely needed."""
        async with _open_db_session() as session:
            repo = APIKeyRepository(session)
            db_key = await self._get_api_key_from_db(repo, token)
            if db_key is None or not self._is_key_eligible(db_key):
                await self._tombstone_invalid_token(token)
                raise InvalidAPIKeyError()
            return await self._rehydrate_cache_from_db(db_key)

    async def validate_api_key(self, token: str) -> dict:
        """
        Validate a hex API key. Redis-first: a cache hit is zero-DB. On a
        miss, falls back to Postgres to repopulate the cache; a token that's
        absent or no longer eligible is negatively cached before raising.
        """
        if not self._is_api_key(token):
            return {"valid": False, "message": "Invalid API key format."}

        cached = await self._cache.get_api_key_cache(token)
        if cached is not None:
            if self._is_cache_entry_invalid(cached):
                raise InvalidAPIKeyError()
            return self._shape_validation_result(cached)

        payload = await self._resolve_from_db_or_tombstone(token)
        return self._shape_validation_result(payload)

    async def revoke_api_key(
        self,
        api_key_value: str,
        user_id: Optional[UUID] = None,
    ) -> None:
        if not self._is_api_key(api_key_value):
            raise ValidationError(
                message="Invalid API key format. Must be a 32-character hex string.",
                code="INVALID_API_KEY_FORMAT",
            )
        db_key = await self._repo.get_by_api_key(api_key_value)
        if not db_key:
            raise EntityNotFoundError("API key")
        if user_id is not None and db_key.user_id != user_id:
            raise AuthorizationError(
                message="You do not have permission to revoke this API key. API keys can only be revoked by their owner.",
                code="UNAUTHORIZED_API_KEY_REVOCATION",
            )
        await self.revoke_by_obj(db_key)

    async def update_key(
        self,
        api_key_value: str,
        data: dict,
        user_id: Optional[UUID] = None,
    ) -> APIKey:
        if not self._is_api_key(api_key_value):
            raise ValidationError(
                message="Invalid API key format. Must be a 32-character hex string.",
                code="INVALID_API_KEY_FORMAT",
            )
        db_key = await self._repo.get_by_api_key(api_key_value)
        if not db_key:
            raise EntityNotFoundError("API key")
        if user_id is not None and db_key.user_id != user_id:
            raise AuthorizationError(
                message="You do not have permission to update this API key. API keys can only be updated by their owner.",
                code="UNAUTHORIZED_API_KEY_UPDATE",
            )
        return await self.update_key_by_obj(db_key, data, user_id)

    async def revoke_by_obj(self, db_key: APIKey) -> None:
        """Revoke a key that has already been fetched and ownership-verified by the caller.
        Skips the second get_by_api_key lookup that revoke_api_key() would otherwise perform."""
        await self._repo.revoke(db_key)
        await self._repo.commit()
        await self._cache.delete_api_key_cache(db_key.api_key)
        logger.info("API key revoked: api_key=%s user=%s", db_key.api_key, db_key.user_id)

    async def update_key_by_obj(
        self,
        db_key: APIKey,
        data: dict,
        user_id: Optional[UUID] = None,
    ) -> APIKey:
        """Update a key that has already been fetched and ownership-verified by the caller.
        Skips the second get_by_api_key lookup that update_key() would otherwise perform."""
        data = dict(data)  # avoid mutating the caller's dict

        permissions = data.get("permissions")
        if permissions is not None:
            data["permissions"] = await self._resolve_permission_names(permissions)

        expires_days = data.pop("expires_days", None)
        if expires_days is not None:
            if not isinstance(expires_days, int) or expires_days < 1:
                raise ValidationError(
                    message="Invalid expires_days. Must be a positive integer.",
                    code="INVALID_EXPIRES_DAYS",
                )
            data["expires_at"] = datetime.now(timezone.utc) + timedelta(days=expires_days)

        if user_id is not None:
            data["updated_by"] = str(user_id)

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
                if self.effective_is_active(db_key, owner, tenant):
                    await self._refresh_redis_cache(db_key, tenant_id_str)
                else:
                    await self._cache.delete_api_key_cache(db_key.api_key)
            else:
                await self._cache.delete_api_key_cache(db_key.api_key)
        elif data.get("is_active") is False:
            await self._cache.delete_api_key_cache(db_key.api_key)

        logger.info("API key updated: api_key=%s user=%s", db_key.api_key, db_key.user_id)
        return db_key

    async def list_by_user(self, user_id: UUID) -> list[APIKey]:
        return await self._repo.list_by_user(user_id)

    async def list_all_with_users(self, offset: int = 0, limit: int = 100) -> list:
        return await self._repo.list_all_with_users(offset, limit)

    async def get_by_api_key(self, api_key_value: str) -> Optional[APIKey]:
        return await self._repo.get_by_api_key(api_key_value)

    async def get_by_id(self, key_id: int) -> Optional[APIKey]:
        return await self._repo.get_by_id(key_id)

    async def get_by_id_for_owner(self, key_id: int, user_id: UUID) -> Optional[APIKey]:
        return await self._repo.get_by_id_for_owner(key_id, user_id)
