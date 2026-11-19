"""Daily API key expiry reminders: GRACE_PERIOD_EXPIRING and API_KEY_EXPIRING.

A step of daily_usage_consolidation (run_key_expiry_alerts), also runnable
on its own: ``python main.py --job key_expiry_alerts``.

For each alert this reads its day thresholds from the cached catalog row,
pages through the keys in the auth DB whose expiry is due a reminder today
(the Grace Period Key Query / Expiring API Key Query), and hands them to
emit_state_bulk. The ledger claim there sends each level once per rotation
(grace) or per expiry (normal key), however often the job runs.

Due level = the smallest active threshold t with t >= days_left and
t < span_days, all in calendar days of NOTIFICATION_TIMEZONE:

* t >= days_left: a day the cron missed is caught up the next day, with the
  most urgent level only.
* t < span_days: a level that had already passed when the key was rotated
  (grace) or created (normal key) is never sent.

The emails identify a key by its masked value (first 4 and last 4
characters); the full value never leaves the step.

Eligibility is api_key.is_active only. applications and tenants are joined
for lookups: tenant_id (api_key has none), the application name and the
institution name in the email subject.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from ai4i_core.kafka import (
    NotificationName,
    Severity,
    StateItem,
    ThresholdUnit,
    emit_state_bulk,
    get_notification_runtime,
    notifications_configured,
    utc_seconds,
)
from ai4i_core.logging import get_logger
from sqlalchemy import text

from bootstrap.config import get_settings
from bootstrap.notifications import notifications

logger = get_logger(__name__)

PAGE_SIZE = 500
ALERT_NAMES = (NotificationName.GRACE_PERIOD_EXPIRING, NotificationName.API_KEY_EXPIRING)

# One run at a time; the ledger stops duplicates even without it.
_LOCK_KEY = "api-key-expiry-alerts"
_MASK_CHAR = "*"
_TRY_LOCK_SQL = text("SELECT pg_try_advisory_lock(hashtext(:key))")
_UNLOCK_SQL = text("SELECT pg_advisory_unlock(hashtext(:key))")

# Grace Period Key Query (auth DB): rotated keys whose old value stops in the
# next max_level days and is due a reminder today.
_GRACE_PERIOD_KEY_SQL = text(
    """
    SELECT k.id                      AS api_key_id,
           k.key_name,
           k.rotated_key             AS expiring_key,   -- masked before it leaves the step
           k.api_key                 AS new_key,
           k.rotated_key_expires_at  AS expires_at,
           k.rotated_at              AS rotated_at,
           a.name                    AS application_name,
           a.tenant_id,
           t.organisation            AS tenant_name,
           d.days_left,
           lvl.days_before
      FROM api_key k
      JOIN applications a ON a.id = k.application_id   -- lookup only: tenant_id, application name
      JOIN tenants t      ON t.id = a.tenant_id         -- lookup only: institution name
      CROSS JOIN LATERAL (
            SELECT (k.rotated_key_expires_at AT TIME ZONE :tz)::date
                 - (now()                    AT TIME ZONE :tz)::date AS days_left,
                   (k.rotated_key_expires_at AT TIME ZONE :tz)::date
                 - (k.rotated_at             AT TIME ZONE :tz)::date AS span_days
           ) d
      CROSS JOIN LATERAL (
            SELECT min(l) AS days_before
              FROM unnest(CAST(:levels AS int[])) AS l
             WHERE l >= d.days_left
               AND l <  d.span_days
           ) lvl
     WHERE k.is_active
       AND k.rotated_key IS NOT NULL
       AND k.rotated_key_expires_at >  now()
       AND k.rotated_key_expires_at <= now() + make_interval(days => CAST(:max_level AS int) + 1)
       AND (k.expires_at IS NULL OR k.expires_at > k.rotated_key_expires_at)
       AND lvl.days_before IS NOT NULL
       AND k.id > :after_id
     ORDER BY k.id
     LIMIT :page_size
    """
)

# Expiring API Key Query (auth DB): keys with an expiry in the next
# max_level days that are due a reminder today.
_EXPIRING_API_KEY_SQL = text(
    """
    SELECT k.id                      AS api_key_id,
           k.key_name,
           k.api_key                 AS expiring_key,   -- masked before it leaves the step
           NULL::text                AS new_key,
           k.expires_at              AS expires_at,
           NULL::timestamptz         AS rotated_at,
           a.name                    AS application_name,
           a.tenant_id,
           t.organisation            AS tenant_name,
           d.days_left,
           lvl.days_before
      FROM api_key k
      JOIN applications a ON a.id = k.application_id   -- lookup only: tenant_id, application name
      JOIN tenants t      ON t.id = a.tenant_id         -- lookup only: institution name
      CROSS JOIN LATERAL (
            SELECT (k.expires_at AT TIME ZONE :tz)::date
                 - (now()        AT TIME ZONE :tz)::date AS days_left,
                   (k.expires_at AT TIME ZONE :tz)::date
                 - (k.created_at AT TIME ZONE :tz)::date AS span_days
           ) d
      CROSS JOIN LATERAL (
            SELECT min(l) AS days_before
              FROM unnest(CAST(:levels AS int[])) AS l
             WHERE l >= d.days_left
               AND l <  d.span_days
           ) lvl
     WHERE k.is_active
       AND k.expires_at IS NOT NULL
       AND k.expires_at >  now()
       AND k.expires_at <= now() + make_interval(days => CAST(:max_level AS int) + 1)
       AND lvl.days_before IS NOT NULL
       AND k.id > :after_id
     ORDER BY k.id
     LIMIT :page_size
    """
)

_CANDIDATE_SQL = {
    NotificationName.GRACE_PERIOD_EXPIRING: _GRACE_PERIOD_KEY_SQL,
    NotificationName.API_KEY_EXPIRING: _EXPIRING_API_KEY_SQL,
}


class ExpiryAlertsUnavailable(RuntimeError):
    """Notifications are off, or the catalog settings could not be read."""


@dataclass
class AlertResult:
    levels: List[int] = field(default_factory=list)
    candidates: int = 0
    sent: int = 0


@dataclass
class RunResult:
    skipped: Optional[str] = None
    results: Dict[str, AlertResult] = field(default_factory=dict)


def day_levels(bands) -> Tuple[List[int], Dict[int, Severity]]:
    """The active DAYS bands of a catalog row: levels (ascending) and the
    severity of each level."""
    severity = {int(b.value): b.severity for b in bands if b.unit is ThresholdUnit.DAYS}
    return sorted(severity), severity


def email_datetime(value: datetime) -> str:
    """Display format of the notification emails (as auth-service's), in
    NOTIFICATION_TIMEZONE."""
    zone = ZoneInfo(get_settings().NOTIFICATION_TIMEZONE)
    return value.astimezone(zone).strftime("%d %b %Y, %I:%M %p %Z")


def mask_api_key(value: Optional[str]) -> Optional[str]:
    """Masked key identifier for the emails: first 4 and last 4 characters,
    as auth-service's mask_api_key (``ab12cd34ef56gh78`` -> ``ab12******gh78``).
    A value too short to mask that way is hidden entirely."""
    if not value or len(value) <= 8:
        return "********" if value else value
    return f"{value[:4]}{_MASK_CHAR * 6}{value[-4:]}"


def _details(row) -> list:
    """Positional email details (see the .j2 templates):
    [application_name, masked expiring key, expiry, days_left], plus the
    masked new key for GRACE_PERIOD_EXPIRING. The full key value never
    leaves the step."""
    details = [
        row["application_name"],
        mask_api_key(row["expiring_key"]),
        email_datetime(row["expires_at"]),
        int(row["days_left"]),
    ]
    if row.get("new_key"):
        details.append(mask_api_key(row["new_key"]))
    return details


def _subject(row, days_before: int) -> Dict[str, str]:
    """Ledger subject. A grace reminder is keyed on the rotation (rotated_at),
    which an extension of the grace period doesn't change, so a level
    already sent for that rotation is never sent again. A key's own expiry
    is keyed on expires_at: a moved expiry starts its reminders again."""
    if row["rotated_at"] is not None:
        moment = {"rotated_at": utc_seconds(row["rotated_at"])}
    else:
        moment = {"expires_at": utc_seconds(row["expires_at"])}
    return {"api_key_id": str(row["api_key_id"]), **moment, "days_before": str(days_before)}


def _state_item(row, severity: Dict[int, Severity]) -> StateItem:
    days_before = int(row["days_before"])
    return StateItem(
        tenant_id=str(row["tenant_id"]),
        subject=_subject(row, days_before),
        new_state={"days_before": days_before},
        details=_details(row),
        tenant_name=row["tenant_name"],
        severity=severity.get(days_before, Severity.INFO),
    )


async def _candidate_page(name: NotificationName, levels: Sequence[int], after_id: int) -> list:
    rt = get_notification_runtime()
    async with rt.auth_session_factory() as session:
        result = await session.execute(
            _CANDIDATE_SQL[name],
            {
                "tz": get_settings().NOTIFICATION_TIMEZONE,
                "levels": list(levels),
                "max_level": max(levels),
                "after_id": after_id,
                "page_size": PAGE_SIZE,
            },
        )
        return list(result.mappings())


async def _send_alert(name: NotificationName, settings_row) -> AlertResult:
    levels, severity = day_levels(settings_row.bands if settings_row else ())
    out = AlertResult(levels=levels)
    if not levels:
        logger.info("Key expiry reminders skipped: no active DAYS thresholds | name=%s", name.value)
        return out
    after_id = 0
    while True:
        rows = await _candidate_page(name, levels, after_id)
        if not rows:
            break
        after_id = int(rows[-1]["api_key_id"])
        out.candidates += len(rows)
        items = [_state_item(row, severity) for row in rows]
        out.sent += len(await emit_state_bulk(name, items, summary=f"{name.value} page after {after_id}"))
        if len(rows) < PAGE_SIZE:
            break
    return out


async def send_reminders(names: Sequence[NotificationName] = ALERT_NAMES) -> RunResult:
    """Send today's reminders through an already configured pipeline. Raises
    ExpiryAlertsUnavailable when notifications are off or the settings can't
    be read, so the job exits as failed."""
    if not notifications_configured():
        raise ExpiryAlertsUnavailable("notifications are not configured")
    rt = get_notification_runtime()
    read = await rt.cache.read(context_name=names[0] if names else NotificationName.GRACE_PERIOD_EXPIRING)
    if read.settings is None:
        raise ExpiryAlertsUnavailable(f"notification settings unavailable: {read.settings_error}")

    async with rt.auth_session_factory() as lock_session:
        locked = (await lock_session.execute(_TRY_LOCK_SQL, {"key": _LOCK_KEY})).scalar()
        if not locked:
            logger.info("Key expiry reminders skipped: another run holds the lock")
            return RunResult(skipped="locked")
        try:
            result = RunResult()
            for name in names:
                alert = await _send_alert(name, read.settings.get(name))
                result.results[name.value] = alert
                logger.info(
                    "Key expiry reminders | name=%s levels=%s candidates=%d sent=%d",
                    name.value, alert.levels, alert.candidates, alert.sent,
                )
            return result
        finally:
            await lock_session.execute(_UNLOCK_SQL, {"key": _LOCK_KEY})


async def run_key_expiry_alerts() -> RunResult:
    """Start the notification pipeline, send today's reminders, stop it."""
    async with notifications():
        return await send_reminders()


async def run() -> None:
    await run_key_expiry_alerts()
