"""Undo the Prometheus backfill: delete every daily_usage row with
source = 'backfill', and nothing else.

    cd services/pyjob
    python -m backfill undo

Rollup rows (source 'rollup', from usage_events) are never touched, nor are
usage_events, budget_usage or quota_usage, which the backfill never writes.
The past-month daily_usage partitions a run created are kept, empty (past
partitions are never dropped; see monthly_partition_rollover). Takes the same
advisory lock as a load, so it can't run alongside one. Re-running is safe:
with nothing backfilled it deletes nothing.
"""
from __future__ import annotations

from ai4i_core.logging import get_logger
from sqlalchemy import text

from backfill.engine import SOURCE, BackfillError
from bootstrap.database import platform_core_session

logger = get_logger(__name__)


async def undo() -> None:
    async with platform_core_session() as session:
        async with session.begin():
            locked = (
                await session.execute(text("SELECT pg_try_advisory_xact_lock(hashtext('pyjob:usage_backfill'))"))
            ).scalar_one()
            if not locked:
                raise BackfillError("a usage_backfill run is in progress; undo after it finishes")

            # source is a native enum; SOURCE is a fixed constant, so compare
            # to the literal rather than a text bind (text-vs-enum has no operator).
            summary = (
                await session.execute(
                    text(
                        "SELECT count(*) AS rows, min(usage_date) AS first_day, max(usage_date) AS last_day,"
                        " coalesce(sum(request_count), 0) AS requests, coalesce(sum(cost), 0) AS cost"
                        f" FROM daily_usage WHERE source = '{SOURCE}'"
                    )
                )
            ).one()
            logger.info(
                "Undoing usage backfill | rows=%d days=%s..%s requests=%d cost=%s",
                summary.rows, summary.first_day, summary.last_day, summary.requests, summary.cost,
            )

            deleted = (
                await session.execute(text(f"DELETE FROM daily_usage WHERE source = '{SOURCE}'"))
            ).rowcount or 0

    logger.info("Usage backfill undone | daily_usage_rows_deleted=%d", deleted)


async def run() -> None:
    await undo()
