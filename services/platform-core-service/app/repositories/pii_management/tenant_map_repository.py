"""Repository for tenant_pii_domain_map."""

from typing import Dict, List, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pii_management.tenant_map import TenantPiiDomainMap


class TenantMapRepository:
    """CRUD for tenant → PII domain mappings."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_all(self) -> List[TenantPiiDomainMap]:
        result = await self._db.execute(
            select(TenantPiiDomainMap).order_by(TenantPiiDomainMap.tenant_id)
        )
        return list(result.scalars().all())

    async def get_all_as_dict(self) -> Dict[str, str]:
        """Return {tenant_id: domain_id} mapping for the policy sync cache."""
        rows = await self.get_all()
        return {row.tenant_id: row.domain_id for row in rows}

    async def get_by_tenant(self, tenant_id: str) -> Optional[TenantPiiDomainMap]:
        result = await self._db.execute(
            select(TenantPiiDomainMap).where(TenantPiiDomainMap.tenant_id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def upsert(self, tenant_id: str, domain_id: str) -> TenantPiiDomainMap:
        stmt = (
            insert(TenantPiiDomainMap)
            .values(tenant_id=tenant_id, domain_id=domain_id)
            .on_conflict_do_update(
                index_elements=["tenant_id"],
                set_={"domain_id": domain_id, "updated_at": func.now()},
            )
        )
        await self._db.execute(stmt)
        await self._db.commit()
        return await self.get_by_tenant(tenant_id)

    async def delete(self, tenant_id: str) -> None:
        await self._db.execute(
            delete(TenantPiiDomainMap).where(TenantPiiDomainMap.tenant_id == tenant_id)
        )
        await self._db.commit()
