"""
API key creation, revocation, and validation.

Keys are 32-char hex strings generated via secrets.token_hex(16).
The raw hex key is stored directly in Postgres (api_key column = primary key).
Redis is the sole validation path at inference time — zero DB calls per request.
Revocation immediately deletes the Redis entry; subsequent lookups find nothing.

Ownership: an API key belongs to an Application, not a User (migration
e9f0a1b2c3d4 dropped api_key.user_id in favor of api_key.application_id).
Eligibility to serve a key therefore depends on the owning Application's and
its Tenant's state — there is no per-user access flag in this path anymore.

Effective key status (no separate DB status column):
  * Active   — ``is_active=True`` and application/tenant allow access (Redis cached)
  * Inactive — ``is_active=True`` but application INACTIVE / tenant SUSPENDED
               (Redis evicted; auto-resumes to Active on reactivation via cache refresh)
  * Revoked  — ``is_active=False`` (tenant DEACTIVATED or explicit revoke;
               reactivation does not restore the key)
"""

import logging
import re
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ai4i_core.ppu import get_inference_types

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import AuthorizationError, EntityNotFoundError, InvalidAPIKeyError, ValidationError
from app.models.api_key import APIKey
from app.models.application import Application, ApplicationStatus
from app.models.tenant import Tenant, TenantStatus
from app.repositories.api_key_repository import APIKeyRepository
from app.repositories.application_repository import ApplicationRepository
from app.repositories.tenant_repository import TenantRepository
from app.services import budget_usage
from app.services.cache_service import CacheService

logger = logging.getLogger(__name__)

_HEX_KEY_RE = re.compile(r"[0-9a-f]{32}")
_TENANT_CASCADE_PAGE_SIZE = 500

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
        application_repo: Optional[ApplicationRepository] = None,
        tenant_repo: Optional[TenantRepository] = None,
    ) -> None:
        self._repo = api_key_repo
        self._cache = cache_service
        self._applications = application_repo
        self._tenants = tenant_repo

    @staticmethod
    def application_may_use_api_keys(
        application: Optional[Application], tenant: Optional[Tenant]
    ) -> bool:
        """True when the application and its tenant allow API key authentication."""
        if application is not None and application.status != ApplicationStatus.ACTIVE:
            return False
        if tenant is None:
            return True
        return tenant.status == TenantStatus.ACTIVE

    @staticmethod
    def effective_is_active(
        api_key: APIKey, application: Optional[Application], tenant: Optional[Tenant]
    ) -> bool:
        """Runtime validity: not revoked, not expired, application/tenant allow access."""
        return bool(
            api_key.is_active
            and not api_key.is_expired()
            and APIKeyService.application_may_use_api_keys(application, tenant)
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
            "id": db_key.id,
            "api_key": db_key.api_key,
            "permissions": db_key.permissions or [],
            "application_id": str(db_key.application_id),
            "tenant_id": tenant_id,
            "user_id": str(db_key.created_by) if db_key.created_by else None,
            **(extra_fields or {}),
        }

    @staticmethod
    def _preserved_billing_fields(db_key: APIKey) -> dict:
        """budget-exhausted/quota-* already in cached_data, carried forward so a
        refresh never erases billing state the PPU write-through path
        (patch_cached_data_field_for_tenant et al.) wrote directly into
        cached_data — mirrors how _refresh_redis_cache's own ``preserved``
        carries the same fields forward from the live Redis hash."""
        return {
            k: v
            for k, v in (db_key.cached_data or {}).items()
            if k == "budget-exhausted" or k.startswith("quota-")
        }

    async def _persist_cache_snapshot(self, db_key: APIKey, payload: dict) -> None:
        """Mirror ``payload`` onto ``api_key.cached_data`` so a future Redis
        miss can repopulate the cache without rejoining applications/tenants.
        Merges forward any billing flags already in cached_data that
        ``payload`` doesn't itself carry — payload's own values (e.g.
        preserved from a live Redis hash) still win when present, since
        they're fresher."""
        snapshot = {**self._preserved_billing_fields(db_key), **payload}
        await self._repo.update(db_key, {"cached_data": snapshot})
        await self._repo.commit()

    @staticmethod
    def _preserved_tier_id(db_key: APIKey) -> dict:
        """tier_id is only ever correctly computed once, at create_api_key
        time (a read of tenants.tier_id) — every other writer must carry
        forward whatever's already in cached_data instead of recomputing it."""
        if db_key.cached_data and "tier_id" in db_key.cached_data:
            return {"tier_id": db_key.cached_data["tier_id"]}
        return {}

    async def _refresh_redis_cache(
        self, db_key: APIKey, tenant_id: Optional[str]
    ) -> None:
        ttl = self._compute_cache_ttl(db_key)
        if ttl <= 0:
            return
        existing = await self._cache.get_api_key_cache(db_key.api_key)
        # No value filter: a live "0" is evidence too — filtering to v == "1"
        # would let a stale "1" in cached_data win the merge below and
        # resurrect a cleared budget-exhausted flag into both stores.
        preserved_from_redis = {
            k: v
            for k, v in (existing or {}).items()
            if k == "budget-exhausted" or k.startswith("quota-")
        }
        # cached_data's own billing state is the base (covers a cold/evicted Redis
        # hash with nothing to preserve); Redis's live state, if any, overrides it —
        # keeps both stores converging on the same values instead of just one.
        preserved = {**self._preserved_billing_fields(db_key), **preserved_from_redis}
        payload = self._build_cache_payload(
            db_key, tenant_id, {**self._preserved_tier_id(db_key), **preserved}
        )
        await self._cache.set_api_key_cache(db_key.api_key, ttl, payload)
        await self._persist_cache_snapshot(db_key, payload)

    async def _persist_current_state_to_cached_data(
        self, db_key: APIKey, tenant_id: Optional[str]
    ) -> None:
        """Write-through even while the key isn't currently eligible to be
        served (revoked, or application/tenant temporarily inactive):
        cached_data must never silently drift from the row an admin just
        edited, or a later reactivation/DB-fallback rehydrate would serve
        stale permissions/expiry. Redis is deliberately left alone here —
        only the DB snapshot updates, since the key must not become servable
        again just because its details changed."""
        payload = self._build_cache_payload(db_key, tenant_id, self._preserved_tier_id(db_key))
        await self._persist_cache_snapshot(db_key, payload)

    async def evict_keys_for_application(self, application_id: int) -> None:
        """Remove Redis entries for all keys under ``application_id``. No DB writes."""
        if self._repo is None:
            return
        for key in await self._repo.list_by_application(application_id):
            await self._cache.delete_api_key_cache(key.api_key)

    async def evict_keys_for_tenant(self, tenant_id: int) -> None:
        """Evict Redis cache for all of the tenant's applications' keys. No DB writes.

        Used for tenant SUSPENDED: keys stay ``is_active=True`` (Inactive) so
        reactivation can repopulate Redis without issuing a new key.
        """
        if self._repo is None:
            return
        after_id = 0
        while True:
            keys = await self._repo.list_active_keys_for_tenant(
                tenant_id, after_id=after_id, limit=_TENANT_CASCADE_PAGE_SIZE
            )
            if not keys:
                break
            for key in keys:
                await self._cache.delete_api_key_cache(key.api_key)
            after_id = keys[-1].id
            if len(keys) < _TENANT_CASCADE_PAGE_SIZE:
                break

    async def revoke_keys_for_tenant(self, tenant_id: int) -> None:
        """Permanently revoke all active API keys for a tenant (DEACTIVATED).

        Bulk-sets ``is_active=False``, commits, then deletes Redis entries.
        Commit-before-Redis matches ``revoke_by_obj`` ordering so a failed
        commit cannot leave Redis empty while keys remain active (which would
        let a later reactivation refresh restore them). Reactivating the
        tenant will not restore revoked keys — an admin must create new ones.
        """
        if self._repo is None or self._applications is None:
            logger.warning(
                "revoke_keys_for_tenant skipped: missing repositories (tenant_id=%s)",
                tenant_id,
            )
            return
        applications = await self._applications.list_by_tenant(tenant_id)
        application_ids = [a.id for a in applications]
        revoked_keys = await self._repo.revoke_active_for_applications(application_ids)
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

    async def refresh_keys_cache_for_application(
        self,
        application: Application,
        tenant: Optional[Tenant] = None,
    ) -> None:
        """Repopulate Redis for keys that remain valid for the application's access state."""
        if self._repo is None:
            return
        if tenant is None and self._tenants is not None:
            tenant = await self._tenants.get_by_id(application.tenant_id)
        if not self.application_may_use_api_keys(application, tenant):
            await self.evict_keys_for_application(application.id)
            return
        tenant_id_str = str(application.tenant_id)
        for key in await self._repo.list_by_application(application.id):
            if key.is_active and not key.is_expired():
                await self._refresh_redis_cache(key, tenant_id_str)

    async def refresh_keys_cache_for_tenant(self, tenant_id: int) -> None:
        """Repopulate Redis for all eligible keys in the tenant."""
        if self._repo is None or self._applications is None or self._tenants is None:
            logger.warning(
                "refresh_keys_cache_for_tenant skipped: missing repositories (tenant_id=%s)",
                tenant_id,
            )
            return
        tenant = await self._tenants.get_by_id(tenant_id)
        if not tenant:
            return
        for application in await self._applications.list_by_tenant(tenant_id):
            await self.refresh_keys_cache_for_application(application, tenant)

    async def _for_each_active_tenant_key(self, tenant_id: int, op) -> None:
        """Apply ``op(key)`` to every active, non-expired API key for a
        tenant, keyset-paginated over api_key.id so a large tenant is walked
        in bounded batches."""
        if self._repo is None:
            return
        after_id = 0
        while True:
            keys = await self._repo.list_active_keys_for_tenant(
                tenant_id, after_id=after_id, limit=_TENANT_CASCADE_PAGE_SIZE
            )
            if not keys:
                break
            for key in keys:
                await op(key)
            after_id = keys[-1].id
            if len(keys) < _TENANT_CASCADE_PAGE_SIZE:
                break

    async def _patch_all_tenant_key_caches(
        self, tenant_id: int, field: str, value: str
    ) -> None:
        """Patch a single Redis hash field on every cached API key for the
        tenant, and mirror the same field/value onto cached_data (write-
        through) so it survives a cache eviction instead of resetting to
        unset on the next DB-fallback rehydrate."""
        if self._repo is None:
            return
        await self._for_each_active_tenant_key(
            tenant_id,
            lambda key: self._cache.patch_api_key_cache_field(key.api_key, field, value),
        )
        await self._repo.patch_cached_data_field_for_tenant(tenant_id, field, value)
        await self._repo.commit()

    async def set_budget_exhausted_for_tenant(self, tenant_id: int, exhausted: bool) -> None:
        """Flip budget-exhausted on all cached API key hashes for the tenant."""
        await self._patch_all_tenant_key_caches(
            tenant_id, "budget-exhausted", "1" if exhausted else "0"
        )

    async def list_key_ids_for_tenant(self, tenant_id: int) -> list[int]:
        """Every api_key.id under any Application belonging to tenant_id,
        regardless of active/expired status — used by
        TenantService._sync_ppu_wallet_and_exhaustion to sum this tenant's
        total spend from platform-core's budget_usage ledger (keyed by
        api_key_id, not tenant_id). Unlike list_active_keys_for_tenant, this
        intentionally does not filter by is_active/expiry: a revoked key's
        past spend still counts against the tenant's allocated_budget.
        """
        if self._repo is None:
            return []
        keys = await self._repo.list_by_tenant(tenant_id)
        return [key.id for key in keys]

    async def set_tier_id_for_tenant(self, tenant_id: int, tier_id: str) -> None:
        """Force every cached API key hash for the tenant onto ``tier_id``.

        Needed specifically because _preserved_tier_id makes every other
        cache writer (update, refresh, DB-fallback rehydrate) carry the
        existing tier_id forward rather than recompute it — by design, since
        it's normally only safe to compute once, at create_api_key time.
        A tier reassignment is the one case that legitimately changes it for
        already-issued keys, so it has to be force-written here instead of
        going through the normal preserve-on-write path.
        """
        await self._patch_all_tenant_key_caches(tenant_id, "tier_id", tier_id)

    async def reset_all_quota_fields(self) -> None:
        """HDEL every quota-* field from all active API key hashes across all tenants,
        and remove the same fields from cached_data. Called by the monthly cron on
        the 1st of each month.

        Reads api_keys directly, paginated by key id — no join through
        applications (list_active_keys), and clears each page via one
        pipelined Redis call (delete_api_key_cache_fields_bulk) instead of
        one HDEL per key. The cached_data side is likewise cleared in
        id-keyset batches (remove_cached_data_fields_globally), each its own
        transaction, so neither side holds table-wide locks or builds one
        oversized transaction.
        """
        if self._repo is None:
            logger.warning("reset_all_quota_fields skipped: missing repositories")
            return
        inference_fields = [f"quota-{entry['name']}" for entry in get_inference_types()]
        offset = 0
        page_size = _TENANT_CASCADE_PAGE_SIZE
        while True:
            keys = await self._repo.list_active_keys(offset=offset, limit=page_size)
            if not keys:
                break
            await self._cache.delete_api_key_cache_fields_bulk(
                [key.api_key for key in keys], inference_fields
            )
            if len(keys) < page_size:
                break
            offset += page_size
        # Commits per batch internally (keyset-paginated); no trailing commit needed.
        await self._repo.remove_cached_data_fields_globally(inference_fields)

    async def set_quota_exhausted_for_tenant(
        self, tenant_id: int, inference_name: str
    ) -> None:
        """Mark quota-{inference_name} exhausted on all cached API key hashes for the tenant."""
        await self._patch_all_tenant_key_caches(
            tenant_id, f"quota-{inference_name}", "1"
        )

    async def clear_quota_flags_for_tenant(self, tenant_id: int) -> None:
        """HDEL every quota-* field from this tenant's cached API key hashes,
        and remove the same fields from cached_data.

        Used when a tenant is reassigned to a new tier: ppu_quota_usage starts
        a fresh row under the new tier_id, so any quota-exhausted flag set
        under the previous tier is stale and must not keep 429'ing requests
        until the monthly cron runs.
        """
        if self._repo is None:
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
        await self._repo.remove_cached_data_fields_for_tenant(tenant_id, inference_fields)
        await self._repo.commit()

    async def create_api_key(
        self,
        actor_user_id: UUID,
        key_name: str,
        permissions: list[str],
        application_id: int,
        expires_days: Optional[int] = None,
        allocated_percentage: Optional[Decimal] = None,
        budget: Optional[Decimal] = None,
        *,
        caller_tenant_id: Optional[int] = None,
        platform_core_db: Optional[AsyncSession] = None,
    ) -> tuple[str, APIKey]:
        """
        Generate a hex API key, persist to DB, cache in Redis.
        Returns (raw_hex_key, api_key_record). Raw key is shown once and never stored again.

        ``caller_tenant_id`` is None for a system admin (unscoped — any
        tenant's application may be targeted); otherwise the application must
        belong to that tenant or this raises the same 404 as "doesn't exist"
        (APPLICATION_NOT_FOUND), so a caller cannot enumerate application IDs
        outside their own tenant.
        """
        if expires_days is not None:
            if not isinstance(expires_days, int) or expires_days < 1:
                raise ValidationError(
                    message="Invalid expires_days. Must be a positive integer.",
                    code="INVALID_EXPIRES_DAYS",
                )

        if self._applications is None:
            raise ValidationError(
                message="API key service is missing application repository; cannot verify application.",
                code="API_KEY_SERVICE_MISCONFIGURED",
            )
        if self._tenants is None:
            raise ValidationError(
                message="API key service is missing tenant repository; cannot verify tier assignment.",
                code="API_KEY_SERVICE_MISCONFIGURED",
            )

        if caller_tenant_id is not None:
            application = await self._applications.get_by_id_for_tenant(
                application_id, caller_tenant_id
            )
        else:
            application = await self._applications.get_by_id(application_id)
        if application is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "APPLICATION_NOT_FOUND", "message": "Application not found."},
            )

        tenant = await self._tenants.get_by_id(application.tenant_id)
        if tenant is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "APPLICATION_NOT_FOUND", "message": "Application not found."},
            )

        # Checked via tenants.tier_id directly (no cross-DB PPU lookup needed
        # any more — tier now lives on the tenant row itself).
        if not tenant.tier_id:
            raise ValidationError(
                message="API key cannot be created: tenant has no active tier assignment.",
                code="NO_ACTIVE_TIER",
            )

        permission_ids = await self._resolve_permission_names(permissions)

        if allocated_percentage is not None:
            # Lock the application row for the rest of this transaction so a
            # concurrent create_api_key call under the same application can't
            # read the same existing_total before either commits — without
            # this, two concurrent 60% requests both pass the check and the
            # application ends up over-allocated. Held until this
            # transaction commits below (self._repo.commit()).
            locked_application = await self._applications.get_by_id_for_update(application_id)
            if locked_application is not None:
                application = locked_application
            existing_total = await self._applications.sum_api_key_allocated_percentage(application_id)
            if existing_total + allocated_percentage > Decimal("100"):
                raise ValidationError(
                    message=(
                        f"Allocating {allocated_percentage}% would bring this application's "
                        f"total API key allocation to {existing_total + allocated_percentage}%, "
                        "which exceeds 100%."
                    ),
                    code="ALLOCATION_TOTAL_EXCEEDED",
                )

        allocated_budget: Optional[Decimal] = None
        if allocated_percentage is not None and application.allocated_budget is not None:
            allocated_budget = (application.allocated_budget * allocated_percentage) / Decimal("100")

        raw_key = self.generate_api_key()
        days = expires_days or settings.api_key_expire_days
        expires_at = datetime.now(timezone.utc) + timedelta(days=days)
        ttl = int(timedelta(days=days).total_seconds())

        api_key = APIKey(
            api_key=raw_key,
            application_id=application_id,
            key_name=key_name,
            allocated_percentage=allocated_percentage,
            allocated_budget=allocated_budget,
            permissions=permission_ids,
            expires_at=expires_at,
            is_active=True,
            created_by=str(actor_user_id),
            updated_by=str(actor_user_id),
        )
        await self._repo.create(api_key)
        await self._repo.commit()

        budget_snap = budget if budget is not None else allocated_budget
        if budget_snap is not None:
            await budget_usage.write_budget_snapshot({api_key.id: budget_snap}, platform_core_db)

        if self.application_may_use_api_keys(application, tenant):
            payload = self._build_cache_payload(
                api_key, str(tenant.id), {"tier_id": str(tenant.tier_id)}
            )
            await self._cache.set_api_key_cache(raw_key, ttl, payload)
            await self._persist_cache_snapshot(api_key, payload)

        logger.info(
            "API key created: name=%s application=%s permissions=%s",
            key_name, application_id, permission_ids,
        )
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
        """DB fallback for a Redis miss. ``repo`` eager-loads application/tenant so
        eligibility can be checked without further queries."""
        return await repo.get_by_api_key_if_valid(token)

    def _is_key_eligible(self, db_key: APIKey) -> bool:
        """Beyond is_active/expiry (already filtered in the DB query): the
        owning application and tenant must still allow API-key authentication."""
        if db_key.application is None:
            logger.warning(
                "API key %s has no owning application row; treating as ineligible", db_key.api_key
            )
            return False
        return self.application_may_use_api_keys(db_key.application, db_key.application.tenant)

    async def _rehydrate_cache_from_db(self, db_key: APIKey) -> dict:
        """Repopulate Redis for an eligible key found on a cache miss —
        verbatim from its persisted ``cached_data`` snapshot, the only source
        of truth for this path (write-through: cached_data is kept in sync on
        every create/update; never synthesized here — the tier_id it can
        carry isn't safe to redo on this hot path)."""
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
        *,
        caller_tenant_id: Optional[int] = None,
    ) -> None:
        if not self._is_api_key(api_key_value):
            raise ValidationError(
                message="Invalid API key format. Must be a 32-character hex string.",
                code="INVALID_API_KEY_FORMAT",
            )
        db_key = await self._repo.get_by_api_key(api_key_value)
        if not db_key:
            raise EntityNotFoundError("API key")
        if caller_tenant_id is not None:
            application = await self._applications.get_by_id_for_tenant(
                db_key.application_id, caller_tenant_id
            )
            if application is None:
                raise AuthorizationError(
                    message="You do not have permission to revoke this API key.",
                    code="UNAUTHORIZED_API_KEY_REVOCATION",
                )
        await self.revoke_by_obj(db_key)

    async def update_key(
        self,
        api_key_value: str,
        data: dict,
        *,
        caller_tenant_id: Optional[int] = None,
    ) -> APIKey:
        if not self._is_api_key(api_key_value):
            raise ValidationError(
                message="Invalid API key format. Must be a 32-character hex string.",
                code="INVALID_API_KEY_FORMAT",
            )
        db_key = await self._repo.get_by_api_key(api_key_value)
        if not db_key:
            raise EntityNotFoundError("API key")
        if caller_tenant_id is not None:
            application = await self._applications.get_by_id_for_tenant(
                db_key.application_id, caller_tenant_id
            )
            if application is None:
                raise AuthorizationError(
                    message="You do not have permission to update this API key.",
                    code="UNAUTHORIZED_API_KEY_UPDATE",
                )
        return await self.update_key_by_obj(db_key, data)

    async def revoke_by_obj(self, db_key: APIKey) -> None:
        """Revoke a key that has already been fetched and scope-verified by the caller.
        Skips the second get_by_api_key lookup that revoke_api_key() would otherwise perform."""
        await self._repo.revoke(db_key)
        await self._repo.commit()
        await self._cache.delete_api_key_cache(db_key.api_key)
        logger.info(
            "API key revoked: api_key=%s application=%s", db_key.api_key, db_key.application_id
        )

    async def update_key_by_obj(
        self,
        db_key: APIKey,
        data: dict,
        updated_by: Optional[UUID] = None,
    ) -> APIKey:
        """Update a key that has already been fetched and scope-verified by the caller.
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

        if updated_by is not None:
            data["updated_by"] = str(updated_by)

        await self._repo.update(db_key, data)
        await self._repo.commit()

        tenant_id_str: Optional[str] = None
        application = None
        tenant = None
        if self._applications is not None:
            application = await self._applications.get_by_id(db_key.application_id)
        if application is not None and self._tenants is not None:
            tenant = await self._tenants.get_by_id(application.tenant_id)
            tenant_id_str = str(application.tenant_id)
        if application is not None and self.effective_is_active(db_key, application, tenant):
            await self._refresh_redis_cache(db_key, tenant_id_str)
        else:
            # Not currently eligible (revoked, or application/tenant inactive) — Redis
            # must stay evicted, but cached_data still has to mirror the edit
            # just committed, or a later reactivation/DB-fallback rehydrate
            # would serve stale permissions/expiry.
            await self._cache.delete_api_key_cache(db_key.api_key)
            await self._persist_current_state_to_cached_data(db_key, tenant_id_str)

        await self._repo.refresh(db_key)
        logger.info(
            "API key updated: api_key=%s application=%s", db_key.api_key, db_key.application_id
        )
        return db_key

    async def list_by_application(self, application_id: int) -> list[APIKey]:
        return await self._repo.list_by_application(application_id)

    async def list_grouped(
        self,
        *,
        caller_tenant_id: Optional[int],
        application_id: Optional[int],
        offset: int = 0,
        limit: int = 100,
    ) -> list[tuple[Application, list[APIKey]]]:
        """Applications + their API keys, for GET /auth/api-keys.

        ``caller_tenant_id=None`` means the caller is a platform ADMIN
        (unscoped); otherwise the result — and any ``application_id`` filter
        — is restricted to that tenant's applications, with a uniform 404
        (APPLICATION_NOT_FOUND) whether the id doesn't exist at all or
        belongs to a different tenant. ``offset``/``limit`` page the
        platform-ADMIN unscoped listing (ApplicationRepository.list_all) —
        previously unpaginated, returning every key on the platform in one
        response; ignored for the ``application_id`` and tenant-scoped
        (a tenant's own application count is bounded in practice) cases.
        """
        if application_id is not None:
            if caller_tenant_id is not None:
                application = await self._applications.get_by_id_for_tenant(
                    application_id, caller_tenant_id
                )
            else:
                application = await self._applications.get_by_id(application_id)
            if application is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail={"code": "APPLICATION_NOT_FOUND", "message": "Application not found."},
                )
            keys = await self._repo.list_by_application(application_id)
            return [(application, keys)]

        if caller_tenant_id is not None:
            applications = await self._applications.list_by_tenant(caller_tenant_id)
        else:
            applications = await self._applications.list_all(offset=offset, limit=limit)
        app_ids = [a.id for a in applications]
        keys = await self._repo.list_by_applications(app_ids)
        keys_by_app: dict[int, list[APIKey]] = {}
        for k in keys:
            keys_by_app.setdefault(k.application_id, []).append(k)
        return [(a, keys_by_app.get(a.id, [])) for a in applications]

    async def list_all_with_applications(
        self, offset: int = 0, limit: int = 100, application_id: Optional[int] = None
    ) -> list[tuple[APIKey, Application]]:
        return await self._repo.list_all_with_applications(offset, limit, application_id)

    async def get_by_api_key(self, api_key_value: str) -> Optional[APIKey]:
        return await self._repo.get_by_api_key(api_key_value)

    async def get_by_id(self, key_id: int) -> Optional[APIKey]:
        return await self._repo.get_by_id(key_id)

    async def get_by_id_for_scope(
        self, key_id: int, caller_tenant_id: Optional[int]
    ) -> Optional[APIKey]:
        """``caller_tenant_id=None`` (platform ADMIN) is unscoped; otherwise
        the key's Application must belong to that tenant."""
        if caller_tenant_id is None:
            return await self._repo.get_by_id(key_id)
        return await self._repo.get_by_id_for_tenant(key_id, caller_tenant_id)
