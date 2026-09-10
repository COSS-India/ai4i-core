"""Notification and alert catalog reads/writes.

The catalog GET is a join in code, not a serialiser over the table: each DB
row is decorated with its display name/description/detail line from
catalog_metadata.py, which the API never exposes for editing. One function
serves both NOTIFICATION and ALERT rows, filtered by ``type``; PATCH updates
one row by ``name`` — unique, stable and meaningful, unlike the bigserial
``id`` (whose values depend on seed history and can differ across
environments).
"""

from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EntityNotFoundError, ValidationError
from app.models.notification_management.config_notification_alert import (
    ConfigNotificationAlert,
)
from app.schemas.enums.notification_management import NotificationName, NotificationType
from app.schemas.notification_management.catalog import CatalogItem, CatalogUpdate
from app.services.notification_management.catalog_metadata import (
    LEGAL_RECIPIENT_ROLES,
    MAX_THRESHOLD_KEYS,
    MAX_THRESHOLD_PERCENT,
    MIN_THRESHOLD_PERCENT,
    NOTIFICATION_METADATA,
)


def _to_catalog_item(row: ConfigNotificationAlert) -> CatalogItem:
    meta = NOTIFICATION_METADATA.get(row.name)
    is_alert = row.type == NotificationType.ALERT.value
    return CatalogItem(
        id=row.id,
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


def _merged_bool_dict(existing: Dict[str, bool], incoming: Dict[str, bool]) -> Dict[str, bool]:
    """PATCH semantics for recipient_roles/thresholds: the payload only
    needs to carry the key(s) that changed. Every key already on the row
    keeps its current value unless the payload names it, in which case it's
    set to exactly what the payload says — no key is ever dropped or reset
    to False just for being omitted."""
    return {**existing, **incoming}


def _validate_recipient_roles(name: str, recipient_roles: Dict[str, bool]) -> None:
    # All 9 catalog rows — NOTIFICATION and ALERT alike — are restricted to
    # ADMIN / TENANT ADMIN (design 6.1).
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


async def update_catalog(
    session: AsyncSession,
    name: str,
    payload: CatalogUpdate,
    *,
    updated_by: Optional[str] = None,
) -> CatalogItem:
    """Update one catalog row, looked up by its own ``name`` — the row's
    type is whatever is already stored, not something the caller asserts.

    ``thresholds`` is ALERT-only (the key only ever exists in ``config`` for
    ALERT-type rows); sending it for a NOTIFICATION row is a validation
    error. channels/recipient_roles are accepted for both types.

    recipient_roles/thresholds are partial-update dicts, not wholesale
    replacements: every key already stored on the row keeps its current
    value unless the payload names it, in which case it's set to exactly
    what the payload says."""
    # Validate against the enum in Python before it ever reaches the query:
    # `name` is arbitrary path-param text, and comparing a non-member string
    # to a Postgres ENUM column raises an invalid-input-value DB error (a
    # 500) rather than the clean 404 an unknown catalog name should be.
    try:
        NotificationName(name)
    except ValueError:
        raise EntityNotFoundError(f"Catalog entry '{name}'")

    result = await session.execute(
        select(ConfigNotificationAlert).where(ConfigNotificationAlert.name == name)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise EntityNotFoundError(f"Catalog entry '{name}'")

    if payload.thresholds is not None and row.type != NotificationType.ALERT.value:
        raise ValidationError(
            message=f"'{row.name}' is a NOTIFICATION-type entry; thresholds do not apply to it.",
            code="INVALID_THRESHOLDS",
        )

    if payload.recipient_roles is not None:
        merged = _merged_bool_dict(row.recipient_roles or {}, payload.recipient_roles)
        _validate_recipient_roles(row.name, merged)
        row.recipient_roles = merged

    if payload.thresholds is not None:
        existing_thresholds = (row.config or {}).get("thresholds", {})
        merged = _merged_bool_dict(existing_thresholds, payload.thresholds)
        _validate_thresholds(row.name, merged)
        config = dict(row.config or {})
        config["thresholds"] = merged
        row.config = config

    if payload.channels is not None:
        row.channels = [channel.value for channel in payload.channels]

    if updated_by is not None:
        row.updated_by = updated_by

    await session.commit()
    await session.refresh(row)
    return _to_catalog_item(row)
