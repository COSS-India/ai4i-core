"""Business logic for Audit Log reads (read-only)."""
from datetime import datetime
from typing import Optional, Sequence
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import PiiAuditLog
from app.repositories.audit_log_repository import AuditLogRepository


class AuditLogService:
    def __init__(self, db: AsyncSession):
        self.repo = AuditLogRepository(db)

    async def list(
        self,
        tenant_id: Optional[str],
        policy_id: Optional[UUID],
        trace_id: Optional[str],
        from_dt: Optional[datetime],
        to_dt: Optional[datetime],
        min_pii_count: Optional[int],
        page: int,
        limit: int,
    ) -> tuple[Sequence[PiiAuditLog], int]:
        return await self.repo.list(
            tenant_id=tenant_id,
            policy_id=policy_id,
            trace_id=trace_id,
            from_dt=from_dt,
            to_dt=to_dt,
            min_pii_count=min_pii_count,
            page=page,
            limit=min(limit, 200),
        )

    async def get(self, log_id: UUID) -> PiiAuditLog:
        obj = await self.repo.get(log_id)
        if not obj:
            raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Log not found"}})
        return obj
