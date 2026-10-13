"""Reads and writes usage_report_send_log, and the lock that keeps two
scheduled runs (an overlapping CronJob, or the job plus a manual run) from
sending the same period twice."""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date
from typing import AsyncIterator, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.services.usage_report.period import ReportPeriod

SENT, FAILED, NOT_READY = "SENT", "FAILED", "NOT_READY"

# pg_advisory_lock key: any fixed bigint unique to this job ("usagerpt" in ASCII).
LOCK_KEY = 0x75736167_65727074 & 0x7FFF_FFFF_FFFF_FFFF


@dataclass(frozen=True)
class RecipientState:
    status: str
    attempts: int


@asynccontextmanager
async def report_lock(engine: AsyncEngine) -> AsyncIterator[bool]:
    """Yields True when this run holds the lock, False when another run does.

    A session-level advisory lock on a dedicated connection, held for the
    whole run: the run commits after every recipient, which would release a
    transaction-level lock (and an AsyncSession may switch connections)."""
    async with engine.connect() as conn:
        acquired = bool(await conn.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": LOCK_KEY}))
        try:
            yield acquired
        finally:
            if acquired:
                await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})


class SendLog:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def last_reported_day(self, excluding: ReportPeriod) -> Optional[date]:
        """Last day covered by any period sent to anyone, other than
        ``excluding`` — a period still being delivered doesn't block itself."""
        return await self._db.scalar(
            text(
                "SELECT max(period_end) FROM usage_report_send_log "
                "WHERE status = :sent AND NOT (frequency = :f AND period_start = :s AND period_end = :e)"
            ),
            {"sent": SENT, **_period_params(excluding)},
        )

    async def recipient_states(self, period: ReportPeriod) -> dict[str, RecipientState]:
        rows = await self._db.execute(
            text(
                "SELECT recipient_user_id, status, attempts FROM usage_report_send_log "
                "WHERE frequency = :f AND period_start = :s AND period_end = :e "
                "AND recipient_user_id IS NOT NULL"
            ),
            _period_params(period),
        )
        return {r.recipient_user_id: RecipientState(r.status, r.attempts) for r in rows}

    async def record(self, period: ReportPeriod, user_id: str, error: Optional[str]) -> None:
        """One delivery attempt: SENT (error None) or FAILED, attempts + 1."""
        await self._db.execute(
            text(
                "INSERT INTO usage_report_send_log "
                "(frequency, period_start, period_end, recipient_user_id, status, attempts, last_error, sent_at) "
                "VALUES (:f, :s, :e, :u, :status, 1, :err, CASE WHEN :is_sent THEN now() END) "
                "ON CONFLICT (frequency, period_start, period_end, recipient_user_id) "
                "WHERE recipient_user_id IS NOT NULL DO UPDATE SET "
                "status = EXCLUDED.status, attempts = usage_report_send_log.attempts + 1, "
                "last_error = EXCLUDED.last_error, sent_at = EXCLUDED.sent_at, updated_at = now()"
            ),
            {**_period_params(period), "u": user_id, "status": SENT if error is None else FAILED,
             "is_sent": error is None, "err": error},
        )
        await self._db.commit()

    async def record_not_ready(self, period: ReportPeriod, reason: str) -> None:
        await self._db.execute(
            text(
                "INSERT INTO usage_report_send_log (frequency, period_start, period_end, status, last_error) "
                "VALUES (:f, :s, :e, :status, :err)"
            ),
            {**_period_params(period), "status": NOT_READY, "err": reason},
        )
        await self._db.commit()


def _period_params(period: ReportPeriod) -> dict:
    return {"f": period.frequency, "s": period.first_day, "e": period.last_day}
