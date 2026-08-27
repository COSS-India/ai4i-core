from decimal import Decimal
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

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
        """Load with ``SELECT … FOR UPDATE`` — guards a single row during allocation writes."""
        result = await self._db.execute(
            select(Application).where(Application.id == application_id).with_for_update()
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
            like = f"%{search.strip()}%"
            filters.append(
                or_(Application.name.ilike(like), Application.domain.ilike(like))
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

    async def list_all_for_tenant_for_update(self, tenant_id: int) -> list[Application]:
        """Lock every Application row for a tenant — used before validating the
        sum of allocation percentages, so two concurrent reallocation calls for
        the same tenant can't both read a stale total and both commit over 100%.
        """
        result = await self._db.execute(
            select(Application)
            .where(Application.tenant_id == tenant_id)
            .order_by(Application.id.asc())
            .with_for_update()
        )
        return list(result.scalars().all())

    async def sum_allocated_percentage(
        self, tenant_id: int, *, exclude_id: Optional[int] = None
    ) -> Decimal:
        filters = [Application.tenant_id == tenant_id]
        if exclude_id is not None:
            filters.append(Application.id != exclude_id)
        result = await self._db.execute(
            select(func.coalesce(func.sum(Application.allocated_percentage), 0)).where(*filters)
        )
        return Decimal(result.scalar_one())
