from typing import Dict, List, Optional

from pydantic import BaseModel, field_validator

from app.schemas.common import MessageMeta, SuccessResponse, SuccessResponseWithMeta
from app.schemas.enums.notification_management import (
    NotificationChannel,
    NotificationModule,
    NotificationType,
)


class CatalogItem(BaseModel):
    """One row of the notification/alert catalog, decorated with its
    code-side display metadata (see catalog_metadata.py). ``thresholds`` is
    omitted entirely on a NOTIFICATION row (``None``, dropped from the JSON
    response) rather than sent as an always-empty ``{}`` — that key only
    ever exists in ``config`` for ALERT-type rows (design section 6.1)."""

    name: str
    display_name: str
    description: str
    type: NotificationType
    module: NotificationModule
    channels: List[NotificationChannel]
    recipient_roles: Dict[str, bool]
    thresholds: Optional[Dict[str, bool]] = None


class CatalogResponse(BaseModel):
    items: List[CatalogItem]


class CatalogUpdate(BaseModel):
    """PATCH /catalog/{name} body. Every field optional — only the fields
    present are changed; recipient_roles/thresholds each replace their own
    column/config-key wholesale (the mockup's checkbox group sends its whole
    current state) without disturbing the other, unset one."""

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


class ListCatalogResponse(SuccessResponse):
    """GET /catalog?type=NOTIFICATION|ALERT"""

    data: CatalogResponse


class UpdateCatalogResponse(SuccessResponseWithMeta):
    """PATCH /alerts/catalog/{name}"""

    data: CatalogItem
    meta: MessageMeta
