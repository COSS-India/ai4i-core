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

    async def list_all(self) -> list[Application]:
        """Every application, across every tenant. Platform-ADMIN-only path
        (GET /auth/api-keys with no application_id filter) — unpaginated,
        matching the contract's own lack of offset/limit on that endpoint."""
        result = await self._db.execute(select(Application).order_by(Application.id))
        return list(result.scalars().all())

    async def sum_allocated_percentage(
        self, application_id: int, *, exclude_key_id: Optional[int] = None
    ) -> Decimal:
        """Sum of allocated_percentage across the application's active,
        non-revoked API keys — used to enforce ALLOCATION_TOTAL_EXCEEDED
        (total percentage allocated to keys under one application must not
        exceed 100). ``exclude_key_id`` lets an update recompute the total
        as if the key being edited didn't yet hold its old percentage."""
        conditions = [
            APIKey.application_id == application_id,
            APIKey.is_active.is_(True),
        ]
        if exclude_key_id is not None:
            conditions.append(APIKey.id != exclude_key_id)
        result = await self._db.execute(
            select(func.coalesce(func.sum(APIKey.allocated_percentage), 0)).where(
                *conditions
            )
        )
        return Decimal(result.scalar_one())
