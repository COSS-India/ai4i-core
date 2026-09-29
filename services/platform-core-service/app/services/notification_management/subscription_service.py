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
catalog_service.update_catalog) touches this table in exactly one
direction: entering INSTITUTION scope from GLOBAL resets every tenant's
``subscribed`` to False, unconditionally (an institution must always
actively re-subscribe after that flip). Going the other way (INSTITUTION
-> GLOBAL) touches nothing — the stored ``subscribed`` simply carries
through underneath, unread while GLOBAL is in effect. ``recipients`` is
never touched by a scope change in either direction.
"""

import logging
from typing import Dict, List, Optional, Sequence

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, EntityNotFoundError, ValidationError
from app.models.notification_management.config_notification_alert import ConfigNotificationAlert
from app.models.notification_management.notification_alert_threshold import NotificationAlertThreshold
from app.models.notification_management.tenant_notification_subscription import (
    TenantNotificationSubscription,
)
from app.schemas.enums.notification_management import NotificationScope, NotificationType
from app.schemas.notification_management.catalog import ThresholdBand
from app.schemas.notification_management.subscription import SubscriptionItem
from app.services.notification_management.catalog_metadata import NOTIFICATION_METADATA
from app.services.notification_management.cache_refresh import after_subscription_write
from app.services.notification_management.thresholds import load_bands

logger = logging.getLogger(__name__)


async def _alert_bands(
    session: AsyncSession, catalog_rows: Sequence[ConfigNotificationAlert]
) -> Dict[int, List[NotificationAlertThreshold]]:
    """Editable bands of the ALERT rows only — no query for NOTIFICATION rows."""
    return await load_bands(
        session, [row.id for row in catalog_rows if row.type == NotificationType.ALERT.value]
    )


def _to_subscription_item(
    catalog_row: ConfigNotificationAlert,
    sub_row: Optional[TenantNotificationSubscription],
    bands: Sequence[NotificationAlertThreshold] = (),
) -> SubscriptionItem:
    meta = NOTIFICATION_METADATA.get(catalog_row.name)
    is_global = catalog_row.scope == NotificationScope.GLOBAL.value
    is_alert = catalog_row.type == NotificationType.ALERT.value
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
        # Same value as CatalogItem.thresholds — None (dropped from the
        # response) on a NOTIFICATION row, see catalog_service._to_catalog_item.
        thresholds=(
            [ThresholdBand(percentage=int(band.band_value), active=band.active) for band in bands]
            if is_alert
            else None
        ),
    )


async def list_subscriptions(
    session: AsyncSession,
    *,
    tenant_id: str,
    catalog_type: Optional[NotificationType] = None,
) -> List[SubscriptionItem]:
    # MONITORING rows are platform-level (no tenant, no subscription) — never
    # on the institution surface, with or without ?type=.
    query = (
        select(ConfigNotificationAlert)
        .where(ConfigNotificationAlert.type != NotificationType.MONITORING.value)
        .order_by(ConfigNotificationAlert.id)
    )
    if catalog_type is not None:
        query = query.where(ConfigNotificationAlert.type == catalog_type.value)
    catalog_rows = (await session.execute(query)).scalars().all()

    sub_result = await session.execute(
        select(TenantNotificationSubscription).where(
            TenantNotificationSubscription.tenant_id == tenant_id
        )
    )
    subs_by_notification_id = {row.notification_id: row for row in sub_result.scalars().all()}
    bands = await _alert_bands(session, catalog_rows)

    return [
        _to_subscription_item(row, subs_by_notification_id.get(row.id), bands.get(row.id, []))
        for row in catalog_rows
    ]


async def _get_catalog_row(session: AsyncSession, notification_id: int) -> ConfigNotificationAlert:
    result = await session.execute(
        select(ConfigNotificationAlert).where(ConfigNotificationAlert.id == notification_id)
    )
    row = result.scalar_one_or_none()
    # Same exclusion as list_subscriptions: an institution can't subscribe
    # to, or add recipients on, a MONITORING row.
    if row is None or row.type == NotificationType.MONITORING.value:
        raise EntityNotFoundError(f"Catalog entry '{notification_id}'")
    return row


async def _get_or_create_subscription_row(
    session: AsyncSession, notification_id: int, tenant_id: str
) -> TenantNotificationSubscription:
    """INSERT ... ON CONFLICT DO NOTHING before the SELECT, not a
    SELECT-then-conditionally-INSERT — a tenant created after the seed
    migration has no row yet, and two concurrent first writes for the same
    (notification_id, tenant_id) would otherwise both see no row, both try
    to insert, and the loser would 500 on
    uq_tenant_notification_subscription_identity. The ON CONFLICT makes the
    insert itself race-safe; the SELECT afterward is guaranteed to find a
    row either way."""
    await session.execute(
        pg_insert(TenantNotificationSubscription)
        .values(
            notification_id=notification_id,
            tenant_id=tenant_id,
            subscribed=False,
            recipients=[],
        )
        .on_conflict_do_nothing(
            index_elements=["notification_id", "tenant_id"],
        )
    )
    result = await session.execute(
        select(TenantNotificationSubscription).where(
            TenantNotificationSubscription.notification_id == notification_id,
            TenantNotificationSubscription.tenant_id == tenant_id,
        )
    )
    return result.scalar_one()


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
    await after_subscription_write([tenant_id])
    bands = await _alert_bands(session, [catalog_row])
    return _to_subscription_item(catalog_row, sub_row, bands.get(catalog_row.id, []))


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
    await after_subscription_write([tenant_id])
    bands = await _alert_bands(session, [catalog_row])
    return _to_subscription_item(catalog_row, sub_row, bands.get(catalog_row.id, []))
