"""Pydantic request/response schemas for routing rules.

Lifted from alert-management-service/alert_management.py:571-634. Changes:
  - BaseModel → BaseSchema (platform-core re-export).
  - Response model drops `organization`.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import Field

from app.schemas.base import BaseSchema
from app.schemas.common import MessageMeta, SuccessResponse, TotalMeta, DeletedIdData


class RoutingRuleCreate(BaseSchema):
    """Create payload."""

    rule_name: str = Field(..., description="Unique rule name")
    receiver_id: int = Field(..., description="ID of the notification receiver")
    match_severity: Optional[str] = Field(None, description="'critical', 'warning', 'info', or null (matches all)")
    match_category: Optional[str] = Field(None, description="'application', 'infrastructure', or null (matches all)")
    match_alert_type: Optional[str] = Field(None, description="Match alert type or null (matches all)")
    match_alert_names: Optional[List[str]] = Field(None, description="Optional list of alert names to match (alertname label)")
    match_tenant_id: Optional[str] = Field(None, description="Optional tenant_id to match (tenant label in metrics)")
    group_by: Optional[List[str]] = Field(
        default_factory=lambda: ["alertname", "category", "severity"],
        description="Labels to group by",
    )
    group_wait: str = Field(default="10s", description="Wait time before sending first notification")
    group_interval: str = Field(default="10s", description="Wait time before sending next notification")
    repeat_interval: str = Field(default="12h", description="Wait time before repeating notification")
    continue_routing: bool = Field(default=False, description="Continue to next matching rule")
    priority: int = Field(default=100, description="Priority (lower = higher priority)")


class RoutingRuleUpdate(BaseSchema):
    """Patch payload — all fields optional."""

    rule_name: Optional[str] = None
    receiver_id: Optional[int] = None
    match_severity: Optional[str] = None
    match_category: Optional[str] = None
    match_alert_type: Optional[str] = None
    match_alert_names: Optional[List[str]] = None
    match_tenant_id: Optional[str] = None
    group_by: Optional[List[str]] = None
    group_wait: Optional[str] = None
    group_interval: Optional[str] = None
    repeat_interval: Optional[str] = None
    continue_routing: Optional[bool] = None
    priority: Optional[int] = None
    enabled: Optional[bool] = None


class RoutingRuleTimingUpdate(BaseSchema):
    """Bulk timing-update payload — applies timing params to all routing rules matching the filter set."""

    category: str = Field(..., description="'application' or 'infrastructure'")
    severity: str = Field(..., description="'critical', 'warning', or 'info'")
    alert_type: Optional[str] = Field(None, description="Optional alert-type filter (e.g., 'latency', 'error_rate')")
    priority: Optional[int] = Field(None, description="Optional priority filter (lower = higher priority)")
    group_wait: Optional[str] = Field(None, description="Wait time before sending first notification")
    group_interval: Optional[str] = Field(None, description="Wait time before sending next notification")
    repeat_interval: Optional[str] = Field(None, description="Wait time before repeating notification")


class RoutingRuleResponse(BaseSchema):
    """Response payload — `organization` removed per migration plan."""

    id: int
    rule_name: str
    receiver_id: int
    match_severity: Optional[str]
    match_category: Optional[str]
    match_alert_type: Optional[str]
    match_alert_names: Optional[List[str]] = None
    match_tenant_id: Optional[str] = None
    group_by: List[str]
    group_wait: str
    group_interval: str
    repeat_interval: str
    continue_routing: bool
    priority: int
    enabled: bool
    created_at: datetime
    updated_at: datetime


class RoutingRuleTimingUpdateData(BaseSchema):
    """``data`` shape for ``PATCH /alerts/routing-rules/timing``."""

    affected: int = Field(..., description="Number of routing rules updated")


# ── Route response envelopes — ``{"success": true, "data": ..., "meta": ...}`` ──


class CreateRoutingRuleResponse(SuccessResponse[RoutingRuleResponse]):
    """POST /alerts/routing-rules"""

    meta: MessageMeta


class ListRoutingRulesResponse(SuccessResponse[List[RoutingRuleResponse]]):
    """GET /alerts/routing-rules"""

    meta: TotalMeta


class UpdateRoutingRuleTimingResponse(SuccessResponse[RoutingRuleTimingUpdateData]):
    """PATCH /alerts/routing-rules/timing"""

    meta: MessageMeta


class GetRoutingRuleResponse(SuccessResponse[RoutingRuleResponse]):
    """GET /alerts/routing-rules/{rule_id}"""


class UpdateRoutingRuleResponse(SuccessResponse[RoutingRuleResponse]):
    """PUT /alerts/routing-rules/{rule_id}"""

    meta: MessageMeta


class DeleteRoutingRuleResponse(SuccessResponse[DeletedIdData]):
    """DELETE /alerts/routing-rules/{rule_id}"""

    meta: MessageMeta
