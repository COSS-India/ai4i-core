"""Pydantic schemas for alert history (read-only audit log of triggered alerts).

Source service accepted the Alertmanager v4 webhook as a raw dict and returned
plain row dicts. We add typed response models here so consumers (portal) get a
documented shape; the webhook endpoint itself still accepts `dict` since
Alertmanager's payload is large and deeply nested.

The `organization` column from the source table is dropped per the migration
plan (all organization-related logic removed).
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import Field

from app.schemas.base import BaseSchema


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


class AlertHistoryWebhookResponse(BaseSchema):
    """Acknowledgement returned to Alertmanager after recording a webhook payload."""

    status: str = "ok"
    recorded: int = Field(0, description="Number of alert rows inserted from this webhook batch")
