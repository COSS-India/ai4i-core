"""Institution Admin's view of, and control over, its Metering
Notifications and Alerts subscriptions.

A GLOBAL-scope catalog row is always effectively subscribed for every
institution, with no unsubscribe option — that's computed at read time from
the catalog row's own ``scope``, never stored. An INSTITUTION-scope row's
subscription state and recipients live in tenant_notification_subscription,
one row per (notification, tenant); a missing row (a tenant created after
the seed migration, say) reads as "unsubscribed, no recipients" rather than
404ing — row absence means unsubscribed by design (see the model's
docstring).

Changing a catalog row's own ``scope`` (app.services.notification_management.
catalog_service.update_catalog) never touches this table — the stored
``subscribed``/``recipients`` simply carry through underneath whichever
scope is currently in effect.
"""

import logging
from typing import List, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, EntityNotFoundError, ValidationError
from app.core.redis import get_redis_client
from app.models.notification_management.config_notification_alert import ConfigNotificationAlert
from app.models.notification_management.tenant_notification_subscription import (
    TenantNotificationSubscription,
)
from app.schemas.enums.notification_management import NotificationScope, NotificationType
from app.schemas.notification_management.subscription import SubscriptionItem
from app.services.notification_management.catalog_metadata import NOTIFICATION_METADATA

logger = logging.getLogger(__name__)

# Same channel catalog_service.update_catalog publishes to — a scope change
# matters to a subscription reader too (it flips whether the stored bit is
# even consulted), so this reuses rather than duplicates the wiring.
NOTIFICATION_ALERT_UPDATES_CHANNEL = "notification_alert_updates"


def _to_subscription_item(
    catalog_row: ConfigNotificationAlert,
    sub_row: Optional[TenantNotificationSubscription],
) -> SubscriptionItem:
    meta = NOTIFICATION_METADATA.get(catalog_row.name)
    is_global = catalog_row.scope == NotificationScope.GLOBAL.value
    stored_subscribed = bool(sub_row.subscribed) if sub_row is not None else False
    recipients = list(sub_row.recipients or []) if sub_row is not None else []
    return SubscriptionItem(
        notification_id=catalog_row.id,
        name=catalog_row.name,
        display_name=meta.display_name if meta else catalog_row.name,
        scope=catalog_row.scope,
        delivery_channel=list(catalog_row.channels or []),
        subscribed=True if is_global else stored_subscribed,
        locked=is_global,
        recipients=recipients,
    )


async def list_subscriptions(
    session: AsyncSession,
    *,
    tenant_id: str,
    catalog_type: Optional[NotificationType] = None,
) -> List[SubscriptionItem]:
    query = select(ConfigNotificationAlert).order_by(ConfigNotificationAlert.id)
    if catalog_type is not None:
        query = query.where(ConfigNotificationAlert.type == catalog_type.value)
    catalog_rows = (await session.execute(query)).scalars().all()

    sub_result = await session.execute(
        select(TenantNotificationSubscription).where(
            TenantNotificationSubscription.tenant_id == tenant_id
        )
    )
    subs_by_notification_id = {row.notification_id: row for row in sub_result.scalars().all()}

    return [
        _to_subscription_item(row, subs_by_notification_id.get(row.id))
        for row in catalog_rows
    ]


async def _get_catalog_row(session: AsyncSession, notification_id: int) -> ConfigNotificationAlert:
    result = await session.execute(
        select(ConfigNotificationAlert).where(ConfigNotificationAlert.id == notification_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise EntityNotFoundError(f"Catalog entry '{notification_id}'")
    return row


async def _get_or_create_subscription_row(
    session: AsyncSession, notification_id: int, tenant_id: str
) -> TenantNotificationSubscription:
    result = await session.execute(
        select(TenantNotificationSubscription).where(
            TenantNotificationSubscription.notification_id == notification_id,
            TenantNotificationSubscription.tenant_id == tenant_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        row = TenantNotificationSubscription(
            notification_id=notification_id,
            tenant_id=tenant_id,
            subscribed=False,
            recipients=[],
        )
        session.add(row)
    return row


async def _notify_producers(name: str) -> None:
    # Best-effort, same framing as catalog_service.update_catalog's own
    # publish: a cache falls back to its last known value if this fails.
    try:
        redis = get_redis_client()
        await redis.publish(NOTIFICATION_ALERT_UPDATES_CHANNEL, name)
    except Exception as exc:
        logger.warning(
            "Failed to publish %s update to '%s': %s",
            NOTIFICATION_ALERT_UPDATES_CHANNEL, name, exc,
        )


async def update_subscription_state(
    session: AsyncSession,
    *,
    tenant_id: str,
    notification_id: int,
    subscribed: bool,
    updated_by: Optional[str] = None,
) -> SubscriptionItem:
    """Institution Admin subscribe/unsubscribe toggle — INSTITUTION-scope
    rows only. A GLOBAL-scope row has no unsubscribe option (it's always
    subscribed for every institution), so toggling it is a 409, not a
    silent no-op."""
    catalog_row = await _get_catalog_row(session, notification_id)
    if catalog_row.scope == NotificationScope.GLOBAL.value:
        raise AppError(
            message=(
                f"'{catalog_row.name}' is Global-scope — every institution is subscribed "
                "with no option to unsubscribe."
            ),
            code="GLOBAL_SCOPE_SUBSCRIPTION_LOCKED",
            status_code=409,
        )

    sub_row = await _get_or_create_subscription_row(session, notification_id, tenant_id)
    sub_row.subscribed = subscribed
    if updated_by is not None:
        sub_row.updated_by = updated_by

    await session.commit()
    await session.refresh(sub_row)
    await _notify_producers(catalog_row.name)
    return _to_subscription_item(catalog_row, sub_row)


async def _validate_recipients_belong_to_tenant(
    auth_db: Optional[AsyncSession], tenant_id: str, recipients: List[str]
) -> None:
    if not tenant_id.isdigit():
        raise ValidationError(message=f"Invalid tenant_id '{tenant_id}'.", code="INVALID_TENANT_ID")
    if auth_db is None:
        raise AppError(
            message="Cannot validate recipients — auth database is not configured.",
            code="AUTH_DB_UNAVAILABLE",
            status_code=503,
        )

    result = await auth_db.execute(
        text(
            "SELECT id::text FROM users"
            " WHERE tenant_id = :tenant_id"
            "   AND is_delete IS NOT TRUE"
            "   AND is_active IS TRUE"
            "   AND id::text = ANY(:recipients)"
        ),
        {"tenant_id": int(tenant_id), "recipients": recipients},
    )
    found = {row[0] for row in result.all()}
    unknown = [r for r in recipients if r not in found]
    if unknown:
        raise ValidationError(
            message=f"Recipient(s) not found in this institution: {unknown}.",
            code="INVALID_RECIPIENTS",
        )


async def update_subscription_recipients(
    session: AsyncSession,
    *,
    tenant_id: str,
    notification_id: int,
    recipients: List[str],
    updated_by: Optional[str] = None,
    auth_db: Optional[AsyncSession] = None,
) -> SubscriptionItem:
    """Wholesale-replace the institution's recipients — not scope-gated
    (AC: recipients added while a row is Global stay intact if it later
    reverts to Institution scope, so adding them while Global must also be
    allowed). Each id must be an active, non-deleted user of this tenant —
    auth_db is the cross-database session onto ai4iplatform_auth (see
    app.core.database.get_auth_db_optional); recipients can't be validated
    from platform-core-service's own database."""
    catalog_row = await _get_catalog_row(session, notification_id)

    if recipients:
        await _validate_recipients_belong_to_tenant(auth_db, tenant_id, recipients)

    sub_row = await _get_or_create_subscription_row(session, notification_id, tenant_id)
    sub_row.recipients = recipients
    if updated_by is not None:
        sub_row.updated_by = updated_by

    await session.commit()
    await session.refresh(sub_row)
    return _to_subscription_item(catalog_row, sub_row)
