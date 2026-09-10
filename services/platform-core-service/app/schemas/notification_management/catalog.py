from typing import Dict, List, Optional

from pydantic import BaseModel, field_validator

from app.schemas.common import MessageMeta, SuccessResponse, SuccessResponseWithMeta
from app.schemas.enums.notification_management import (
    NotificationChannel,
    NotificationModule,
    NotificationType,
)


class NotificationCatalogItem(BaseModel):
    """One row of the notification catalog, decorated with its code-side
    display metadata (see catalog_metadata.py)."""

    name: str
    display_name: str
    description: str
    type: NotificationType
    module: NotificationModule
    channels: List[NotificationChannel]
    is_enabled: bool
    recipient_roles: Dict[str, bool]


class NotificationCatalogResponse(BaseModel):
    notifications: List[NotificationCatalogItem]


# ── Route response envelope — ``{"success": true, "data": ...}`` ──


class ListNotificationCatalogResponse(SuccessResponse):
    """GET /notifications/catalog"""

    data: NotificationCatalogResponse


# ── Alert catalog — the 2 ALERT-type rows (QUOTA_THRESHOLD, BUDGET_THRESHOLD) ──


class AlertCatalogItem(BaseModel):
    """One row of the alert catalog, decorated with its code-side display
    metadata (see catalog_metadata.py). Adds ``thresholds`` on top of
    NotificationCatalogItem's fields — the config key only ALERT-type rows
    carry (design section 6.1)."""

    name: str
    display_name: str
    description: str
    type: NotificationType
    module: NotificationModule
    channels: List[NotificationChannel]
    is_enabled: bool
    recipient_roles: Dict[str, bool]
    thresholds: Dict[str, bool]


class AlertCatalogResponse(BaseModel):
    alerts: List[AlertCatalogItem]


class AlertCatalogUpdate(BaseModel):
    """PATCH /alerts/catalog/{name} body. Every field optional — only the
    fields present are changed; recipient_roles/thresholds each replace
    their own config key wholesale (the mockup's checkbox group sends its
    whole current state) without disturbing the other, unset one."""

    is_enabled: Optional[bool] = None
    channels: Optional[List[NotificationChannel]] = None
    recipient_roles: Optional[Dict[str, bool]] = None
    thresholds: Optional[Dict[str, bool]] = None

    @field_validator("channels")
    @classmethod
    def _channels_not_empty(cls, v):
        if v is not None and len(v) == 0:
            raise ValueError(
                "channels must not be empty — at least one channel is required "
                "(ck_configs_notification_alert_channels)."
            )
        return v


# ── Route response envelopes — ``{"success": true, "data": ...}`` ──


class ListAlertCatalogResponse(SuccessResponse):
    """GET /alerts/catalog"""

    data: AlertCatalogResponse


class UpdateAlertCatalogResponse(SuccessResponseWithMeta):
    """PATCH /alerts/catalog/{name}"""

    data: AlertCatalogItem
    meta: MessageMeta
