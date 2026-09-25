from typing import List

from pydantic import BaseModel, StrictBool

from app.schemas.common import MessageMeta, SuccessResponse, SuccessResponseWithMeta
from app.schemas.enums.notification_management import NotificationChannel, NotificationScope


class SubscriptionItem(BaseModel):
    """One institution's view of one catalog row.

    ``subscribed``/``locked`` are the *effective* values for this
    institution, not the raw stored bit: a GLOBAL-scope row is always
    ``subscribed=true``/``locked=true`` (no unsubscribe option) regardless
    of whatever tenant_notification_subscription.subscribed still holds
    underneath — see subscription_service._to_subscription_item. ``locked``
    is what the UI uses to disable the subscribe/unsubscribe control."""

    notification_id: int
    name: str
    display_name: str
    scope: NotificationScope
    delivery_channel: List[NotificationChannel]
    subscribed: bool
    locked: bool
    recipients: List[str]


class SubscriptionListData(BaseModel):
    items: List[SubscriptionItem]


class SubscriptionPatch(BaseModel):
    """PATCH .../subscriptions/{notification_id} body — subscribe/
    unsubscribe. Rejected (409) when the row is currently GLOBAL-scope,
    where there is no unsubscribe option to change."""

    # Strict: pydantic's default lax bool mode would otherwise silently
    # coerce a string like "true"/"false" into a real bool instead of
    # 422ing — a loosely-typed caller's bug must fail fast, not get masked.
    subscribed: StrictBool


class SubscriptionRecipientsUpdate(BaseModel):
    """PUT .../subscriptions/{notification_id} body — the institution's
    complete list of additional recipients (user ids), replaced wholesale.
    Each id must belong to an active user of this same institution."""

    recipients: List[str]


# ── Route response envelopes — ``{"success": true, "data": ...}`` ──


class ListSubscriptionResponse(SuccessResponse):
    """GET /notification-alerts/subscriptions?tenant_id="""

    data: SubscriptionListData


class UpdateSubscriptionResponse(SuccessResponseWithMeta):
    """PATCH|PUT /notification-alerts/subscriptions/{notification_id}"""

    data: SubscriptionItem
    meta: MessageMeta
