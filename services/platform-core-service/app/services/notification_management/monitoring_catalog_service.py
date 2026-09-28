"""Monitoring alert catalog writes — the 5 MONITORING-type rows of
configs_notification_alert (error rate / latency).

Separate from catalog_service.update_catalog because monitoring alerts
follow their own configuration and recipient model: no scope (always
platform-level), Email only, recipients are ADMIN (Adopter Admin) and/or
MODERATOR, and thresholds are value + unit bands (PERCENT or SECONDS) in
notification_alert_threshold rather than metering percentages.

Selecting a role stores it in recipient_roles AND resolves it to concrete
user ids in monitoring_alert_recipient — every active, non-deleted user
currently holding that role in ai4iplatform_auth. That's a snapshot taken
at PATCH time: a user granted the role later is only picked up by the next
recipient_roles PATCH.
"""

import logging
from decimal import Decimal
from typing import Dict, List, Optional, Set

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, EntityNotFoundError, ValidationError
from app.models.notification_management.config_notification_alert import (
    ConfigNotificationAlert,
)
from app.models.notification_management.monitoring_alert_recipient import (
    MonitoringAlertRecipient,
)
from app.schemas.enums.notification_management import (
    MonitoringThresholdUnit,
    NotificationName,
    NotificationType,
)
from app.schemas.notification_management.catalog import (
    MonitoringCatalogItem,
    MonitoringCatalogUpdate,
    MonitoringThresholdBand,
)
from app.services.notification_management.cache_refresh import after_settings_write
from app.services.notification_management.catalog_metadata import (
    LEGAL_RECIPIENT_ROLES,
    MONITORING_ALERT_NAMES,
)
from app.services.notification_management.catalog_service import (
    _to_catalog_item,
    _validate_band_count,
)
from app.services.notification_management.thresholds import load_bands, replace_bands

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


def _validate_thresholds(
    row: ConfigNotificationAlert, bands: List[MonitoringThresholdBand], expected_unit: Optional[str]
) -> None:
    def invalid(message: str) -> ValidationError:
        return ValidationError(message=message, code="INVALID_THRESHOLDS")

    _validate_band_count(row.name, len(bands))
    # The unit is fixed per alert (error rates are %, latencies seconds) —
    # an Adopter Admin edits values, never what they measure.
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


async def _resolve_role_user_ids(
    auth_db: Optional[AsyncSession], roles: Set[str]
) -> Dict[str, str]:
    """{user_id: role} for every active, non-deleted user holding one of
    ``roles``. A user holding both is attributed to ADMIN (sorted first)."""
    if not roles:
        return {}
    if auth_db is None:
        raise AppError(
            message="Cannot resolve recipients — auth database is not configured.",
            code="AUTH_DB_UNAVAILABLE",
            status_code=503,
        )
    result = await auth_db.execute(
        text(
            "SELECT DISTINCT u.id::text AS user_id, r.name AS role"
            "  FROM users u"
            "  JOIN user_role ur ON ur.user_id = u.id"
            "  JOIN roles r ON r.id = ur.role_id"
            " WHERE r.name = ANY(:roles)"
            "   AND u.is_delete IS NOT TRUE"
            "   AND u.is_active IS TRUE"
            " ORDER BY role, user_id"
        ),
        {"roles": sorted(roles)},
    )
    resolved: Dict[str, str] = {}
    for row in result.all():
        resolved.setdefault(row.user_id, row.role)
    return resolved


async def _replace_recipients(
    session: AsyncSession,
    notification_id: int,
    user_roles: Dict[str, str],
    created_by: Optional[str],
) -> None:
    await session.execute(
        delete(MonitoringAlertRecipient).where(
            MonitoringAlertRecipient.notification_id == notification_id
        )
    )
    session.add_all(
        MonitoringAlertRecipient(
            notification_id=notification_id, user_id=user_id, role=role, created_by=created_by
        )
        for user_id, role in user_roles.items()
    )


async def _list_recipient_ids(session: AsyncSession, notification_id: int) -> List[str]:
    result = await session.execute(
        select(MonitoringAlertRecipient.user_id)
        .where(MonitoringAlertRecipient.notification_id == notification_id)
        .order_by(MonitoringAlertRecipient.id)
    )
    return list(result.scalars().all())


async def update_monitoring_catalog(
    session: AsyncSession,
    name: str,
    payload: MonitoringCatalogUpdate,
    *,
    auth_db: Optional[AsyncSession] = None,
    updated_by: Optional[str] = None,
) -> MonitoringCatalogItem:
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
        selected = {role for role, on in merged.items() if on}
        # Resolve before mutating anything, so a 503 from the auth DB
        # leaves the row exactly as it was.
        user_roles = await _resolve_role_user_ids(auth_db, selected)
        row.recipient_roles = merged
        await _replace_recipients(session, row.id, user_roles, updated_by)
    else:
        # Every save re-resolves the selected roles, so a user who got
        # ADMIN or MODERATOR since the last save is included. Best effort:
        # without the auth DB the stored recipients stay as they are.
        selected = {role for role, on in (row.recipient_roles or {}).items() if on}
        try:
            user_roles = await _resolve_role_user_ids(auth_db, selected)
        except Exception as exc:
            logger.warning("Monitoring recipients not refreshed for %s: %s", row.name, exc)
        else:
            await _replace_recipients(session, row.id, user_roles, updated_by)

    if payload.monitoring_thresholds is not None:
        stored = (await load_bands(session, [row.id])).get(row.id, [])
        expected_unit = stored[0].unit if stored else None
        _validate_thresholds(row, payload.monitoring_thresholds, expected_unit)
        await replace_bands(
            session,
            row.id,
            [(Decimal(str(band.value)), band.active) for band in payload.monitoring_thresholds],
            expected_unit or payload.monitoring_thresholds[0].unit.value,
            updated_by,
        )

    if updated_by is not None:
        row.updated_by = updated_by

    await session.commit()
    await session.refresh(row)

    # The snapshot carries the resolved recipient ids and the active bands.
    await after_settings_write([row.name])

    bands = await load_bands(session, [row.id])
    item = _to_catalog_item(row, bands.get(row.id, []))
    return MonitoringCatalogItem(
        **item.model_dump(), recipients=await _list_recipient_ids(session, row.id)
    )
