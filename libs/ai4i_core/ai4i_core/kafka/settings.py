"""DB loaders of the settings snapshot (Q-S1) and tenant subscriptions
(Q-S2, Q-S3), ai4iplatform_core.
"""

import json
from decimal import Decimal
from typing import Dict, List, Sequence

from sqlalchemy import text

from .constants import NotificationModule, NotificationName, NotificationScope, NotificationType, ThresholdUnit, Severity
from .keys import iso_z, to_decimal, utc_now
from .models import Band, SettingsRow, SettingsSnapshot, SubscriptionEntry, TenantSubscriptions

# Q-S1 — every catalog row with its active bands; recipient ids on MONITORING rows only.
_SNAPSHOT_SQL = text(
    """
    SELECT c.id, c.name::text AS name, c.type::text AS type, c.module::text AS module,
           c.scope::text AS scope, c.channels::text[] AS channels,
           c.recipient_roles,
           COALESCE((
               SELECT json_agg(json_build_object(
                          'value', t.band_value, 'unit', t.unit, 'severity', t.severity)
                      ORDER BY t.band_value)
                 FROM notification_alert_threshold t
                WHERE t.notification_id = c.id
                  AND t.active
           ), '[]'::json) AS bands,
           CASE WHEN c.type = 'MONITORING' THEN
               COALESCE((
                   SELECT array_agg(r.user_id ORDER BY r.user_id)
                     FROM monitoring_alert_recipient r
                    WHERE r.notification_id = c.id
               ), '{}'::varchar[])
           END AS recipient_user_ids
      FROM configs_notification_alert c
    """
)

# Q-S2 — subscriptions of one tenant
_SUBSCRIPTIONS_SQL = text(
    """
    SELECT c.name::text AS name, s.subscribed, s.recipients
      FROM tenant_notification_subscription s
      JOIN configs_notification_alert c ON c.id = s.notification_id
     WHERE s.tenant_id = :tenant_id
    """
)

# Q-S3 — subscriptions of many tenants
_SUBSCRIPTIONS_MANY_SQL = text(
    """
    SELECT s.tenant_id, c.name::text AS name, s.subscribed, s.recipients
      FROM tenant_notification_subscription s
      JOIN configs_notification_alert c ON c.id = s.notification_id
     WHERE s.tenant_id = ANY(CAST(:tenant_ids AS varchar[]))
    """
)


def _json(value):
    if isinstance(value, (str, bytes)):
        return json.loads(value, parse_float=Decimal)
    return value


def _bands(raw) -> tuple:
    bands = [
        Band(to_decimal(b["value"]), ThresholdUnit(b["unit"]), Severity(b["severity"]))
        for b in (_json(raw) or [])
    ]
    return tuple(sorted(bands, key=lambda b: b.value))


async def load_settings_snapshot(session) -> SettingsSnapshot:
    rows: Dict[str, SettingsRow] = {}
    result = await session.execute(_SNAPSHOT_SQL)
    for row in result.mappings():
        user_ids = row["recipient_user_ids"]
        rows[row["name"]] = SettingsRow(
            id=int(row["id"]),
            name=NotificationName(row["name"]),
            type=NotificationType(row["type"]),
            module=NotificationModule(row["module"]),
            scope=NotificationScope(row["scope"]),
            channels=tuple(row["channels"] or ()),
            recipient_roles={str(k): bool(v) for k, v in (_json(row["recipient_roles"]) or {}).items()},
            bands=_bands(row["bands"]),
            recipient_user_ids=tuple(str(u) for u in user_ids) if user_ids is not None else None,
        )
    return SettingsSnapshot(built_at=iso_z(utc_now()), rows=rows)


def _entry(row) -> SubscriptionEntry:
    return SubscriptionEntry(bool(row["subscribed"]), tuple(str(r) for r in (row["recipients"] or ())))


async def load_subscriptions(session, tenant_id: str) -> TenantSubscriptions:
    result = await session.execute(_SUBSCRIPTIONS_SQL, {"tenant_id": str(tenant_id)})
    rows = {row["name"]: _entry(row) for row in result.mappings()}
    return TenantSubscriptions(tenant_id=str(tenant_id), built_at=iso_z(utc_now()), rows=rows)


async def load_subscriptions_many(session, tenant_ids: Sequence[str]) -> Dict[str, TenantSubscriptions]:
    """Every requested tenant gets an entry; one with no rows gets rows={}."""
    ids: List[str] = [str(t) for t in tenant_ids]
    if not ids:
        return {}
    if len(ids) == 1:
        return {ids[0]: await load_subscriptions(session, ids[0])}
    built_at = iso_z(utc_now())
    grouped: Dict[str, Dict[str, SubscriptionEntry]] = {t: {} for t in ids}
    result = await session.execute(_SUBSCRIPTIONS_MANY_SQL, {"tenant_ids": ids})
    for row in result.mappings():
        grouped.setdefault(str(row["tenant_id"]), {})[row["name"]] = _entry(row)
    return {t: TenantSubscriptions(tenant_id=t, built_at=built_at, rows=grouped[t]) for t in ids}
