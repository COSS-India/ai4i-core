"""
APIKey table queries.

No business logic, no Redis calls — Postgres only.

Ownership: an API key belongs to an Application (application_id), not a
User (migration e9f0a1b2c3d4 dropped api_key.user_id in favor of
application_id). Tenant scoping therefore always goes through
Application.tenant_id, not through users.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import cast, func, or_, select, update
from sqlalchemy.dialects.postgresql import ARRAY, TEXT
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.api_key import APIKey
from app.models.application import Application
from app.models.role import Permission
from app.repositories.base import BaseRepository


class APIKeyRepository(BaseRepository):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def get_by_id(self, key_id: int) -> Optional[APIKey]:
        result = await self._db.execute(
            select(APIKey).where(APIKey.id == key_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_for_tenant(self, key_id: int, tenant_id: int) -> Optional[APIKey]:
        """Tenant-scoped lookup (via the key's Application): returns None whether
        the key doesn't exist or its application belongs to a different tenant,
        so a Tenant Admin caller cannot enumerate valid key IDs outside their tenant."""
        result = await self._db.execute(
            select(APIKey)
            .join(Application, APIKey.application_id == Application.id)
            .where(APIKey.id == key_id, Application.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def get_by_api_key(self, api_key_value: str) -> Optional[APIKey]:
        result = await self._db.execute(
            select(APIKey).where(APIKey.api_key == api_key_value)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _active_key_conditions(*, require_cached_data: bool = False) -> list:
        """Shared is_active/expiry predicate for every 'still-usable key'
        query, optionally requiring a cached_data snapshot to be present
        (the tenant/global cached_data patch-and-remove writers only touch
        already-backfilled rows)."""
        conditions = [
            APIKey.is_active.is_(True),
            or_(APIKey.expires_at.is_(None), APIKey.expires_at > datetime.now(timezone.utc)),
        ]
        if require_cached_data:
            conditions.append(APIKey.cached_data.isnot(None))
        return conditions

    async def get_by_api_key_if_valid(self, api_key_value: str) -> Optional[APIKey]:
        """Validation-hot-path lookup: eager-loads application and
        application.tenant in one query so the caller can check
        application/tenant eligibility with zero further queries. Filters
        is_active/expiry here; application/tenant eligibility itself stays a
        service-layer concern."""
        result = await self._db.execute(
            select(APIKey)
            .options(joinedload(APIKey.application).joinedload(Application.tenant))
            .where(APIKey.api_key == api_key_value, *self._active_key_conditions())
        )
        return result.unique().scalar_one_or_none()

    async def get_permission_names_by_ids(self, permission_ids: list[int]) -> dict[int, str]:
        if not permission_ids:
            return {}
        result = await self._db.execute(
            select(Permission.id, Permission.name).where(Permission.id.in_(permission_ids))
        )
        return {pid: name for pid, name in result.all()}

    async def get_permission_ids_by_names(self, permission_names: list[str]) -> dict[str, int]:
        """Resolve permission names to ids — restricted to inference
        permissions (``action == 'inference'``), the only kind an API key
        may ever hold. Without this, nothing stopped an API key from being
        created/updated with an admin permission like service.create —
        request headers carry no owning user for API-key traffic (no
        api_key.user_id any more), so any write that permission reached
        would silently attribute to no one (created_by/updated_by left
        NULL) instead of failing. A name that exists but isn't an
        inference permission is therefore treated the same as an unknown
        one by callers (_resolve_permission_names' INVALID_PERMISSION_NAMES
        check doesn't distinguish "doesn't exist" from "not inference").
        """
        if not permission_names:
            return {}
        result = await self._db.execute(
            select(Permission.name, Permission.id).where(
                Permission.name.in_(permission_names), Permission.action == "inference"
            )
        )
        return {name: pid for name, pid in result.all()}

    async def list_by_application(self, application_id: int) -> list[APIKey]:
        result = await self._db.execute(
            select(APIKey)
            .where(APIKey.application_id == application_id)
            .order_by(APIKey.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_by_applications(self, application_ids: list[int]) -> list[APIKey]:
        """Batch fetch for grouped list responses. Empty input short-circuits
        to avoid an ``IN ()`` round trip."""
        if not application_ids:
            return []
        result = await self._db.execute(
            select(APIKey)
            .where(APIKey.application_id.in_(application_ids))
            .order_by(APIKey.application_id, APIKey.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_by_tenant(self, tenant_id: int) -> list[APIKey]:
        """Every key under any Application belonging to tenant_id."""
        result = await self._db.execute(
            select(APIKey)
            .join(Application, APIKey.application_id == Application.id)
            .where(Application.tenant_id == tenant_id)
            .order_by(APIKey.application_id, APIKey.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_active_keys_for_tenant(
        self, tenant_id: int, *, after_id: int = 0, limit: int = 500
    ) -> list[APIKey]:
        """Keyset-paginated (id > after_id) active/non-expired keys for every
        application belonging to tenant_id. Used by the tenant-wide cache
        cascade operations (suspend/deactivate/reactivate, budget/quota flag
        fan-out) so a large tenant's keys are walked in bounded batches
        instead of one big IN() list."""
        result = await self._db.execute(
            select(APIKey)
            .join(Application, APIKey.application_id == Application.id)
            .where(
                Application.tenant_id == tenant_id,
                APIKey.id > after_id,
                *self._active_key_conditions(),
            )
            .order_by(APIKey.id)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_active_keys(self, offset: int = 0, limit: int = 100) -> list[APIKey]:
        """Page directly over api_keys — active, non-expired, no join through
        applications. Used for operations that need every active key across
        every tenant (e.g. the monthly quota-reset cron) so the caller
        doesn't have to issue one query per application to reach the same
        keys."""
        result = await self._db.execute(
            select(APIKey)
            .where(*self._active_key_conditions())
            .order_by(APIKey.id)
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def patch_cached_data_field_for_tenant(
        self, tenant_id: int, field: str, value: str
    ) -> int:
        """Set one top-level field inside cached_data for every active,
        non-expired, already-backfilled key belonging to tenant_id's
        applications — a single UPDATE ... FROM, not a per-key round trip.
        Keys with no cached_data snapshot yet are skipped (nothing to patch
        until the backfill/an update populates one). Returns rows touched.

        Mirrors the same field this call's Redis counterpart
        (CacheService.patch_api_key_cache_field) writes, so budget/quota
        flags survive a cache eviction instead of resetting on rehydrate.
        """
        result = await self._db.execute(
            update(APIKey)
            .where(
                APIKey.application_id == Application.id,
                Application.tenant_id == tenant_id,
                *self._active_key_conditions(require_cached_data=True),
            )
            .values(
                cached_data=func.jsonb_set(
                    APIKey.cached_data, cast([field], ARRAY(TEXT)), func.to_jsonb(value)
                )
            )
        )
        return result.rowcount

    async def patch_cached_data_field_for_keys(
        self, key_ids: list[int], field: str, value: str
    ) -> list[str]:
        """Set one top-level field inside cached_data for every id in
        key_ids that's still active, non-expired, and already-backfilled —
        one UPDATE, not a per-key round trip (the id-list analogue of
        patch_cached_data_field_for_tenant, for a caller that already has
        the exact key ids in hand instead of a tenant to walk). Returns the
        api_key values of the rows actually touched (via RETURNING), so the
        caller can mirror the same field into Redis without a separate
        SELECT to look up which ids were eligible.
        """
        if not key_ids:
            return []
        result = await self._db.execute(
            update(APIKey)
            .where(
                APIKey.id.in_(key_ids),
                *self._active_key_conditions(require_cached_data=True),
            )
            .values(
                cached_data=func.jsonb_set(
                    APIKey.cached_data, cast([field], ARRAY(TEXT)), func.to_jsonb(value)
                )
            )
            .returning(APIKey.api_key)
        )
        return list(result.scalars().all())

    async def remove_cached_data_fields_for_tenant(
        self, tenant_id: int, fields: list[str]
    ) -> int:
        """Remove multiple top-level fields from cached_data for every active,
        non-expired, already-backfilled key belonging to tenant_id's
        applications — one UPDATE ... FROM. Mirrors
        CacheService.delete_api_key_cache_fields."""
        if not fields:
            return 0
        result = await self._db.execute(
            update(APIKey)
            .where(
                APIKey.application_id == Application.id,
                Application.tenant_id == tenant_id,
                *self._active_key_conditions(require_cached_data=True),
            )
            .values(cached_data=APIKey.cached_data.op("-")(cast(fields, ARRAY(TEXT))))
        )
        return result.rowcount

    async def remove_cached_data_fields_globally(
        self, fields: list[str], *, batch_size: int = 1000
    ) -> int:
        """Remove multiple top-level fields from cached_data across every
        active, non-expired, already-backfilled key in every tenant. Used by
        the monthly quota-reset cron. Commits per batch and returns the total
        rows touched.

        Keyset-paginated (id > last_id) rather than a single table-wide UPDATE:
        at lakhs-of-keys scale one statement would hold row locks on every
        matching row for its whole duration — blocking concurrent
        billing/create writes to cached_data — build one oversized
        transaction (WAL bloat, vacuum stall, replica lag), and risk a
        statement_timeout rolling back the entire reset. Each batch locks only
        ~batch_size rows briefly then commits; the ``-`` operator is
        idempotent, so a mid-run failure resumes cleanly on the next run. This
        is the one repository method that commits on its own — batching is
        meaningless otherwise. Mirrors CacheService.delete_api_key_cache_fields_bulk."""
        if not fields:
            return 0
        total = 0
        last_id = 0
        while True:
            ids = (
                await self._db.execute(
                    select(APIKey.id)
                    .where(
                        APIKey.id > last_id,
                        *self._active_key_conditions(require_cached_data=True),
                    )
                    .order_by(APIKey.id)
                    .limit(batch_size)
                )
            ).scalars().all()
            if not ids:
                break
            result = await self._db.execute(
                update(APIKey)
                .where(APIKey.id.in_(ids))
                .values(cached_data=APIKey.cached_data.op("-")(cast(fields, ARRAY(TEXT))))
            )
            await self.commit()
            total += result.rowcount
            last_id = ids[-1]
            if len(ids) < batch_size:
                break
        return total

    async def list_all_with_applications(
        self, offset: int = 0, limit: int = 100, application_id: Optional[int] = None
    ) -> list[tuple[APIKey, Application]]:
        stmt = (
            select(APIKey, Application)
            .join(Application, APIKey.application_id == Application.id)
            .order_by(APIKey.created_at.desc())
        )
        if application_id is not None:
            stmt = stmt.where(APIKey.application_id == application_id)
        stmt = stmt.offset(offset).limit(limit)
        result = await self._db.execute(stmt)
        return list(result.all())

    async def revoke(self, api_key: APIKey) -> None:
        api_key.is_active = False
        await self._db.flush()

    async def revoke_active_for_applications(self, application_ids: list[int]) -> list[str]:
        """Bulk-revoke active keys for the given applications; return raw key values.

        Single ``UPDATE … RETURNING`` per call (no per-key flush). Callers
        must ``commit()`` before deleting Redis entries so a failed commit
        cannot leave Redis empty while ``is_active`` remains true.
        """
        if not application_ids:
            return []
        result = await self._db.execute(
            update(APIKey)
            .where(
                APIKey.application_id.in_(application_ids),
                APIKey.is_active.is_(True),
            )
            .values(is_active=False)
            .returning(APIKey.api_key)
        )
        return list(result.scalars().all())

    async def zero_allocation_for_applications(self, application_ids: list[int]) -> list[int]:
        """Bulk-zero ``allocated_budget``/``allocated_percentage`` for the
        active keys under the given Applications; return their ids.

        Used when an Application is deactivated: its own allocation is
        cleared by the caller separately (ApplicationService), and this
        clears its Keys' ceilings to match — zeroed, not NULLed, since the
        returned ids feed ``write_budget_snapshot`` and a NULL
        ``budget_usage.api_key_budget_snap`` reads as "uncapped" rather than
        "zero room" (see AllocationService._active's docstring for why a
        revoked key is excluded here — a revoked key can never spend again,
        so its stale ceiling doesn't matter; only active keys still can, so
        only they need a real ceiling written through).

        Single ``UPDATE … RETURNING`` per call, same batching rationale as
        ``revoke_active_for_applications``.
        """
        if not application_ids:
            return []
        result = await self._db.execute(
            update(APIKey)
            .where(
                APIKey.application_id.in_(application_ids),
                APIKey.is_active.is_(True),
            )
            .values(allocated_budget=Decimal("0"), allocated_percentage=Decimal("0"))
            .returning(APIKey.id)
        )
        return list(result.scalars().all())
