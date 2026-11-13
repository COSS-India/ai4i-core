"""Read access to ``audit_logs``."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai4i_core.audit.enums import AuditAction, AuditEntity
from ai4i_core.audit.models import AuditLog


class AuditLogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._db = session

    async def list(
        self,
        entity_name: Optional[AuditEntity] = None,
        entity_id: Optional[str] = None,
        action: Optional[AuditAction] = None,
        from_: Optional[datetime] = None,
        to_: Optional[datetime] = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[AuditLog]:
        """Rows matching every given filter, newest first.

        ``from_`` is inclusive (``created_at >= from_``), ``to_`` exclusive.
        """
        stmt = select(AuditLog)
        if entity_name is not None:
            stmt = stmt.where(AuditLog.entity_name == AuditEntity(entity_name).value)
        if entity_id is not None:
            stmt = stmt.where(AuditLog.entity_id == str(entity_id))
        if action is not None:
            stmt = stmt.where(AuditLog.action == AuditAction(action).value)
        if from_ is not None:
            stmt = stmt.where(AuditLog.created_at >= from_)
        if to_ is not None:
            stmt = stmt.where(AuditLog.created_at < to_)
        stmt = (
            stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list((await self._db.execute(stmt)).scalars().all())
