from typing import Dict, List

from pydantic import BaseModel

from app.schemas.common import SuccessResponse
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
