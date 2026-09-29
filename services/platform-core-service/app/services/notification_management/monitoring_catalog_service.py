"""Monitoring alert catalog writes — the 5 MONITORING-type rows of
configs_notification_alert (error rate / latency).

Separate from catalog_service.update_catalog because monitoring alerts
follow their own configuration and recipient model: no scope (always
platform-level), Email only, recipients are ADMIN (Adopter Admin) and/or
MODERATOR, and thresholds are value + unit bands under
config.monitoring_thresholds rather than metering percentages.

Selecting a role only stores it in recipient_roles. Who that means is
resolved at send time (ai4i_core.kafka.recipients.
resolve_monitoring_recipients), the same way metering resolves its
recipients per event — so a user granted, revoked or deactivated after the
save is reflected on the next alert with no re-save.
"""

import logging
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundError, ValidationError
from app.core.redis import get_redis_client
from app.models.notification_management.config_notification_alert import (
    ConfigNotificationAlert,
)
from app.schemas.enums.notification_management import (
    MonitoringThresholdUnit,
    NotificationName,
    NotificationType,
)
from app.schemas.notification_management.catalog import (
    CatalogItem,
    MonitoringCatalogUpdate,
    MonitoringThresholdBand,
)
from app.services.notification_management.catalog_metadata import (
    LEGAL_RECIPIENT_ROLES,
    MONITORING_ALERT_NAMES,
    THRESHOLD_BAND_COUNT,
)
from app.services.notification_management.catalog_service import (
    NOTIFICATION_ALERT_UPDATES_CHANNEL,
    _to_catalog_item,
)

logger = logging.getLogger(__name__)

MAX_PERCENT = 100


def _validate_recipient_roles(name: str, recipient_roles: Dict[str, bool]) -> None:
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


def _stored_unit(row: ConfigNotificationAlert) -> Optional[str]:
    bands = (row.config or {}).get("monitoring_thresholds") or []
    return bands[0].get("unit") if bands else None


def _validate_thresholds(
    row: ConfigNotificationAlert, bands: List[MonitoringThresholdBand]
) -> None:
    def invalid(message: str) -> ValidationError:
        return ValidationError(message=message, code="INVALID_THRESHOLDS")

    if len(bands) != THRESHOLD_BAND_COUNT:
        raise invalid(
            f"Exactly {THRESHOLD_BAND_COUNT} threshold band(s) are required for '{row.name}' "
            f"(got {len(bands)})."
        )
    # The unit is fixed per alert (error rates are %, latencies seconds) —
    # an Adopter Admin edits values, never what they measure.
    expected_unit = _stored_unit(row)
    if expected_unit is not None and any(band.unit.value != expected_unit for band in bands):
        raise invalid(f"Threshold unit for '{row.name}' must be {expected_unit}.")
    values = [band.value for band in bands]
    if len(set(values)) != len(values):
        raise invalid(f"Threshold values for '{row.name}' must be unique.")
    for band in bands:
        if band.value <= 0:
            raise invalid(f"Threshold value {band.value} for '{row.name}' must be greater than 0.")
        if band.unit == MonitoringThresholdUnit.PERCENT and band.value > MAX_PERCENT:
            raise invalid(
                f"Threshold value {band.value} for '{row.name}' must not exceed {MAX_PERCENT}%."
            )


async def update_monitoring_catalog(
    session: AsyncSession,
    name: str,
    payload: MonitoringCatalogUpdate,
    *,
    updated_by: Optional[str] = None,
) -> CatalogItem:
    """Update one MONITORING catalog row's recipient roles and/or threshold
    bands. A name that isn't a monitoring alert is a 404 here — metering
    rows are updated through PATCH /notification-alerts/catalog/{name}."""
    if name not in {n.value for n in MONITORING_ALERT_NAMES}:
        raise EntityNotFoundError(f"Monitoring alert '{name}'")

    result = await session.execute(
        select(ConfigNotificationAlert).where(ConfigNotificationAlert.name == name)
    )
    row = result.scalar_one_or_none()
    if row is None or row.type != NotificationType.MONITORING.value:
        raise EntityNotFoundError(f"Monitoring alert '{name}'")

    if payload.recipient_roles is not None:
        merged = {**(row.recipient_roles or {}), **payload.recipient_roles}
        _validate_recipient_roles(row.name, merged)
        row.recipient_roles = merged

    if payload.monitoring_thresholds is not None:
        _validate_thresholds(row, payload.monitoring_thresholds)
        config = dict(row.config or {})
        config["monitoring_thresholds"] = [
            band.model_dump(mode="json") for band in payload.monitoring_thresholds
        ]
        row.config = config

    if updated_by is not None:
        row.updated_by = updated_by

    await session.commit()
    await session.refresh(row)

    if payload.recipient_roles is not None or payload.monitoring_thresholds is not None:
        # Same best-effort cache invalidation as catalog_service.update_catalog.
        try:
            redis = get_redis_client()
            await redis.publish(NOTIFICATION_ALERT_UPDATES_CHANNEL, row.name)
        except Exception as exc:
            logger.warning(
                "Failed to publish %s update to '%s': %s",
                NOTIFICATION_ALERT_UPDATES_CHANNEL, row.name, exc,
            )

    return _to_catalog_item(row)
