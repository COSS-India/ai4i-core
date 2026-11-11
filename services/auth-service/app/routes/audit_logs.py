"""Audit log read route. ADMIN only (enforced at the gateway via
api_permissions.json). Reads ai4iplatform_core.audit_logs; no business logic."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from ai4i_core.audit import AuditAction, AuditEntity, AuditLog, AuditLogRepository

from app.core import pii_crypto
from app.core.exceptions import ValidationError
from app.dependencies.auth import get_current_user_id
from app.dependencies.services import get_audit_log_repository
from app.schemas.audit_log import AuditLogResponse, ListAuditLogsResponse
from app.schemas.common import error_responses
from app.utils.masking import mask_pii_in_dict

router = APIRouter(
    prefix="/audit-logs",
    tags=["Audit Logs"],
    responses=error_responses(401),
)


# Snapshots store email / phone as ciphertext (bound column values).
_PII_CONTEXTS = {
    "email": pii_crypto.EMAIL_CONTEXT,
    "phone_number": pii_crypto.PHONE_CONTEXT,
}


def _readable_state(state: Optional[dict]) -> Optional[dict]:
    """Snapshot for the response: PII decrypted, then masked as in GET /tenants."""
    if state is None:
        return None
    out = dict(state)
    for key, context in _PII_CONTEXTS.items():
        if out.get(key) is not None:
            try:
                out[key] = pii_crypto.decrypt(out[key], context)
            except Exception:  # wrong key / corrupt value: never leak ciphertext
                out[key] = None
    return mask_pii_in_dict(out)


def to_audit_log_response(row: AuditLog) -> AuditLogResponse:
    return AuditLogResponse(
        id=row.id,
        created_at=row.created_at,
        entity_name=row.entity_name,
        entity_id=row.entity_id,
        action=row.action,
        message=row.message,
        performed_by=row.performed_by,
        previous_state=_readable_state(row.previous_state),
        new_state=_readable_state(row.new_state),
        trace_id=row.trace_id,
    )


@router.get(
    "",
    response_model=ListAuditLogsResponse,
    responses=error_responses(403, 422, 503),
)
async def list_audit_logs(
    entity_name: Optional[AuditEntity] = Query(None),
    entity_id: Optional[str] = Query(None),
    action: Optional[AuditAction] = Query(None),
    from_: Optional[datetime] = Query(None, alias="from"),
    to: Optional[datetime] = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    _user_id: UUID = Depends(get_current_user_id),
    repo: AuditLogRepository = Depends(get_audit_log_repository),
):
    """List audit log rows, newest first.

    Each row's `message` is the readable summary, including the reason;
    `performed_by` is the acting user's id and `created_at` the time of the
    change. `from` is inclusive, `to` exclusive. `entity_id` requires
    `entity_name`. Example: a tenant's history is
    `?entity_name=TENANT&entity_id=7`.
    """
    if entity_id and not entity_name:
        raise ValidationError(
            message="entity_id requires entity_name.", code="INVALID_AUDIT_FILTER"
        )
    if from_ and to and from_ > to:
        raise ValidationError(message="from must be before to.", code="INVALID_AUDIT_FILTER")
    rows = await repo.list(entity_name, entity_id, action, from_, to, offset, limit)
    return ListAuditLogsResponse(data=[to_audit_log_response(r) for r in rows])
