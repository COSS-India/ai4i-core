"""Schemas for GET /auth/audit-logs."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import ConfigDict, Field

from ai4i_core.audit import AuditAction, AuditEntity

from app.schemas.base import BaseSchema
from app.schemas.common import SuccessResponse


class AuditLogResponse(BaseSchema):
    """One audit row. ``message`` is the readable summary (it includes the
    reason); ``performed_by`` is the acting user's id and ``created_at`` is
    when the change happened."""

    id: int
    created_at: datetime
    entity_name: AuditEntity
    entity_id: str
    action: AuditAction
    message: Optional[str] = None
    performed_by: Optional[UUID] = None
    previous_state: Optional[dict[str, Any]] = Field(
        None, description="Entity before the change (email / phone masked)"
    )
    new_state: Optional[dict[str, Any]] = Field(
        None, description="Entity after the change (email / phone masked)"
    )
    trace_id: Optional[str] = None

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": 1042,
                    "created_at": "2026-11-03T10:15:31Z",
                    "entity_name": "TENANT",
                    "entity_id": "7",
                    "action": "STATUS_CHANGE",
                    "message": "Tenant 'Acme University' suspended. Reason: Agreement renewal pending.",
                    "performed_by": "<place your id here>",
                    "previous_state": {
                        "id": 7,
                        "name": "Asha Rao",
                        "organisation": "Acme University",
                        "email": "a***@a***.edu",
                        "phone_number": None,
                        "status": "ACTIVE",
                        "reason": None,
                        "tier_id": None,
                        "allocated_budget": None,
                        "budget_effective_from": None,
                        "budget_effective_to": None,
                    },
                    "new_state": {
                        "id": 7,
                        "name": "Asha Rao",
                        "organisation": "Acme University",
                        "email": "a***@a***.edu",
                        "phone_number": None,
                        "status": "SUSPENDED",
                        "reason": "Agreement renewal pending",
                        "tier_id": None,
                        "allocated_budget": None,
                        "budget_effective_from": None,
                        "budget_effective_to": None,
                    },
                    "trace_id": "a1b2c3d4e5f6",
                }
            ]
        }
    )


class ListAuditLogsResponse(SuccessResponse):
    """GET /auth/audit-logs"""

    data: list[AuditLogResponse]
