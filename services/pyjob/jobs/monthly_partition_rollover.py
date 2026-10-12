"""Monthly partitions for daily_usage.

Run by k8s on the 1st of every month at 00:00. Schedule it in UTC: partition
months are UTC calendar months (see the create_daily_usage_table migration),
and this job reads the current month in UTC.

usage_events is partitioned by day instead, by the daily_usage_consolidation
job, which also converts the month partitions its migration creates.

In one transaction, with daily_usage locked ACCESS EXCLUSIVE so the rollup
waits instead of writing mid-change:

- Creates the partitions for the current month and the next
  PARTITION_MONTHS_AHEAD months that don't exist yet, named daily_usage_YYYY_MM
  like the ones the migration creates. Rows the DEFAULT partition holds for a
  month being created are moved into it first, since Postgres refuses the new
  range otherwise (this happens when the job wasn't running when a month
  started).
- Past month partitions are never dropped.

Re-running is safe: existing partitions are skipped. A transaction-level
advisory lock makes an overlapping run skip instead of racing.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone

from ai4i_core.logging import get_logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from bootstrap.config import get_settings
from bootstrap.database import platform_core_session

logger = get_logger(__name__)

TABLE = "daily_usage"
COLUMN = "usage_date"
_MONTH_RE = re.compile(rf"^{TABLE}_(\d{{4}})_(\d{{2}})$")


class RowCountMismatchError(RuntimeError):
    pass


def _bound(month: date) -> str:
    # usage_date is a date, so plain date bounds.
    return f"'{month.isoformat()}'"


def _add_months(month: date, n: int) -> date:
    index = month.year * 12 + (month.month - 1) + n
    return date(index // 12, index % 12 + 1, 1)


def _partition_name(month: date) -> str:
    return f"{TABLE}_{month.year:04d}_{month.month:02d}"


def _in_months(months: list[date]) -> str:
    """SQL condition matching usage_date in any of ``months``."""
    return " OR ".join(
        f'("{COLUMN}" >= {_bound(m)} AND "{COLUMN}" < {_bound(_add_months(m, 1))})' for m in months
    )


async def _partitions(session: AsyncSession) -> tuple[dict[date, str], str | None]:
    """Month partitions by month, and the DEFAULT partition, of daily_usage."""
    rows = (
        await session.execute(
            text(
                """
                SELECT c.relname, pg_get_expr(c.relpartbound, c.oid) = 'DEFAULT' AS is_default
                FROM pg_inherits i
                JOIN pg_class c ON c.oid = i.inhrelid
                WHERE i.inhparent = CAST(:table AS regclass)
                """
            ),
            {"table": TABLE},
        )
    ).all()
    months = {
        date(int(m[1]), int(m[2]), 1): name
        for name, is_default in rows
        if not is_default and (m := _MONTH_RE.match(name))
    }
    default = next((name for name, is_default in rows if is_default), None)
    return months, default


async def _insertable_columns(session: AsyncSession) -> str:
    """Columns of daily_usage that can be written: generated ones are skipped."""
    rows = await session.execute(
        text(
            """
            SELECT attname
            FROM pg_attribute
            WHERE attrelid = CAST(:table AS regclass) AND attnum > 0 AND NOT attisdropped AND attgenerated = ''
            ORDER BY attnum
            """
        ),
        {"table": TABLE},
    )
    return ", ".join(f'"{name}"' for name in rows.scalars())


async def _create_months(session: AsyncSession, default: str | None, to_create: list[date]) -> int:
    """Create ``to_create``, moving their rows out of the DEFAULT partition. Returns rows moved."""
    if not to_create:
        return 0

    # Rows in the DEFAULT partition for a month being created must leave it
    # first, or Postgres refuses the new partition's range.
    moved = 0
    if default is not None:
        await session.execute(text(f'CREATE TEMP TABLE du_moved (LIKE "{default}") ON COMMIT DROP'))
        result = await session.execute(
            text(
                f'WITH m AS (DELETE FROM "{default}" WHERE {_in_months(to_create)} RETURNING *) '
                f"INSERT INTO du_moved SELECT * FROM m"
            )
        )
        moved = result.rowcount or 0

    for month in to_create:
        await session.execute(
            text(
                f'CREATE TABLE "{_partition_name(month)}" PARTITION OF "{TABLE}" '
                f"FOR VALUES FROM ({_bound(month)}) TO ({_bound(_add_months(month, 1))})"
            )
        )

    # Restore through the parent, which routes each row to its month. id is
    # GENERATED ALWAYS, so the rows keep their ids only with OVERRIDING.
    if moved:
        columns = await _insertable_columns(session)
        result = await session.execute(
            text(f'INSERT INTO "{TABLE}" ({columns}) OVERRIDING SYSTEM VALUE SELECT {columns} FROM du_moved')
        )
        if (result.rowcount or 0) != moved:
            raise RowCountMismatchError(f"restored {result.rowcount} of {moved} row(s) from {default}; rolled back")
    return moved


async def rollover(today: date) -> None:
    settings = get_settings()
    current = today.replace(day=1)
    wanted = [_add_months(current, i) for i in range(settings.PARTITION_MONTHS_AHEAD + 1)]

    async with platform_core_session() as session:
        async with session.begin():
            locked = (
                await session.execute(
                    text("SELECT pg_try_advisory_xact_lock(hashtext(:key))"),
                    {"key": f"pyjob:monthly_partition_rollover:{TABLE}"},
                )
            ).scalar_one()
            if not locked:
                logger.warning("Partition rollover already running, skipping | table=%s", TABLE)
                return
            await session.execute(text("SET LOCAL lock_timeout = '30s'"))
            await session.execute(text(f'LOCK TABLE "{TABLE}" IN ACCESS EXCLUSIVE MODE'))

            existing, default = await _partitions(session)
            to_create = [month for month in wanted if month not in existing]
            moved = await _create_months(session, default, to_create)

    logger.info(
        "Partition rollover done | table=%s current=%s created=%s default_rows_moved=%d",
        TABLE, f"{current:%Y-%m}", [_partition_name(m) for m in to_create], moved,
    )


async def run() -> None:
    logger.info("Starting monthly partition rollover")
    await rollover(datetime.now(timezone.utc).date())
