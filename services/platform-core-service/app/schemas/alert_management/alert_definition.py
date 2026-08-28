"""Pydantic request/response schemas for alert definitions.

Lifted from alert-management-service/alert_management.py:382-474. Two
deliberate changes from the source:
  - `BaseModel` → platform-core's `BaseSchema` (re-export from shared lib).
  - The `organization` field is removed from the response model; all
    organization-related logic is being dropped from alerting per the
    migration plan.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import ConfigDict, Field

from app.schemas.base import BaseSchema
from app.schemas.common import (
    DeletedIdData,
    MessageMeta,
    SuccessResponse,
    SuccessResponseWithMeta,
    TotalMeta,
)


class AlertAnnotation(BaseSchema):
    """Alert annotation key/value pair."""

    key: str = Field(..., description="Annotation key (summary, description, impact, action)")
    value: str = Field(..., description="Annotation value")


_ALERT_DEFINITION_CREATE_EXAMPLE = {
    "name": "HighLatency",
    "description": "Fires when inference request latency exceeds threshold",
    "threshold_value": 2.5,
    "threshold_unit": "s",
    "category": "application",
    "severity": "critical",
    "urgency": "high",
    "alert_type": "Latency",
    "scope": "per_service",
    "service": ["nmt", "asr"],
    "evaluation_interval": "30s",
    "for_duration": "5m",
    "enabled": True,
    "annotations": [
        {"key": "summary", "value": "High latency detected on {{ $labels.service }}"},
        {"key": "action", "value": "Check Triton backend health and scale if needed"},
    ],
}


class AlertDefinitionCreate(BaseSchema):
    """Create payload. PromQL is built server-side from either alert_type+threshold
    OR (sub_category + signal + signal_metric + condition_operator + threshold)."""

    model_config = ConfigDict(json_schema_extra={"example": _ALERT_DEFINITION_CREATE_EXAMPLE})

    name: str = Field(..., description="Alert name (e.g., 'HighLatency')")
    description: Optional[str] = Field(None, description="Alert description")
    threshold_value: float = Field(..., description="Threshold value (seconds for latency; percent for error_rate/CPU/Memory/Disk)")
    threshold_unit: str = Field(..., description="'ms' or 's' for latency (ms is converted to seconds in PromQL); '%' for error rate / infrastructure")
    category: str = Field(default="application", description="'application' or 'infrastructure'")
    severity: str = Field(..., description="'critical', 'warning', or 'info'")
    urgency: str = Field(default="medium", description="'high', 'medium', or 'low'")
    alert_type: Optional[str] = Field(None, description="App: 'Latency' or 'Error Rate'. Infra: 'CPU', 'Memory', 'Disk'. Required unless using sub_category/signal/signal_metric path.")
    sub_category: Optional[str] = Field(None, description="Sub-category filtered by category (e.g. 'Performance', 'Availability')")
    signal: Optional[str] = Field(None, description="Monitoring signal type (e.g. 'Latency', 'Error rate')")
    signal_metric: Optional[str] = Field(None, description="Specific metric within the selected signal (e.g. 'Latency P50')")
    condition_operator: Optional[str] = Field(None, description="Comparison operator: '>', '>=', '<', '<='")
    scope: Optional[str] = Field(None, description="Scope (e.g., 'all_services', 'per_service')")
    service: Optional[List[str]] = Field(None, description="Optional list of inference task names (e.g. 'nmt', 'asr'); scopes the generated PromQL to those tasks via the endpoint label (/api/v1/inference/<task>). Omit to alert across all inference endpoints.")
    evaluation_interval: str = Field(default="30s", description="Prometheus evaluation interval")
    for_duration: str = Field(default="5m", description="Duration before alert fires")
    enabled: Optional[bool] = Field(default=True, description="Whether the alert definition is enabled")
    annotations: Optional[List[AlertAnnotation]] = Field(default_factory=list, description="Alert annotations")

    def model_post_init(self, __context):
        """Require either alert_type or the full (sub_category, signal, signal_metric, condition_operator) tuple."""
        new_path = all([self.sub_category, self.signal, self.signal_metric, self.condition_operator])
        if not new_path and not self.alert_type:
            raise ValueError(
                "Either provide alert_type or all of sub_category, signal, signal_metric, condition_operator"
            )

        if self.threshold_unit.strip().lower() in {"%", "percent", "percentage"}:
            if not (0 <= self.threshold_value <= 100):
                raise ValueError(
                    f"threshold_value must be between 0 and 100 when threshold_unit is '{self.threshold_unit}'"
                )


_ALERT_DEFINITION_UPDATE_EXAMPLE = {
    "threshold_value": 3.0,
    "threshold_unit": "s",
    "severity": "warning",
    "enabled": True,
}


class AlertDefinitionUpdate(BaseSchema):
    """Patch payload — every field optional."""

    model_config = ConfigDict(json_schema_extra={"example": _ALERT_DEFINITION_UPDATE_EXAMPLE})

    description: Optional[str] = None
    threshold_value: Optional[float] = None
    threshold_unit: Optional[str] = None
    category: Optional[str] = None
    severity: Optional[str] = None
    urgency: Optional[str] = None
    alert_type: Optional[str] = None
    sub_category: Optional[str] = None
    signal: Optional[str] = None
    signal_metric: Optional[str] = None
    condition_operator: Optional[str] = None
    scope: Optional[str] = None
    service: Optional[List[str]] = Field(None, description="Inference task names (e.g. 'nmt', 'asr') to scope the rule's endpoint selector to.")
    evaluation_interval: Optional[str] = None
    for_duration: Optional[str] = None
    enabled: Optional[bool] = None
    annotations: Optional[List[AlertAnnotation]] = None

    def model_post_init(self, __context):
        if (
            self.threshold_unit is not None
            and self.threshold_value is not None
            and self.threshold_unit.strip().lower() in {"%", "percent", "percentage"}
        ):
            if not (0 <= self.threshold_value <= 100):
                raise ValueError(
                    f"threshold_value must be between 0 and 100 when threshold_unit is '{self.threshold_unit}'"
                )


class AlertDefinitionResponse(BaseSchema):
    """Response payload — `organization` removed per migration plan."""

    id: int
    name: str
    description: Optional[str]
    promql_expr: str
    threshold_value: Optional[float] = None
    threshold_unit: Optional[str] = None
    category: str
    severity: str
    urgency: str
    alert_type: Optional[str]
    sub_category: Optional[str] = None
    signal: Optional[str] = None
    signal_metric: Optional[str] = None
    condition_operator: Optional[str] = None
    scope: Optional[str]
    service: Optional[List[str]] = None
    evaluation_interval: str
    for_duration: str
    enabled: bool
    created_at: datetime
    updated_at: datetime
    annotations: List[AlertAnnotation] = Field(default_factory=list)


# ── Route response envelopes — ``{"success": true, "data": ..., "meta": ...}`` ──


class CreateAlertDefinitionResponse(SuccessResponseWithMeta):
    """POST /alerts/definitions"""

    data: AlertDefinitionResponse
    meta: MessageMeta


class ListAlertDefinitionsResponse(SuccessResponseWithMeta):
    """GET /alerts/definitions"""

    data: List[AlertDefinitionResponse]
    meta: TotalMeta


class GetAlertDefinitionResponse(SuccessResponse):
    """GET /alerts/definitions/{alert_id}"""

    data: AlertDefinitionResponse


class UpdateAlertDefinitionResponse(SuccessResponseWithMeta):
    """PUT /alerts/definitions/{alert_id}"""

    data: AlertDefinitionResponse
    meta: MessageMeta


class DeleteAlertDefinitionResponse(SuccessResponseWithMeta):
    """DELETE /alerts/definitions/{alert_id}"""

    data: DeletedIdData
    meta: MessageMeta


class ToggleAlertDefinitionResponse(SuccessResponseWithMeta):
    """PATCH /alerts/definitions/{alert_id}/enabled"""

    data: AlertDefinitionResponse
    meta: MessageMeta
