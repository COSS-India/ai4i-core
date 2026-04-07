"""Repository for TenantPolicy mapping operations (async SQLAlchemy)."""
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.orm import PiiPolicy, TenantPolicy


class TenantPolicyRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, assignment_id: UUID) -> Optional[TenantPolicy]:
        return await self.db.get(TenantPolicy, assignment_id)

    async def get_assignment(self, tenant_id: str, policy_id: UUID) -> Optional[TenantPolicy]:
        stmt = select(TenantPolicy).where(
            TenantPolicy.tenant_id == tenant_id,
            TenantPolicy.policy_id == policy_id,
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list_for_tenant(
        self, tenant_id: str, page: int = 1, limit: int = 20
    ) -> tuple[Sequence[PiiPolicy], int]:
        """
        Returns explicitly assigned policies + all active global policies.
        """
        # explicitly assigned policies for this tenant
        assigned_ids_stmt = select(TenantPolicy.policy_id).where(
            TenantPolicy.tenant_id == tenant_id
        )
        assigned_ids = (await self.db.execute(assigned_ids_stmt)).scalars().all()

        stmt = select(PiiPolicy).where(
            (PiiPolicy.policy_id.in_(assigned_ids)) | (PiiPolicy.is_global == True)  # noqa: E712
        )
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar_one()
        rows = (await self.db.execute(stmt.offset((page - 1) * limit).limit(limit))).scalars().all()
        return rows, total

    async def assign(self, tenant_id: str, policy_id: UUID) -> TenantPolicy:
        obj = TenantPolicy(tenant_id=tenant_id, policy_id=policy_id)
        self.db.add(obj)
        await self.db.commit()
        await self.db.refresh(obj)
        return obj

    async def assign_many(self, tenant_ids: Sequence[str], policy_id: UUID) -> None:
        """
        Best-effort idempotent bulk assign. Skips existing mappings.
        """
        for tenant_id in tenant_ids:
            existing = await self.get_assignment(tenant_id, policy_id)
            if existing:
                continue
            self.db.add(TenantPolicy(tenant_id=tenant_id, policy_id=policy_id))
        await self.db.commit()

    async def unassign(self, tenant_id: str, policy_id: UUID) -> bool:
        assignment = await self.get_assignment(tenant_id, policy_id)
        if not assignment:
            return False
        await self.db.delete(assignment)
        await self.db.commit()
        return True
