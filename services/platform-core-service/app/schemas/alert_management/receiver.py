"""Pydantic request/response schemas for notification receivers.

Lifted from alert-management-service/alert_management.py:476-569. Changes:
  - BaseModel → BaseSchema (platform-core re-export).
  - Response model drops `organization`.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import ConfigDict, Field, field_validator

from app.schemas.base import BaseSchema
from app.schemas.common import (
    DeletedIdData,
    MessageMeta,
    SuccessResponse,
    SuccessResponseWithMeta,
    TotalMeta,
)
from app.schemas.enums.alert_management import VALID_RBAC_ROLES


_NOTIFICATION_RECEIVER_CREATE_EXAMPLE = {
    "category": "application",
    "severity": "critical",
    "alert_type": "latency",
    "description": "Notify platform on-call for critical application latency alerts",
    "email_to": ["oncall@example.com"],
    "email_subject_template": "[ALERT] {{ .CommonLabels.alertname }}",
    "email_body_template": "<p>{{ .CommonAnnotations.summary }}</p>",
}


class NotificationReceiverCreate(BaseSchema):
    """Create payload — auto-generates receiver name + paired routing rule on the server side."""

    model_config = ConfigDict(json_schema_extra={"example": _NOTIFICATION_RECEIVER_CREATE_EXAMPLE})

    category: str = Field(..., description="'application' or 'infrastructure'")
    severity: str = Field(..., description="'critical', 'warning', or 'info'")
    alert_type: Optional[str] = Field(None, description="Optional alert-type filter (e.g., 'latency', 'error_rate')")
    alert_names: Optional[List[str]] = Field(None, description="Optional list of alert definition names to route only those alerts within the group")
    tenant: Optional[str] = Field(None, description="Optional tenant name; routes by tenant_id and uses tenant user email")
    rule_name: Optional[str] = Field(None, description="Optional rule name; stored on the receiver and used for the auto-created routing rule")
    description: Optional[str] = Field(None, description="Human-friendly description of what this receiver is for")
    email_to: Optional[List[str]] = Field(None, description="Email addresses (required if rbac_role not provided)", min_items=1)
    rbac_role: Optional[str] = Field(None, description="RBAC role name — emails will be resolved from users with this role")
    email_subject_template: Optional[str] = Field(None, description="Email subject template")
    email_body_template: Optional[str] = Field(None, description="Email body template (HTML)")

    @field_validator("rbac_role")
    @classmethod
    def _validate_rbac_role(cls, v):
        if v is not None and v not in VALID_RBAC_ROLES:
            raise ValueError(
                f"Invalid RBAC role '{v}'. Must be one of: {', '.join(sorted(VALID_RBAC_ROLES))}"
            )
        return v

    def model_post_init(self, __context):
        """Cannot supply both email_to and rbac_role. If neither is set (and no tenant), the service layer defaults rbac_role=ADMIN."""
        if self.email_to and self.rbac_role:
            raise ValueError("Cannot provide both 'email_to' and 'rbac_role'. Use one or the other.")


_NOTIFICATION_RECEIVER_UPDATE_EXAMPLE = {
    "description": "Updated on-call distribution list",
    "email_to": ["oncall@example.com", "backup-oncall@example.com"],
    "enabled": True,
}


class NotificationReceiverUpdate(BaseSchema):
    """Patch payload — all fields optional."""

    model_config = ConfigDict(json_schema_extra={"example": _NOTIFICATION_RECEIVER_UPDATE_EXAMPLE})

    receiver_name: Optional[str] = None
    rule_name: Optional[str] = None
    description: Optional[str] = Field(None, description="Human-friendly description of what this receiver is for")
    category: Optional[str] = Field(None, description="'application' or 'infrastructure'")
    severity: Optional[str] = Field(None, description="'critical', 'warning', or 'info'")
    alert_names: Optional[List[str]] = Field(None, description="Optional list of alert definition names")
    tenant: Optional[str] = Field(None, description="Optional tenant name")
    email_to: Optional[List[str]] = Field(None, description="Email addresses (required if rbac_role not provided)", min_items=1)
    rbac_role: Optional[str] = Field(None, description="RBAC role name — resolves emails from users with this role")
    email_subject_template: Optional[str] = None
    email_body_template: Optional[str] = None
    enabled: Optional[bool] = None

    @field_validator("rbac_role")
    @classmethod
    def _validate_rbac_role(cls, v):
        if v is not None and v not in VALID_RBAC_ROLES:
            raise ValueError(
                f"Invalid RBAC role '{v}'. Must be one of: {', '.join(sorted(VALID_RBAC_ROLES))}"
            )
        return v

    @field_validator("category")
    @classmethod
    def _validate_category(cls, v):
        if v is not None and v.lower() not in ("application", "infrastructure"):
            raise ValueError("category must be 'application' or 'infrastructure'")
        return v

    @field_validator("severity")
    @classmethod
    def _validate_severity(cls, v):
        if v is not None and v.lower() not in ("critical", "warning", "info"):
            raise ValueError("severity must be 'critical', 'warning', or 'info'")
        return v

    def model_post_init(self, __context):
        """If both email_to and rbac_role are explicitly provided together, reject."""
        if self.email_to is not None or self.rbac_role is not None:
            if self.email_to and self.rbac_role:
                raise ValueError("Cannot provide both 'email_to' and 'rbac_role'. Use one or the other.")


class NotificationReceiverResponse(BaseSchema):
    """Response payload — `organization` removed per migration plan."""

    id: int
    receiver_name: str
    rule_name: Optional[str] = None
    description: Optional[str] = Field(None, description="Human-friendly description of what this receiver is for")
    category: str = Field(default="application", description="'application' or 'infrastructure'")
    severity: str = Field(default="warning", description="'critical', 'warning', or 'info'")
    email_to: List[str]
    rbac_role: Optional[str] = None
    alert_names: Optional[List[str]] = None
    tenant: Optional[str] = None
    email_subject_template: Optional[str]
    email_body_template: Optional[str]
    enabled: bool
    created_at: datetime
    updated_at: datetime


# ── Route response envelopes — ``{"success": true, "data": ..., "meta": ...}`` ──


class CreateReceiverResponse(SuccessResponseWithMeta):
    """POST /alerts/receivers"""

    data: NotificationReceiverResponse
    meta: MessageMeta


class ListReceiversResponse(SuccessResponseWithMeta):
    """GET /alerts/receivers"""

    data: List[NotificationReceiverResponse]
    meta: TotalMeta


class GetReceiverResponse(SuccessResponse):
    """GET /alerts/receivers/{receiver_id}"""

    data: NotificationReceiverResponse


class UpdateReceiverResponse(SuccessResponseWithMeta):
    """PUT /alerts/receivers/{receiver_id}"""

    data: NotificationReceiverResponse
    meta: MessageMeta


class DeleteReceiverResponse(SuccessResponseWithMeta):
    """DELETE /alerts/receivers/{receiver_id}"""

    data: DeletedIdData
    meta: MessageMeta
