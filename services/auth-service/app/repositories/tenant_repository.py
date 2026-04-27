from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant, TenantStatus


class TenantRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, tenant_id: UUID) -> Optional[Tenant]:
        result = await self._db.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[Tenant]:
        result = await self._db.execute(
            select(Tenant).where(Tenant.email == email)
        )
        return result.scalar_one_or_none()

    async def get_by_organisation(self, organisation: str) -> Optional[Tenant]:
        result = await self._db.execute(
            select(Tenant).where(Tenant.organisation == organisation).limit(1)
        )
        return result.scalar_one_or_none()

    async def create(self, tenant: Tenant) -> Tenant:
        self._db.add(tenant)
        await self._db.flush()
        return tenant

    async def update(self, tenant: Tenant, data: dict) -> Tenant:
        for key, value in data.items():
            if hasattr(tenant, key) and value is not None:
                setattr(tenant, key, value)
        await self._db.flush()
        return tenant

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

    async def commit(self) -> None:
        await self._db.commit()
