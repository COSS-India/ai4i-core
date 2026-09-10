"""Notification and alert catalog reads/writes.

The catalog GET is a join in code, not a serialiser over the table: each DB
row is decorated with its display name/description/detail line from
catalog_metadata.py, which the API never exposes for editing. One function
serves both NOTIFICATION and ALERT rows, filtered by ``type`` — the alert
catalog additionally supports a PATCH.
"""

from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundError, ValidationError
from app.models.notification_management.config_notification_alert import (
    ConfigNotificationAlert,
)
from app.schemas.enums.notification_management import NotificationName, NotificationType
from app.schemas.notification_management.catalog import CatalogItem, CatalogUpdate
from app.services.notification_management.catalog_metadata import (
    ALERT_LEGAL_RECIPIENT_ROLES,
    MAX_THRESHOLD_KEYS,
    MAX_THRESHOLD_PERCENT,
    MIN_THRESHOLD_PERCENT,
    NOTIFICATION_METADATA,
)


def _to_catalog_item(row: ConfigNotificationAlert) -> CatalogItem:
    meta = NOTIFICATION_METADATA.get(row.name)
    is_alert = row.type == NotificationType.ALERT.value
    return CatalogItem(
        name=row.name,
        display_name=meta.display_name if meta else row.name,
        description=meta.description if meta else "",
        type=row.type,
        module=row.module,
        channels=list(row.channels or []),
        recipient_roles=row.recipient_roles or {},
        # None (dropped from the response) on a NOTIFICATION row — that key
        # only ever exists in config for ALERT-type rows.
        thresholds=(row.config or {}).get("thresholds", {}) if is_alert else None,
    )


async def list_catalog(session: AsyncSession, catalog_type: NotificationType) -> List[CatalogItem]:
    result = await session.execute(
        select(ConfigNotificationAlert)
        .where(ConfigNotificationAlert.type == catalog_type.value)
        .order_by(ConfigNotificationAlert.id)
    )
    rows = result.scalars().all()
    return [_to_catalog_item(row) for row in rows]


def _validate_recipient_roles(name: str, recipient_roles: Dict[str, bool]) -> None:
    try:
        legal_roles = ALERT_LEGAL_RECIPIENT_ROLES.get(NotificationName(name), frozenset())
    except ValueError:
        legal_roles = frozenset()
    illegal = set(recipient_roles) - legal_roles
    if illegal:
        raise ValidationError(
            message=(
                f"Unsupported recipient role(s) for '{name}': {sorted(illegal)}. "
                f"Legal roles: {sorted(legal_roles)}."
            ),
            code="INVALID_RECIPIENT_ROLES",
        )


def _validate_thresholds(name: str, thresholds: Dict[str, bool]) -> None:
    if len(thresholds) > MAX_THRESHOLD_KEYS:
        raise ValidationError(
            message=f"At most {MAX_THRESHOLD_KEYS} threshold(s) allowed for '{name}'.",
            code="INVALID_THRESHOLDS",
        )
    for key in thresholds:
        if not key.isdigit() or not (MIN_THRESHOLD_PERCENT <= int(key) <= MAX_THRESHOLD_PERCENT):
            raise ValidationError(
                message=(
                    f"Threshold key '{key}' for '{name}' must be a whole percent between "
                    f"{MIN_THRESHOLD_PERCENT} and {MAX_THRESHOLD_PERCENT}."
                ),
                code="INVALID_THRESHOLDS",
            )


async def update_alert_catalog(
    session: AsyncSession, name: str, payload: CatalogUpdate
) -> CatalogItem:
    # Validate against the enum in Python before it ever reaches the query:
    # `name` is arbitrary path-param text, and comparing a non-member string
    # to a Postgres ENUM column raises an invalid-input-value DB error (a
    # 500) rather than the clean 404 an unknown catalog name should be.
    try:
        NotificationName(name)
    except ValueError:
        raise EntityNotFoundError(f"Alert '{name}'")

    result = await session.execute(
        select(ConfigNotificationAlert).where(ConfigNotificationAlert.name == name)
    )
    row = result.scalar_one_or_none()
    if row is None or row.type != NotificationType.ALERT.value:
        raise EntityNotFoundError(f"Alert '{name}'")

    if payload.recipient_roles is not None:
        _validate_recipient_roles(name, payload.recipient_roles)
        row.recipient_roles = payload.recipient_roles

    if payload.thresholds is not None:
        _validate_thresholds(name, payload.thresholds)
        config = dict(row.config or {})
        config["thresholds"] = payload.thresholds
        row.config = config

    if payload.channels is not None:
        row.channels = [channel.value for channel in payload.channels]

    await session.commit()
    await session.refresh(row)
    return _to_catalog_item(row)
