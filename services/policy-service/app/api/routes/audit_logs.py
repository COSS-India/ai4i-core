"""
Audit Log routes (read-only).
GET /audit-logs
GET /audit-logs/{log_id}
"""
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.schemas import AuditLogDetailOut, AuditLogListResponse, AuditLogOut, Meta
from app.services.audit_log_service import AuditLogService

router = APIRouter(prefix="/audit-logs", tags=["Audit Logs"])


def _svc(db: AsyncSession = Depends(get_db)) -> AuditLogService:
    return AuditLogService(db)


@router.get("", response_model=AuditLogListResponse, summary="Query audit logs")
async def list_audit_logs(
    tenant_id: Optional[str] = Query(None),
    policy_id: Optional[UUID] = Query(None),
    trace_id: Optional[str] = Query(None),
    from_dt: Optional[datetime] = Query(None, alias="from"),
    to_dt: Optional[datetime] = Query(None, alias="to"),
    min_pii_count: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    svc: AuditLogService = Depends(_svc),
):
    rows, total = await svc.list(
        tenant_id=tenant_id,
        policy_id=policy_id,
        trace_id=trace_id,
        from_dt=from_dt,
        to_dt=to_dt,
        min_pii_count=min_pii_count,
        page=page,
        limit=limit,
    )
    data = [AuditLogOut.model_validate(r) for r in rows]
    return AuditLogListResponse(data=data, meta=Meta(total=total, page=page, limit=limit))


@router.get("/{log_id}", response_model=AuditLogDetailOut, summary="Get full audit log with trace_json")
async def get_audit_log(log_id: UUID, svc: AuditLogService = Depends(_svc)):
    obj = await svc.get(log_id)
    return AuditLogDetailOut.model_validate(obj)
