"""Records notification_failures — one row per email that never went out
to any recipient.

No ORM model here on purpose, same raw-SQL-via-text() convention this
consumer used for ledger_notification_alert before that table was removed
from its scope entirely: this table lives in ai4iplatform_core, a
different service's database.

Deliberately dumb: the row is the entire failed Kafka message, verbatim,
plus the channel it failed on. Nothing here parses that message or decides
why it failed — that's for whoever reads this table later.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def record_failure(db: AsyncSession, *, message: bytes, channel: str) -> None:
    await db.execute(
        text("INSERT INTO notification_failures (message, channel) VALUES (:message, :channel)"),
        {"message": message.decode("utf-8", errors="replace"), "channel": channel},
    )
    await db.commit()
