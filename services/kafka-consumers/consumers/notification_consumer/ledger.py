"""Reads and writes against ledger_notification_alert — consumer side.

The producer (auth-service / platform-core-service / payperuse_consumer,
via libs/ai4i_core/ai4i_core/kafka/ledger.py's check_and_record_*) already
claimed the row before ever publishing: by the time a message reaches this
consumer, the row for (notification_id, tenant_id, subject, channel) already
exists with {"value": ..., "delivery": "in_progress"}. This module does NOT
decide a new value — that decision, and its dedup guard, already happened
producer-side. The consumer's only remaining job is the delivery half:
claim the SEND attempt (so a Kafka redelivery or a second replica can't both
send), then settle it to "sent"/"failed".

No ORM model here on purpose: this table lives in ai4iplatform_core, a
different service's database, and kafka-consumers follows the same
raw-SQL-via-text() convention payperuse_consumer already uses for
cross-service tables (see _billing.py) rather than importing
platform-core-service's models.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple

from ai4i_core.logging import get_logger
from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


async def fetch_row(
    db: AsyncSession, *, notification_id: int, tenant_id: str, subject: Dict[str, Any], channel: str
) -> Optional[Tuple[int, Dict[str, Any]]]:
    """(id, status) for this (notification, tenant, subject, channel), or
    None if no row exists yet. Not existing yet is unexpected — the
    producer writes it before publishing — but not impossible (a redelivery
    racing a slow producer-side commit is timing-dependent, not a
    guarantee), so callers treat it as "nothing to do yet", not an error."""
    stmt = text(
        "SELECT id, status FROM ledger_notification_alert"
        " WHERE notification_id = :notification_id"
        "   AND tenant_id = :tenant_id"
        "   AND subject = :subject"
        "   AND channel = CAST(:channel AS notification_alert_channel_enum)"
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
    status = row[1] or {}
    if isinstance(status, str):  # defensive — see catalog_cache.py's note
        status = json.loads(status) if status else {}
    return row[0], status


async def claim_send(db: AsyncSession, *, row_id: int) -> bool:
    """Atomically flip status.delivery from "in_progress" to "sending".
    True if THIS call won — i.e. it's the one that should actually send.
    False means someone already claimed it (a concurrent redelivery, or a
    second replica) — the guard is the WHERE clause, not a prior read, so
    two simultaneous callers can never both get True."""
    result = await db.execute(
        text(
            "UPDATE ledger_notification_alert"
            " SET status = jsonb_set(status, '{delivery}', '\"sending\"'::jsonb),"
            "     updated_at = now()"
            " WHERE id = :row_id AND status->>'delivery' = 'in_progress'"
            " RETURNING id"
        ),
        {"row_id": row_id},
    )
    won = result.first() is not None
    await db.commit()
    return won


async def mark_delivery(db: AsyncSession, *, row_id: int, delivery: str) -> None:
    """Settle status.delivery to its final value ("sent"/"failed"), leaving
    `value` untouched."""
    await db.execute(
        text(
            "UPDATE ledger_notification_alert"
            " SET status = jsonb_set(status, '{delivery}', to_jsonb(CAST(:delivery AS text))),"
            "     updated_at = now()"
            " WHERE id = :row_id"
        ),
        {"row_id": row_id, "delivery": delivery},
    )
    await db.commit()
