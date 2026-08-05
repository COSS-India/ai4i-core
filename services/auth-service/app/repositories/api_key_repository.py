"""
APIKey table queries.

No business logic, no Redis calls — Postgres only.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import cast, func, or_, select, update
from sqlalchemy.dialects.postgresql import ARRAY, TEXT
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.api_key import APIKey
from app.models.role import Permission
from app.models.user import User
from app.repositories.base import BaseRepository


class APIKeyRepository(BaseRepository):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def get_by_id(self, key_id: int) -> Optional[APIKey]:
        result = await self._db.execute(
            select(APIKey).where(APIKey.id == key_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_for_owner(self, key_id: int, user_id: UUID) -> Optional[APIKey]:
        """Ownership-scoped lookup: returns None whether the key doesn't exist or belongs
        to a different user, so the caller cannot enumerate valid key IDs."""
        result = await self._db.execute(
            select(APIKey).where(APIKey.id == key_id, APIKey.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_api_key(self, api_key_value: str) -> Optional[APIKey]:
        result = await self._db.execute(
            select(APIKey).where(APIKey.api_key == api_key_value)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _active_key_conditions(*, require_cached_data: Optional[bool] = None) -> list:
        """Shared is_active/expiry predicate for every 'still-usable key'
        query, optionally combined with a cached_data presence/absence
        filter. ``require_cached_data``: None = don't filter on it, True =
        require present, False = require absent."""
        conditions = [
            APIKey.is_active.is_(True),
            or_(APIKey.expires_at.is_(None), APIKey.expires_at > datetime.now(timezone.utc)),
        ]
        if require_cached_data is True:
            conditions.append(APIKey.cached_data.isnot(None))
        elif require_cached_data is False:
            conditions.append(APIKey.cached_data.is_(None))
        return conditions

    async def get_by_api_key_if_valid(self, api_key_value: str) -> Optional[APIKey]:
        """Validation-hot-path lookup: eager-loads user and user.tenant in one
        query so the caller can check owner/tenant eligibility with zero
        further queries. Filters is_active/expiry here; owner/tenant
        eligibility itself stays a service-layer concern."""
        result = await self._db.execute(
            select(APIKey)
            .options(joinedload(APIKey.user).joinedload(User.tenant))
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
        if not permission_names:
            return {}
        result = await self._db.execute(
            select(Permission.name, Permission.id).where(Permission.name.in_(permission_names))
        )
        return {name: pid for name, pid in result.all()}

    async def list_by_user(self, user_id: UUID) -> list[APIKey]:
        result = await self._db.execute(
            select(APIKey)
            .where(APIKey.user_id == user_id)
            .order_by(APIKey.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_active_keys(self, offset: int = 0, limit: int = 100) -> list[APIKey]:
        """Page directly over api_keys — active, non-expired, no join through
        users. Used for operations that need every active key across every
        tenant (e.g. the monthly quota-reset cron) so the caller doesn't have
        to issue one query per user to reach the same keys."""
        result = await self._db.execute(
            select(APIKey)
            .where(*self._active_key_conditions())
            .order_by(APIKey.id)
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_active_without_cached_data(
        self, after_id: int = 0, limit: int = 500
    ) -> list[APIKey]:
        """Active, non-expired keys still missing their cached_data snapshot —
        keyset-paginated on id (not offset): the backfill mutates cached_data
        as it goes, which would make an offset-based page skip rows on the
        next query since the filtered set shrinks underneath it. Eager-loads
        user/tenant for the eligibility check and payload backfill."""
        result = await self._db.execute(
            select(APIKey)
            .options(joinedload(APIKey.user).joinedload(User.tenant))
            .where(
                APIKey.id > after_id,
                *self._active_key_conditions(require_cached_data=False),
            )
            .order_by(APIKey.id)
            .limit(limit)
        )
        return list(result.unique().scalars().all())

    async def patch_cached_data_field_for_tenant(
        self, tenant_id: int, field: str, value: str
    ) -> int:
        """Set one top-level field inside cached_data for every active,
        non-expired, already-backfilled key belonging to tenant_id's users —
        a single UPDATE ... FROM, not a per-key round trip. Keys with no
        cached_data snapshot yet are skipped (nothing to patch until the
        backfill/an update populates one). Returns rows touched.

        Mirrors the same field this call's Redis counterpart
        (CacheService.patch_api_key_cache_field) writes, so budget/quota
        flags survive a cache eviction instead of resetting on rehydrate.
        """
        result = await self._db.execute(
            update(APIKey)
            .where(
                APIKey.user_id == User.id,
                User.tenant_id == tenant_id,
                *self._active_key_conditions(require_cached_data=True),
            )
            .values(
                cached_data=func.jsonb_set(
                    APIKey.cached_data, cast([field], ARRAY(TEXT)), func.to_jsonb(value)
                )
            )
        )
        return result.rowcount

    async def remove_cached_data_fields_for_tenant(
        self, tenant_id: int, fields: list[str]
    ) -> int:
        """Remove multiple top-level fields from cached_data for every active,
        non-expired, already-backfilled key belonging to tenant_id's users —
        one UPDATE ... FROM. Mirrors CacheService.delete_api_key_cache_fields."""
        if not fields:
            return 0
        result = await self._db.execute(
            update(APIKey)
            .where(
                APIKey.user_id == User.id,
                User.tenant_id == tenant_id,
                *self._active_key_conditions(require_cached_data=True),
            )
            .values(cached_data=APIKey.cached_data.op("-")(cast(fields, ARRAY(TEXT))))
        )
        return result.rowcount

    async def remove_cached_data_fields_globally(self, fields: list[str]) -> int:
        """Remove multiple top-level fields from cached_data across every
        active, non-expired, already-backfilled key in every tenant — one
        UPDATE, no per-page pagination needed (unlike the Redis side, which
        must chunk for pipelining). Used by the monthly quota-reset cron.
        Mirrors CacheService.delete_api_key_cache_fields_bulk."""
        if not fields:
            return 0
        result = await self._db.execute(
            update(APIKey)
            .where(*self._active_key_conditions(require_cached_data=True))
            .values(cached_data=APIKey.cached_data.op("-")(cast(fields, ARRAY(TEXT))))
        )
        return result.rowcount

    async def list_all_with_users(self, offset: int = 0, limit: int = 100) -> list[tuple[APIKey, User]]:
        result = await self._db.execute(
            select(APIKey, User)
            .join(User, APIKey.user_id == User.id)
            .order_by(APIKey.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.all())

    async def revoke(self, api_key: APIKey) -> None:
        api_key.is_active = False
        await self._db.flush()

    async def revoke_active_for_users(self, user_ids: list[UUID]) -> list[str]:
        """Bulk-revoke active keys for the given users; return raw key values.

        Single ``UPDATE … RETURNING`` per call (no per-key flush). Callers
        must ``commit()`` before deleting Redis entries so a failed commit
        cannot leave Redis empty while ``is_active`` remains true.
        """
        if not user_ids:
            return []
        result = await self._db.execute(
            update(APIKey)
            .where(
                APIKey.user_id.in_(user_ids),
                APIKey.is_active.is_(True),
            )
            .values(is_active=False)
            .returning(APIKey.api_key)
        )
        return list(result.scalars().all())
