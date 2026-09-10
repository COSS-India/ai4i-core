"""Reads and writes against ledger_notification_alert — design doc §5-§7.

No ORM model here on purpose: this table lives in ai4iplatform_core, a
different service's database, and kafka-consumers follows the same
raw-SQL-via-text() convention payperuse_consumer already uses for
cross-service tables (see _billing.py) rather than importing
platform-core-service's models.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from ai4i_core.logging import get_logger
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


async def fetch_current_status(
    db: AsyncSession, *, notification_id: int, tenant_id: str, subject: Dict[str, Any], channel: str
) -> Optional[Dict[str, Any]]:
    """The row's current `status`, or None if no row exists yet for this
    (notification, tenant, subject, channel). patterns.decide() needs this
    as its starting point — reading it here, ahead of the guarded write, is
    what lets decide() stay pure and I/O-free."""
    stmt = text(
        "SELECT status FROM ledger_notification_alert"
        " WHERE notification_id = :notification_id"
        "   AND tenant_id = :tenant_id"
        "   AND subject = :subject"
        "   AND channel = :channel::notification_alert_channel_enum"
    ).bindparams(bindparam("subject", type_=JSONB))
    result = await db.execute(
        stmt,
        {
            "notification_id": notification_id,
            "tenant_id": tenant_id,
            "subject": subject,
            "channel": channel,
        },
    )
    row = result.first()
    if row is None:
        return None
    status = row[0] or {}
    if isinstance(status, str):  # defensive — see catalog_cache.py's note
        status = json.loads(status) if status else {}
    return status


# design doc §7's WHERE clause, made pattern-aware — see patterns.StatusDecision's
# docstring for why "monotonic"/"reset"/"marker" need different guards rather
# than one generic IS DISTINCT FROM.
_GUARD_CLAUSES = {
    "monotonic": (
        "ledger_notification_alert.status = '{}'::jsonb"
        " OR (ledger_notification_alert.status->>'value')::numeric"
        "    < (EXCLUDED.status->>'value')::numeric"
    ),
    "reset": "ledger_notification_alert.status IS DISTINCT FROM EXCLUDED.status",
    "marker": (
        "ledger_notification_alert.status->>'value'"
        " IS DISTINCT FROM EXCLUDED.status->>'value'"
    ),
}


async def claim(
    db: AsyncSession,
    *,
    notification_id: int,
    tenant_id: str,
    subject: Dict[str, Any],
    channel: str,
    new_status: Dict[str, Any],
    guard: str,
    actor_id: Optional[str],
) -> Optional[int]:
    """Try to write new_status. Returns the row id if THIS call is the one
    that won the race (per the guard clause for `guard`); returns None if a
    concurrent caller already got there first, or if the guard rejected the
    write outright (e.g. a stale candidate lower than what's already
    recorded). Never raises on a lost race — that's the whole point.
    """
    guard_clause = _GUARD_CLAUSES[guard]
    stmt = text(
        "INSERT INTO ledger_notification_alert"
        "    (notification_id, tenant_id, subject, channel, status, created_by, updated_by)"
        " VALUES"
        "    (:notification_id, :tenant_id, :subject, :channel::notification_alert_channel_enum,"
        "     :status, :actor_id, :actor_id)"
        " ON CONFLICT (notification_id, tenant_id, subject, channel)"
        " DO UPDATE SET"
        "    status = EXCLUDED.status,"
        "    updated_by = EXCLUDED.updated_by,"
        "    updated_at = now()"
        f" WHERE {guard_clause}"
        " RETURNING id"
    ).bindparams(bindparam("subject", type_=JSONB), bindparam("status", type_=JSONB))

    result = await db.execute(
        stmt,
        {
            "notification_id": notification_id,
            "tenant_id": tenant_id,
            "subject": subject,
            "channel": channel,
            "status": new_status,
            "actor_id": actor_id,
        },
    )
    row = result.first()
    await db.commit()
    return row[0] if row is not None else None


async def mark_delivery(
    db: AsyncSession, *, row_id: int, delivery: str
) -> None:
    """Update just status.delivery on an already-claimed row (in_progress ->
    sent/failed), leaving `value` untouched. A plain, unguarded update — this
    call only ever happens after claim() already confirmed this row is ours
    for this update."""
    await db.execute(
        text(
            "UPDATE ledger_notification_alert"
            " SET status = jsonb_set(status, '{delivery}', to_jsonb(:delivery::text)),"
            "     updated_at = now()"
            " WHERE id = :row_id"
        ),
        {"row_id": row_id, "delivery": delivery},
    )
    await db.commit()
