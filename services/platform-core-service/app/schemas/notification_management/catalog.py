from typing import Dict, List, Optional, Union

from pydantic import BaseModel, StrictBool, StrictFloat, StrictInt, field_validator

from app.schemas.common import MessageMeta, SuccessResponse, SuccessResponseWithMeta
from app.schemas.enums.notification_management import (
    MonitoringThresholdUnit,
    NotificationChannel,
    NotificationModule,
    NotificationScope,
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
    # Strict: pydantic's default lax bool coercion would otherwise accept
    # "true"/"false" (string) and silently coerce them instead of 422ing.
    active: StrictBool


class MonitoringThresholdBand(BaseModel):
    """One configurable band on a MONITORING row: the value it fires at
    (``>=``), its unit (PERCENT for error rates, SECONDS for latencies) and
    whether it's currently turned on. Stored as a row of
    notification_alert_threshold."""

    # Strict so a string ("5") or a bool (True is an int) 422s instead of
    # being silently coerced — same reasoning as ``active`` below.
    value: Union[StrictInt, StrictFloat]
    unit: MonitoringThresholdUnit
    active: StrictBool


class CatalogItem(BaseModel):
    """One row of the notification/alert catalog, decorated with its
    code-side display metadata (see catalog_metadata.py). ``thresholds`` is
    omitted entirely on a NOTIFICATION row (``None``, dropped from the JSON
    response) rather than sent as an always-empty ``[]`` — only ALERT-type
    rows have admin-editable percentage bands.

    ``scope`` is GLOBAL (applies platform-wide, no per-institution
    opt-out) or INSTITUTION (available for an institution to subscribe to
    — see app.routes.notification_subscription). ``recipient_roles`` is
    kept (not dropped) so the producer-side caches that still raw-SELECT it
    keep working until they move onto scope. Its ``"ADMIN"`` key (the
    Adopter Admin's own recipient toggle) is exactly the stored column
    value, not re-derived from ``scope`` on read — every row was backfilled
    to already be scope-consistent (True on GLOBAL, False on INSTITUTION,
    see e2a4c6b8d0f2) and PATCH keeps it that way going forward (see
    catalog_service._apply_admin_recipient_scope_invariant) — because the
    send path reads this same column directly, and a value shown here that
    the stored column disagrees with would be a lie."""

    id: int
    name: str
    display_name: str
    description: str
    type: NotificationType
    module: NotificationModule
    channels: List[NotificationChannel]
    recipient_roles: Dict[str, bool]
    scope: NotificationScope
    thresholds: Optional[List[ThresholdBand]] = None
    # MONITORING rows only; None (dropped from the response) otherwise.
    monitoring_thresholds: Optional[List[MonitoringThresholdBand]] = None


class CatalogResponse(BaseModel):
    items: List[CatalogItem]


class CatalogUpdate(BaseModel):
    """PATCH /notification-alerts/catalog/{name} body. Every field optional — only the fields
    present are changed; recipient_roles/scope/thresholds each replace
    their own value wholesale (the mockup's checkbox group
    sends its whole current state) without disturbing the other, unset
    one.

    ``recipient_roles["ADMIN"]`` (the Adopter Admin's own recipient toggle)
    is enforced against the row's effective ``scope`` regardless of what's
    sent here — see catalog_service._apply_admin_recipient_scope_invariant.

    ``thresholds``, when present, must be the complete set of 1 to 10
    bands — there is no partial/per-band PATCH, since a
    band has no stable key to merge against once its own ``percentage`` is
    editable. Renaming/reordering has no meaning either (bands are unnamed);
    an Adopter Admin edits a percentage, flips ``active``, and sends the
    whole list back."""

    channels: Optional[List[NotificationChannel]] = None
    # Strict: a plain `bool` here would let pydantic's default lax mode
    # coerce a string like "true"/"false" (or "1"/"yes"/"on"/...) into a
    # real bool instead of 422ing — silently masking a loosely-typed
    # caller's bug instead of failing fast (per this endpoint's spec).
    recipient_roles: Optional[Dict[str, StrictBool]] = None
    scope: Optional[NotificationScope] = None
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


class MonitoringCatalogUpdate(BaseModel):
    """PATCH /notification-alerts/monitoring-catalog/{name} body. Every field
    optional — only the fields present are changed. No ``scope`` (monitoring
    alerts are platform-level, never per-institution) and no ``channels``
    (Email is the only delivery channel).

    ``recipient_roles`` is a partial-update dict over ADMIN / MODERATOR —
    only the key(s) that changed need sending. Whenever it's present the
    row's resolved recipients (monitoring_alert_recipient) are rebuilt from
    every user currently holding a selected role.

    ``monitoring_thresholds``, when present, must be the complete set of
    bands, same wholesale-replace semantics as CatalogUpdate.thresholds."""

    recipient_roles: Optional[Dict[str, StrictBool]] = None
    monitoring_thresholds: Optional[List[MonitoringThresholdBand]] = None


class MonitoringCatalogItem(CatalogItem):
    """A MONITORING catalog row plus its resolved recipient user ids."""

    recipients: List[str]


# ── Route response envelopes — ``{"success": true, "data": ...}`` ──


class ListCatalogResponse(SuccessResponse):
    """GET /notification-alerts/catalog?type=NOTIFICATION|ALERT|MONITORING"""

    data: CatalogResponse


class UpdateCatalogResponse(SuccessResponseWithMeta):
    """PATCH /notification-alerts/catalog/{name}"""

    data: CatalogItem
    meta: MessageMeta


class UpdateMonitoringCatalogResponse(SuccessResponseWithMeta):
    """PATCH /notification-alerts/monitoring-catalog/{name}"""

    data: MonitoringCatalogItem
    meta: MessageMeta
