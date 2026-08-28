"""
Application table queries.

No business logic, no Redis calls — Postgres only. There is no
Application CRUD route/service layer yet; this repository exists solely
to let API-key operations resolve/validate the application_id they're
handed (existence, tenant scope, allocation totals).
"""

from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import APIKey
from app.models.application import Application
from app.repositories.base import BaseRepository


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
        both committing over 100%."""
        result = await self._db.execute(
            select(Application).where(Application.id == application_id).with_for_update()
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

    async def list_by_tenant(self, tenant_id: int) -> list[Application]:
        result = await self._db.execute(
            select(Application)
            .where(Application.tenant_id == tenant_id)
            .order_by(Application.id)
        )
        return list(result.scalars().all())

    async def list_all(self, offset: int = 0, limit: int = 100) -> list[Application]:
        """Every application, across every tenant, paginated — the
        platform-ADMIN-only path for GET /auth/api-keys with no
        application_id filter."""
        result = await self._db.execute(
            select(Application).order_by(Application.id).offset(offset).limit(limit)
        )
        return list(result.scalars().all())

    async def sum_api_key_allocated_percentage(self, application_id: int) -> Decimal:
        """Sum of allocated_percentage across the application's active,
        non-revoked API keys — used to enforce ALLOCATION_TOTAL_EXCEEDED
        (total percentage allocated to keys under one application must not
        exceed 100).

        Distinctly named (not ``sum_allocated_percentage``) to avoid
        colliding with a same-named, differently-scoped method some other
        branch may add to this repository (e.g. one summing
        Application.allocated_percentage per tenant_id) — same file, same
        class, different table and filter column, which a generic name
        would let a merge silently pick either implementation of.

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
