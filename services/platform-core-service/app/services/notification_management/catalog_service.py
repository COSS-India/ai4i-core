"""Notification and alert catalog reads/writes.

The catalog GET is a join in code, not a serialiser over the table: each DB
row is decorated with its display name/description/detail line from
catalog_metadata.py, which the API never exposes for editing, and with its
threshold bands from notification_alert_threshold. One function serves every
catalog type, filtered by ``type``; PATCH updates one row by ``name`` —
unique, stable and meaningful, unlike the bigserial ``id`` (whose values
depend on seed history and can differ across environments).

After every write commits, the shared settings snapshot is rebuilt in Redis
and an invalidation is published (cache_refresh), so every producer sees
the change at once.
"""

import logging
from decimal import Decimal
from typing import Dict, List, Optional, Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ai4i_core.kafka import RecipientRole

from app.core.exceptions import EntityNotFoundError, ValidationError
from app.models.notification_management.config_notification_alert import (
    ConfigNotificationAlert,
)
from app.models.notification_management.notification_alert_threshold import (
    NotificationAlertThreshold,
)
from app.models.notification_management.tenant_notification_subscription import (
    TenantNotificationSubscription,
)
from app.schemas.enums.notification_management import (
    NotificationName,
    NotificationScope,
    NotificationType,
    ThresholdUnit,
)
from app.schemas.notification_management.catalog import (
    CatalogItem,
    CatalogUpdate,
    MonitoringThresholdBand,
    ThresholdBand,
)
from app.services.notification_management.cache_refresh import (
    after_settings_write,
    after_subscription_write,
)
from app.services.notification_management.catalog_metadata import (
    LEGAL_RECIPIENT_ROLES,
    MAX_THRESHOLD_BANDS,
    MAX_THRESHOLD_PERCENT,
    MIN_THRESHOLD_BANDS,
    MIN_THRESHOLD_PERCENT,
    NOTIFICATION_METADATA,
)
from app.services.notification_management.thresholds import load_bands, replace_bands

logger = logging.getLogger(__name__)


def _number(value: Decimal):
    """80.0000 -> 80, 1.5000 -> 1.5 for the API's band values."""
    return int(value) if value == value.to_integral_value() else float(value)


def _apply_admin_recipient_scope_invariant(
    recipient_roles: Dict[str, bool], scope: str
) -> Dict[str, bool]:
    """Ties the ``"ADMIN"`` key (the Adopter Admin's own recipient toggle)
    to ``scope``: overridable while GLOBAL, forced off while INSTITUTION —
    an Institution-scope row is never delivered to the Adopter Admin as
    such, delivery for it is governed by tenant_notification_subscription
    instead. Applied on every write, never re-derived on read: the send
    path reads the stored recipient_roles column directly."""
    result = dict(recipient_roles)
    if scope == NotificationScope.INSTITUTION.value:
        result[RecipientRole.ADMIN.value] = False
    else:
        result.setdefault(RecipientRole.ADMIN.value, False)
    return result


def _to_catalog_item(
    row: ConfigNotificationAlert, bands: Sequence[NotificationAlertThreshold] = ()
) -> CatalogItem:
    meta = NOTIFICATION_METADATA.get(row.name)
    is_alert = row.type == NotificationType.ALERT.value
    is_monitoring = row.type == NotificationType.MONITORING.value
    return CatalogItem(
        id=row.id,
        name=row.name,
        display_name=meta.display_name if meta else row.name,
        description=meta.description if meta else "",
        type=row.type,
        module=row.module,
        channels=list(row.channels or []),
        # The stored value, as-is — see _apply_admin_recipient_scope_invariant.
        recipient_roles=row.recipient_roles or {},
        scope=row.scope,
        # None (dropped from the response) unless the row is ALERT /
        # MONITORING. The fixed band of the EXHAUSTED rows is not editable
        # and not shown.
        thresholds=(
            [ThresholdBand(percentage=int(band.band_value), active=band.active) for band in bands]
            if is_alert
            else None
        ),
        monitoring_thresholds=(
            [
                MonitoringThresholdBand(value=_number(band.band_value), unit=band.unit, active=band.active)
                for band in bands
            ]
            if is_monitoring
            else None
        ),
    )


async def list_catalog(session: AsyncSession, catalog_type: NotificationType) -> List[CatalogItem]:
    result = await session.execute(
        select(ConfigNotificationAlert)
        .where(ConfigNotificationAlert.type == catalog_type.value)
        .order_by(ConfigNotificationAlert.id)
    )
    rows = result.scalars().all()
    bands = await load_bands(session, [row.id for row in rows])
    return [_to_catalog_item(row, bands.get(row.id, [])) for row in rows]


def _validate_recipient_roles(name: str, recipient_roles: Dict[str, bool]) -> None:
    # NOTIFICATION and ALERT rows are restricted to ADMIN / TENANT ADMIN
    # (design 6.1). MONITORING rows never reach here — update_catalog 404s
    # them; monitoring_catalog_service validates their ADMIN / MODERATOR.
    legal_roles = LEGAL_RECIPIENT_ROLES[NotificationName(name)]
    illegal = set(recipient_roles) - legal_roles
    if illegal:
        raise ValidationError(
            message=(
                f"Unsupported recipient role(s) for '{name}': {sorted(illegal)}. "
                f"Legal roles: {sorted(legal_roles)}."
            ),
            code="INVALID_RECIPIENT_ROLES",
        )


def _validate_band_count(name: str, count: int) -> None:
    if not MIN_THRESHOLD_BANDS <= count <= MAX_THRESHOLD_BANDS:
        raise ValidationError(
            message=(
                f"'{name}' holds {MIN_THRESHOLD_BANDS} to {MAX_THRESHOLD_BANDS} threshold band(s) "
                f"(got {count})."
            ),
            code="INVALID_THRESHOLDS",
        )


def _validate_thresholds(name: str, thresholds: List[ThresholdBand]) -> None:
    _validate_band_count(name, len(thresholds))
    percentages = [band.percentage for band in thresholds]
    if len(set(percentages)) != len(percentages):
        raise ValidationError(
            message=f"Threshold percentages for '{name}' must be unique.",
            code="INVALID_THRESHOLDS",
        )
    for band in thresholds:
        if not (MIN_THRESHOLD_PERCENT <= band.percentage <= MAX_THRESHOLD_PERCENT):
            raise ValidationError(
                message=(
                    f"Threshold percentage {band.percentage} for '{name}' must be a whole percent "
                    f"between {MIN_THRESHOLD_PERCENT} and {MAX_THRESHOLD_PERCENT}."
                ),
                code="INVALID_THRESHOLDS",
            )


async def update_catalog(
    session: AsyncSession,
    name: str,
    payload: CatalogUpdate,
    *,
    updated_by: Optional[str] = None,
) -> CatalogItem:
    """Update one catalog row, looked up by its own ``name`` — the row's
    type is whatever is already stored, not something the caller asserts.

    ``thresholds`` is ALERT-only; sending it for any other row is a
    validation error. It replaces the row's whole band list (1 to 10 bands)
    and severities are recounted from the top. channels/recipient_roles/scope
    are accepted for every type.

    recipient_roles is a partial-update dict: every key already stored keeps
    its value unless the payload names it — except ``"ADMIN"``, which is
    re-derived from the row's effective scope afterward.

    A ``scope`` PATCH that transitions GLOBAL -> INSTITUTION also resets
    every tenant's ``tenant_notification_subscription.subscribed`` to False,
    unconditionally. Recipients are left untouched. A no-op PATCH that
    resends the row's current scope does not trigger this."""
    # Validate against the enum in Python before it ever reaches the query:
    # comparing a non-member string to a Postgres ENUM column raises a DB
    # error (a 500) rather than the clean 404 an unknown name should be.
    try:
        NotificationName(name)
    except ValueError:
        raise EntityNotFoundError(f"Catalog entry '{name}'")

    result = await session.execute(
        select(ConfigNotificationAlert).where(ConfigNotificationAlert.name == name)
    )
    row = result.scalar_one_or_none()
    # MONITORING rows have their own model (no scope, Email only, ADMIN /
    # MODERATOR with resolved recipients) and are written only through
    # monitoring_catalog_service — same 404 it returns for metering names.
    if row is None or row.type == NotificationType.MONITORING.value:
        raise EntityNotFoundError(f"Catalog entry '{name}'")

    if payload.thresholds is not None and row.type != NotificationType.ALERT.value:
        raise ValidationError(
            message=f"'{row.name}' is a {row.type}-type entry; thresholds do not apply to it.",
            code="INVALID_THRESHOLDS",
        )

    previous_scope = row.scope
    if payload.scope is not None:
        row.scope = payload.scope.value

    reset_tenant_ids: List[str] = []
    if (
        payload.scope is not None
        and payload.scope.value == NotificationScope.INSTITUTION.value
        and previous_scope != NotificationScope.INSTITUTION.value
    ):
        reset_values = {"subscribed": False}
        if updated_by is not None:
            reset_values["updated_by"] = updated_by
        reset = await session.execute(
            update(TenantNotificationSubscription)
            .where(TenantNotificationSubscription.notification_id == row.id)
            .values(**reset_values)
            .returning(TenantNotificationSubscription.tenant_id)
        )
        reset_tenant_ids = [str(tenant_id) for tenant_id in reset.scalars().all()]

    if payload.recipient_roles is not None:
        merged = {**(row.recipient_roles or {}), **payload.recipient_roles}
        _validate_recipient_roles(row.name, merged)
        row.recipient_roles = merged

    # Re-applied unconditionally — a scope-only PATCH into INSTITUTION must
    # still clear a previously-true ADMIN flag.
    row.recipient_roles = _apply_admin_recipient_scope_invariant(row.recipient_roles or {}, row.scope)

    if payload.thresholds is not None:
        _validate_thresholds(row.name, payload.thresholds)
        await replace_bands(
            session,
            row.id,
            [(Decimal(band.percentage), band.active) for band in payload.thresholds],
            ThresholdUnit.PERCENT.value,
            updated_by,
        )

    if payload.channels is not None:
        row.channels = [channel.value for channel in payload.channels]

    if updated_by is not None:
        row.updated_by = updated_by

    await session.commit()
    await session.refresh(row)

    await after_settings_write([row.name])
    if reset_tenant_ids:
        await after_subscription_write(reset_tenant_ids)

    bands = await load_bands(session, [row.id])
    return _to_catalog_item(row, bands.get(row.id, []))
