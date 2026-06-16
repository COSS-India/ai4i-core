"""Repository for audit_logs."""

from typing import Any, Dict, List

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pii_management.audit_log import AuditLog


class AuditLogRepository:
    """Write-mostly repository for PII redaction audit trails."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, payload: Dict[str, Any]) -> None:
        """Insert a single audit record. Callers should not await a return value."""
        log = AuditLog(
            trace_id=payload.get("trace_id"),
            tenant_id=payload.get("tenant_id"),
            domain_id=payload.get("domain_id"),
            target_context=payload.get("target_context"),
            pii_count=payload.get("pii_count"),
            processing_ms=payload.get("processing_ms"),
            trace_json=payload.get("trace_json"),
        )
        self._db.add(log)
        await self._db.commit()

    async def list_recent(self, limit: int = 50) -> List[AuditLog]:
        result = await self._db.execute(
            select(AuditLog)
            .order_by(desc(AuditLog.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())
