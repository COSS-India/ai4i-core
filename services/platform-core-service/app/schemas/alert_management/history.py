"""Pydantic schemas for alert history (read-only audit log of triggered alerts).

Source service accepted the Alertmanager v4 webhook as a raw dict and returned
plain row dicts. We add typed models here so both the webhook request body and
the portal-facing responses get a documented shape.

The `organization` column from the source table is dropped per the migration
plan (all organization-related logic removed).
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import BaseSchema
from app.schemas.common import SuccessResponseWithMeta


class AlertHistoryItem(BaseSchema):
    """One row from the alert_history table."""

    id: int
    alert_name: str
    category: str
    severity: str
    triggered_at: datetime
    resolved_at: Optional[datetime] = None
    status: str
    receiver: str
    notified_display: Optional[str] = None
    tenant: Optional[str] = None
    labels: Optional[Dict[str, Any]] = None
    annotations: Optional[Dict[str, Any]] = None
    fingerprint: Optional[str] = None
    created_at: datetime


class AlertHistoryListResponse(BaseSchema):
    """Paginated list response for GET /alerts/history."""

    items: List[AlertHistoryItem] = Field(default_factory=list)
    total: int


# ── Alertmanager webhook request body ───────────────────────────────────────
# https://prometheus.io/docs/alerting/latest/configuration/#webhook_config
#
# Every field is optional and extra keys are allowed: AlertHistoryService.
# record_from_webhook is deliberately tolerant of a malformed/partial payload
# (it falls back to "unknown"/"firing"/skips an alert rather than erroring),
# and this is an unauthenticated endpoint Alertmanager itself calls — a strict
# model that 422s on an unexpected shape would turn a delivery hiccup into a
# dropped alert instead of a best-effort partial record.


class AlertmanagerLabels(BaseSchema):
    """Prometheus label set on an alert/group. Only the labels this platform's own
    alert rules set are named below — Alertmanager attaches whatever labels the
    firing rule defines, so any other key is still accepted and preserved."""

    model_config = ConfigDict(extra="allow")

    alertname: Optional[str] = None
    severity: Optional[str] = Field(None, description="'critical', 'warning', or 'info'")
    category: Optional[str] = Field(None, description="'application' or 'infrastructure'")
    tenant: Optional[str] = None


class AlertmanagerAnnotations(BaseSchema):
    """Annotations on an alert/group. Only the keys this platform's own alert
    rules set are named below — any other annotation is still accepted and
    preserved."""

    model_config = ConfigDict(extra="allow")

    summary: Optional[str] = None
    description: Optional[str] = None
    impact: Optional[str] = None
    action: Optional[str] = None


class AlertmanagerWebhookAlert(BaseSchema):
    """One entry in the top-level ``alerts`` array of an Alertmanager webhook."""

    model_config = ConfigDict(extra="allow")

    status: Optional[str] = Field(None, description="'firing' or 'resolved'")
    labels: AlertmanagerLabels = Field(default_factory=AlertmanagerLabels)
    annotations: AlertmanagerAnnotations = Field(default_factory=AlertmanagerAnnotations)
    startsAt: Optional[str] = Field(None, description="ISO 8601 timestamp the alert started firing")
    endsAt: Optional[str] = Field(
        None, description="ISO 8601 timestamp the alert resolved; '0001-01-01T00:00:00Z' while still firing"
    )
    generatorURL: Optional[str] = None
    fingerprint: Optional[str] = Field(None, description="Alertmanager's stable identity hash for this alert")


_ALERTMANAGER_WEBHOOK_EXAMPLE = {
    "version": "4",
    "groupKey": '{}:{alertname="HighLatency"}',
    "truncatedAlerts": 0,
    "status": "firing",
    "receiver": "platform-oncall",
    "groupLabels": {"alertname": "HighLatency"},
    "commonLabels": {"alertname": "HighLatency", "severity": "critical", "category": "application"},
    "commonAnnotations": {
        "summary": "High latency detected",
        "action": "Check Triton backend health and scale if needed",
    },
    "externalURL": "https://alertmanager.example.com",
    "alerts": [
        {
            "status": "firing",
            "labels": {"alertname": "HighLatency", "severity": "critical", "category": "application"},
            "annotations": {
                "summary": "High latency detected",
                "description": "P95 latency exceeded 2.5s for 5m",
            },
            "startsAt": "2026-08-28T10:00:00Z",
            "endsAt": "0001-01-01T00:00:00Z",
            "generatorURL": "https://prometheus.example.com/graph?g0.expr=...",
            "fingerprint": "abc123def456",
        }
    ],
}


class AlertmanagerWebhookPayload(BaseSchema):
    """POST /alerts/history/webhook — Alertmanager v4 webhook body."""

    model_config = ConfigDict(extra="allow", json_schema_extra={"examples": [_ALERTMANAGER_WEBHOOK_EXAMPLE]})

    version: Optional[str] = None
    groupKey: Optional[str] = None
    truncatedAlerts: Optional[int] = None
    status: Optional[str] = Field(None, description="'firing' or 'resolved' — group-level status")
    receiver: Optional[str] = None
    groupLabels: AlertmanagerLabels = Field(default_factory=AlertmanagerLabels)
    commonLabels: AlertmanagerLabels = Field(default_factory=AlertmanagerLabels)
    commonAnnotations: AlertmanagerAnnotations = Field(default_factory=AlertmanagerAnnotations)
    externalURL: Optional[str] = None
    alerts: List[AlertmanagerWebhookAlert] = Field(default_factory=list)


class AlertHistoryWebhookResponse(BaseSchema):
    """Acknowledgement returned to Alertmanager after recording a webhook payload."""

    status: str = "ok"
    recorded: int = Field(0, description="Number of alert rows inserted from this webhook batch")


class AlertHistoryListMeta(BaseModel):
    """``meta`` shape for ``GET /alerts/history`` — pagination info alongside the page of items."""

    total: int
    limit: int
    offset: int


class ListAlertHistoryResponse(SuccessResponseWithMeta):
    """GET /alerts/history

    Note: ``data`` is the flat page of items (not the ``{items, total}`` shape
    of ``AlertHistoryListResponse`` above) — pagination info lives in ``meta``,
    matching what ``AlertHistoryService.list`` + the route actually return.
    """

    data: List[AlertHistoryItem]
    meta: AlertHistoryListMeta
