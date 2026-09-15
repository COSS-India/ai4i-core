from typing import Dict, List, Optional

from pydantic import BaseModel, field_validator

from app.schemas.common import MessageMeta, SuccessResponse, SuccessResponseWithMeta
from app.schemas.enums.notification_management import (
    NotificationChannel,
    NotificationModule,
    NotificationType,
)


class ThresholdBand(BaseModel):
    """One configurable alert band: the usage percentage it fires at, and
    whether it's currently turned on. No id/name/label — a band's position
    in the ``thresholds`` list carries no meaning of its own either;
    ``percentage`` is what an Adopter Admin sets, and PATCH always replaces
    the whole list (see CatalogUpdate.thresholds) since there's no stable
    key to merge a partial update against once percentage itself is
    editable."""

    percentage: int
    active: bool


class CatalogItem(BaseModel):
    """One row of the notification/alert catalog, decorated with its
    code-side display metadata (see catalog_metadata.py). ``thresholds`` is
    omitted entirely on a NOTIFICATION row (``None``, dropped from the JSON
    response) rather than sent as an always-empty ``[]`` — that key only
    ever exists in ``config`` for ALERT-type rows (design section 6.1)."""

    id: int
    name: str
    display_name: str
    description: str
    type: NotificationType
    module: NotificationModule
    channels: List[NotificationChannel]
    recipient_roles: Dict[str, bool]
    thresholds: Optional[List[ThresholdBand]] = None


class CatalogResponse(BaseModel):
    items: List[CatalogItem]


class CatalogUpdate(BaseModel):
    """PATCH /notification-alerts/catalog/{name} body. Every field optional — only the fields
    present are changed; recipient_roles/thresholds each replace their own
    column/config-key wholesale (the mockup's checkbox group sends its whole
    current state) without disturbing the other, unset one.

    ``thresholds``, when present, must be the complete set of exactly
    THRESHOLD_BAND_COUNT bands — there is no partial/per-band PATCH, since a
    band has no stable key to merge against once its own ``percentage`` is
    editable. Renaming/reordering has no meaning either (bands are unnamed);
    an Adopter Admin edits a percentage, flips ``active``, and sends the
    whole list back."""

    channels: Optional[List[NotificationChannel]] = None
    recipient_roles: Optional[Dict[str, bool]] = None
    thresholds: Optional[List[ThresholdBand]] = None

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
    """GET /notification-alerts/catalog?type=NOTIFICATION|ALERT"""

    data: CatalogResponse


class UpdateCatalogResponse(SuccessResponseWithMeta):
    """PATCH /notification-alerts/catalog/{name}"""

    data: CatalogItem
    meta: MessageMeta
