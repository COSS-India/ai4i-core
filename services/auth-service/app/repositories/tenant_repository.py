from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant, TenantStatus
from app.repositories.base import BaseRepository


class TenantRepository(BaseRepository):
    def __init__(self, db: AsyncSession) -> None:
        super().__init__(db)

    async def get_by_id(self, tenant_id: int) -> Optional[Tenant]:
        result = await self._db.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id_for_update(self, tenant_id: int) -> Optional[Tenant]:
        """Load tenant with ``SELECT … FOR UPDATE`` (blocks concurrent status changes)."""
        result = await self._db.execute(
            select(Tenant).where(Tenant.id == tenant_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[Tenant]:
        result = await self._db.execute(
            select(Tenant).where(Tenant.email == email)
        )
        return result.scalar_one_or_none()

    async def get_by_organisation(self, organisation: str) -> Optional[Tenant]:
        result = await self._db.execute(
            select(Tenant).where(func.lower(Tenant.organisation) == organisation.lower()).limit(1)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        offset: int = 0,
        limit: int = 100,
        status: Optional[TenantStatus] = None,
    ) -> list[Tenant]:
        stmt = select(Tenant)
        if status is not None:
            stmt = stmt.where(Tenant.status == status)
        stmt = (
            stmt.order_by(func.lower(Tenant.organisation).asc(), Tenant.id.asc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
