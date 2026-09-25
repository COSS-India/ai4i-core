"""Notification and alert catalog reads/writes.

The catalog GET is a join in code, not a serialiser over the table: each DB
row is decorated with its display name/description/detail line from
catalog_metadata.py, which the API never exposes for editing. One function
serves both NOTIFICATION and ALERT rows, filtered by ``type``; PATCH updates
one row by ``name`` — unique, stable and meaningful, unlike the bigserial
``id`` (whose values depend on seed history and can differ across
environments).
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
    NotificationName,
    NotificationScope,
    NotificationType,
)
from app.schemas.notification_management.catalog import CatalogItem, CatalogUpdate, ThresholdBand
from app.services.notification_management.catalog_metadata import (
    LEGAL_RECIPIENT_ROLES,
    MAX_THRESHOLD_PERCENT,
    MIN_THRESHOLD_PERCENT,
    NOTIFICATION_METADATA,
    THRESHOLD_BAND_COUNT,
)

logger = logging.getLogger(__name__)

# payperuse_consumer's in-memory threshold-bands cache subscribes to this
# channel and refreshes the one row named in the message — see
# services/kafka-consumers/consumers/payperuse_consumer/_thresholds.py.
# Mirrors this service's own pii "policy_updates" channel (app/routes/pii.py).
NOTIFICATION_ALERT_UPDATES_CHANNEL = "notification_alert_updates"


def _parse_thresholds(raw) -> List[ThresholdBand]:
    """Accepts either shape config.thresholds has ever been stored in:
    the current list of {percentage, active} bands, or the pre-migration
    dict keyed by percent-as-string ({"70": false, ...}). ai4iplatform_core
    has multiple outstanding Alembic heads on release-2.7 at the time this
    was written, so `alembic upgrade head` cannot be relied on to have run
    a3f5c7e9b1d3 — a row still holding the old shape must degrade to a
    correct read, not 500."""
    if raw is None:
        return []
    if isinstance(raw, dict):
        return [
            ThresholdBand(percentage=int(percent), active=bool(active))
            for percent, active in raw.items()
        ]
    return [ThresholdBand(**band) for band in raw]


def _apply_admin_recipient_scope_invariant(
    recipient_roles: Dict[str, bool], scope: str
) -> Dict[str, bool]:
    """Ties the ``"ADMIN"`` key (the Adopter Admin's own recipient toggle)
    to ``scope``, per design: defaults to selected and can be overridden
    while GLOBAL; forced off while INSTITUTION — an Institution-scope row
    is never delivered to the Adopter Admin as such, delivery for it is
    governed by tenant_notification_subscription instead. Applied on every
    read and every write so a row can't drift out of this invariant (e.g.
    a stale ``ADMIN: true`` left over from before a GLOBAL->INSTITUTION
    scope change)."""
    result = dict(recipient_roles)
    if scope == NotificationScope.INSTITUTION.value:
        result["ADMIN"] = False
    else:
        result.setdefault("ADMIN", True)
    return result


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
        recipient_roles=_apply_admin_recipient_scope_invariant(row.recipient_roles or {}, row.scope),
        scope=row.scope,
        # None (dropped from the response) on a NOTIFICATION row — that key
        # only ever exists in config for ALERT-type rows.
        thresholds=(
            _parse_thresholds((row.config or {}).get("thresholds"))
            if is_alert
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
    return [_to_catalog_item(row) for row in rows]


def _merged_bool_dict(existing: Dict[str, bool], incoming: Dict[str, bool]) -> Dict[str, bool]:
    """PATCH semantics for recipient_roles: the payload only needs to carry
    the key(s) that changed. Every key already on the row keeps its current
    value unless the payload names it, in which case it's set to exactly
    what the payload says — no key is ever dropped or reset to False just
    for being omitted. (thresholds does not use this — see update_catalog.)"""
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


def _validate_thresholds(name: str, thresholds: List[ThresholdBand]) -> None:
    if len(thresholds) != THRESHOLD_BAND_COUNT:
        raise ValidationError(
            message=(
                f"Exactly {THRESHOLD_BAND_COUNT} threshold band(s) are required for '{name}' "
                f"(got {len(thresholds)})."
            ),
            code="INVALID_THRESHOLDS",
        )
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

    ``thresholds`` is ALERT-only (the key only ever exists in ``config`` for
    ALERT-type rows); sending it for a NOTIFICATION row is a validation
    error. channels/recipient_roles/scope are accepted for both types.

    recipient_roles is a partial-update dict, not a wholesale replacement:
    every key already stored on the row keeps its current value unless the
    payload names it, in which case it's set to exactly what the payload
    says — except ``"ADMIN"``, which is always re-derived from the row's
    effective scope afterward (see _apply_admin_recipient_scope_invariant),
    overriding whatever the payload sent for that one key. ``thresholds``
    is different — it's a wholesale replacement of the whole
    THRESHOLD_BAND_COUNT-length list, since a band's ``percentage`` is
    itself editable and bands have no other stable key to merge a partial
    update against."""
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

    if payload.scope is not None:
        row.scope = payload.scope.value

    if payload.recipient_roles is not None:
        merged = _merged_bool_dict(row.recipient_roles or {}, payload.recipient_roles)
        _validate_recipient_roles(row.name, merged)
        row.recipient_roles = merged

    # Re-applied unconditionally (not just when payload touched
    # recipient_roles) — a scope-only PATCH into INSTITUTION must still
    # clear a previously-true ADMIN flag, and a row's ADMIN key must never
    # drift out of sync with its current scope.
    row.recipient_roles = _apply_admin_recipient_scope_invariant(
        row.recipient_roles or {}, row.scope
    )

    if payload.thresholds is not None:
        _validate_thresholds(row.name, payload.thresholds)
        config = dict(row.config or {})
        config["thresholds"] = [band.model_dump() for band in payload.thresholds]
        row.config = config

    if payload.channels is not None:
        row.channels = [channel.value for channel in payload.channels]

    if updated_by is not None:
        row.updated_by = updated_by

    await session.commit()
    await session.refresh(row)

    if (
        payload.thresholds is not None
        or payload.scope is not None
        or payload.recipient_roles is not None
    ):
        # Every producer's in-memory settings cache (ai4i_core.kafka.
        # notification_settings_cache) subscribes to this channel and does a
        # full reload on any message — scope/recipient_roles changes matter
        # there too (a notification with no roles selected is treated as
        # "off", and scope decides whether an event fires platform-wide or
        # is gated by a tenant's subscription), not just thresholds.
        # Best-effort: a cache falls back to its last known value (and its
        # own DB reload on next restart) if this fails, same framing as
        # every other pub/sub-notify call in this codebase.
        try:
            redis = get_redis_client()
            await redis.publish(NOTIFICATION_ALERT_UPDATES_CHANNEL, row.name)
        except Exception as exc:
            logger.warning(
                "Failed to publish %s update to '%s': %s",
                NOTIFICATION_ALERT_UPDATES_CHANNEL, row.name, exc,
            )

    return _to_catalog_item(row)
