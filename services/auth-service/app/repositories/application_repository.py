"""
Application table queries.

Two independent slices landed on this file: Application CRUD (create/list/
search/update an Application under a tenant) and API-key-scoped-to-Application
lookups (letting API-key operations resolve/validate the application_id
they're handed — existence, tenant scope, allocation totals). No business
logic, no Redis calls — Postgres only.
"""

from decimal import Decimal
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import APIKey
from app.models.application import Application
from app.repositories.base import BaseRepository


def _escape_like(value: str) -> str:
    """Escape LIKE metacharacters so a literal '%'/'_' in user input (e.g. an
    Application named "50%_off_promo") isn't treated as a wildcard — same
    escaping UserRepository.list_usernames_in_collision_family uses for the
    same reason. Pair with ``.ilike(pattern, escape="\\\\")``.
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class ApplicationRepository(BaseRepository):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def get_by_id(self, application_id: int) -> Optional[Application]:
        result = await self._db.execute(
            select(Application).where(Application.id == application_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_for_update(self, application_id: int) -> Optional[Application]:
        """Lock the application row (``SELECT ... FOR UPDATE``) for the
        current transaction — used before summing existing API-key
        allocations so two concurrent create_api_key calls under the same
        application serialize instead of both reading the same total and
        both committing over 100%.

        ``populate_existing()`` — same reasoning as
        ``TenantRepository.get_by_id_for_update``: without it, an
        application already in the session's identity map (e.g.
        ``api_key_service.create_api_key``'s earlier unlocked
        ``get_by_id``/``get_by_id_for_tenant`` lookup) is returned unchanged
        by this locked query — the lock is real, but ``allocated_budget``
        read off the result can still be the pre-lock, pre-revision value.
        """
        result = await self._db.execute(
            select(Application)
            .where(Application.id == application_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_by_id_for_tenant(
        self, application_id: int, tenant_id: int
    ) -> Optional[Application]:
        """Tenant-scoped lookup: returns None whether the application doesn't
        exist or belongs to a different tenant, so the caller cannot enumerate
        valid application IDs across tenants (matches APPLICATION_NOT_FOUND's
        uniform-404 contract)."""
        result = await self._db.execute(
            select(Application).where(
                Application.id == application_id, Application.tenant_id == tenant_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, tenant_id: int, name: str) -> Optional[Application]:
        """Case-insensitive lookup within a tenant, matching uq_applications_tenant_name_lower."""
        result = await self._db.execute(
            select(Application)
            .where(
                Application.tenant_id == tenant_id,
                func.lower(Application.name) == name.strip().lower(),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_by_tenant(self, tenant_id: int) -> list[Application]:
        result = await self._db.execute(
            select(Application)
            .where(Application.tenant_id == tenant_id)
            .order_by(Application.id)
        )
        return list(result.scalars().all())

    async def list_by_tenant_for_update(self, tenant_id: int) -> list[Application]:
        """Same as ``list_by_tenant``, but locks every row in ONE round trip
        (``SELECT ... FOR UPDATE``) instead of the caller looping
        ``get_by_id_for_update`` once per Application — used by the two
        callers that need every Application under a Tenant locked up front
        (Tenant-level Budget Allocation, and PATCH .../budget's own
        cascade), since either can end up writing any of them.
        ``ORDER BY id`` pins a consistent lock-acquisition order across
        both call sites (and across concurrent calls to either), the same
        purpose ``get_by_id_for_update``'s single-row lock serves for
        create_api_key's narrower case — without it, two concurrent calls
        locking the same Applications in different orders could deadlock
        instead of one simply waiting for the other. ``populate_existing``
        — same reasoning as ``get_by_id_for_update``: refreshes any row
        already in the session's identity map from an earlier unlocked
        read, so ``allocated_budget`` off the result is the just-locked
        value, not a stale pre-lock one.
        """
        result = await self._db.execute(
            select(Application)
            .where(Application.tenant_id == tenant_id)
            .order_by(Application.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return list(result.scalars().all())

    async def list_for_tenant(
        self,
        tenant_id: int,
        *,
        search: Optional[str] = None,
        domain: Optional[str] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[Application], int]:
        filters = [Application.tenant_id == tenant_id]
        if search:
            like = f"%{_escape_like(search.strip())}%"
            filters.append(
                or_(
                    Application.name.ilike(like, escape="\\"),
                    Application.domain.ilike(like, escape="\\"),
                )
            )
        if domain:
            filters.append(func.lower(Application.domain) == domain.strip().lower())

        count_stmt = select(func.count()).select_from(Application).where(*filters)
        total = (await self._db.execute(count_stmt)).scalar_one()

        stmt = (
            select(Application)
            .where(*filters)
            .order_by(func.lower(Application.name).asc(), Application.id.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all()), total

    async def list_all(self, offset: int = 0, limit: int = 100) -> list[Application]:
        """Every application, across every tenant, paginated — the
        platform-ADMIN-only path for GET /auth/api-keys with no
        application_id filter."""
        result = await self._db.execute(
            select(Application).order_by(Application.id).offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def sum_allocated_percentage(self, tenant_id: int) -> Decimal:
        """Sum of allocated_percentage across a tenant's Applications — used
        to enforce ALLOCATION_TOTAL_EXCEEDED when creating/reallocating an
        Application's share of its Institution's budget."""
        result = await self._db.execute(
            select(func.coalesce(func.sum(Application.allocated_percentage), 0)).where(
                Application.tenant_id == tenant_id
            )
        )
        return Decimal(result.scalar_one())

    async def sum_api_key_allocated_percentage(self, application_id: int) -> Decimal:
        """Sum of allocated_percentage across the application's active,
        non-revoked API keys — used to enforce ALLOCATION_TOTAL_EXCEEDED
        (total percentage allocated to keys under one application must not
        exceed 100).

        Distinctly named (not ``sum_allocated_percentage``, which sums
        Application.allocated_percentage per tenant_id — same file, same
        class, different table and filter column) so a merge can't silently
        pick one implementation over the other.

        No ``exclude_key_id``/edit-recompute parameter: allocated_percentage
        cannot be edited after creation (UpdateAPIKeyRequest has no such
        field and forbids extra ones), so there's no update path that would
        need to exclude a key's own prior value from this sum.

        Callers should hold a row lock on the application (see
        ``get_by_id_for_update``) before calling this and before writing a
        new key's allocated_percentage, so two concurrent creates under the
        same application serialize instead of both summing the same total.
        """
        result = await self._db.execute(
            select(func.coalesce(func.sum(APIKey.allocated_percentage), 0)).where(
                APIKey.application_id == application_id,
                APIKey.is_active.is_(True),
            )
        )
        return Decimal(result.scalar_one())
