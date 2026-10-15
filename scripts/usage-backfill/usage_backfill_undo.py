"""Undo the Prometheus backfill (usage_backfill.py): removes exactly what
its loads wrote, and nothing else.

    python scripts/usage-backfill/usage_backfill_undo.py

In one transaction:

- deletes every daily_usage row with source = 'backfill'. Rollup rows (source
  'rollup', from usage_events) are never touched, nor are usage_events,
  budget_usage or quota_usage, which the backfill never writes;
- deletes the usage_backfill row, so the Usage Dashboard stops counting the
  backfilled days and stops marking figures as estimated.

The past-month daily_usage partitions a load created are kept, empty: past
partitions are never dropped (see monthly_partition_rollover), and the next
load reuses them.

Takes the same advisory lock as a load, so it can't run alongside one.
Re-running is safe: with nothing backfilled it deletes nothing. Running
usage_backfill again afterwards re-reads Prometheus, which may no longer hold
the oldest days.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from ai4i_core.logging import configure_logging, get_logger
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent))
from usage_backfill import SOURCE, BackfillError  # noqa: E402  (also puts pyjob on sys.path)

from bootstrap.database import close_databases, init_databases, platform_core_session  # noqa: E402

logger = get_logger(__name__)


async def undo() -> None:
    async with platform_core_session() as session:
        async with session.begin():
            locked = (
                await session.execute(text("SELECT pg_try_advisory_xact_lock(hashtext('usage_backfill'))"))
            ).scalar_one()
            if not locked:
                raise BackfillError("a usage_backfill load is running; undo after it finishes")

            coverage = (await session.execute(text("SELECT first_day, until FROM usage_backfill"))).first()
            summary = (
                await session.execute(
                    text(
                        "SELECT count(*) AS rows, min(usage_date) AS first_day, max(usage_date) AS last_day,"
                        " coalesce(sum(request_count), 0) AS requests, coalesce(sum(cost), 0) AS cost"
                        " FROM daily_usage WHERE source = :source"
                    ),
                    {"source": SOURCE},
                )
            ).one()
            logger.info(
                "Undoing usage backfill | coverage=%s rows=%d days=%s..%s requests=%d cost=%s",
                f"{coverage.first_day}..{coverage.until.isoformat()}" if coverage else "none",
                summary.rows, summary.first_day, summary.last_day, summary.requests, summary.cost,
            )

            deleted = (
                await session.execute(text("DELETE FROM daily_usage WHERE source = :source"), {"source": SOURCE})
            ).rowcount or 0
            coverage_deleted = (await session.execute(text("DELETE FROM usage_backfill"))).rowcount or 0

    logger.info(
        "Usage backfill undone | daily_usage_rows_deleted=%d coverage_row_deleted=%s",
        deleted, bool(coverage_deleted),
    )


async def _main() -> None:
    init_databases()
    try:
        await undo()
    finally:
        await close_databases()


def main() -> None:
    configure_logging(service_name="usage-backfill-undo")
    asyncio.run(_main())


if __name__ == "__main__":
    main()
