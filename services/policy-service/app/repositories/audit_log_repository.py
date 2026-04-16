"""Repository for PiiAuditLog read-only operations (async SQLAlchemy)."""
from datetime import datetime
from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import PiiAuditLog


class AuditLogRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get(self, log_id: UUID) -> Optional[PiiAuditLog]:
        return await self.db.get(PiiAuditLog, log_id)

    async def list(
        self,
        tenant_id: Optional[str] = None,
        policy_id: Optional[UUID] = None,
        trace_id: Optional[str] = None,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
        min_pii_count: Optional[int] = None,
        page: int = 1,
        limit: int = 50,
    ) -> tuple[Sequence[PiiAuditLog], int]:
        stmt = select(PiiAuditLog)
        if tenant_id:
            stmt = stmt.where(PiiAuditLog.tenant_id == tenant_id)
        if policy_id:
            stmt = stmt.where(PiiAuditLog.policy_id == policy_id)
        if trace_id:
            stmt = stmt.where(PiiAuditLog.trace_id == trace_id)
        if from_dt:
            stmt = stmt.where(PiiAuditLog.created_at >= from_dt)
        if to_dt:
            stmt = stmt.where(PiiAuditLog.created_at <= to_dt)
        if min_pii_count is not None:
            stmt = stmt.where(PiiAuditLog.pii_count >= min_pii_count)

        stmt = stmt.order_by(PiiAuditLog.created_at.desc())
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self.db.execute(count_stmt)).scalar_one()
        rows = (await self.db.execute(stmt.offset((page - 1) * limit).limit(limit))).scalars().all()
        return rows, total
