"""Monthly partition creation for daily_usage.

Run by k8s on the 1st of every month at 00:00. Schedule it in UTC: partition
months are UTC calendar months (see the create_daily_usage_table migration),
and this job reads the current month in UTC.

usage_events is partitioned by day instead, by the daily_usage_consolidation
job, which also converts the month partitions its migration creates.

In one transaction, creates the daily_usage partitions for the current month
and the next PARTITION_MONTHS_AHEAD months that don't exist yet, named
daily_usage_YYYY_MM like the ones the migration creates. Past partitions are
never dropped.

Re-running is safe: existing partitions are skipped. A transaction-level
advisory lock makes an overlapping run skip instead of racing.

Creating a month fails if the DEFAULT partition already holds rows for it
(Postgres refuses to attach the range). The job checks for this first and
fails with the month and row count, leaving the table unchanged; those rows
have to be moved out of the DEFAULT partition before the month can be added.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from ai4i_core.logging import get_logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from bootstrap.config import get_settings
from bootstrap.database import platform_core_session

logger = get_logger(__name__)

TABLE = "daily_usage"
COLUMN = "usage_date"


class DefaultPartitionHasRowsError(RuntimeError):
    pass


def _bound(month: date) -> str:
    # usage_date is a date, so plain date bounds.
    return f"'{month.isoformat()}'"


def _add_months(month: date, n: int) -> date:
    index = month.year * 12 + (month.month - 1) + n
    return date(index // 12, index % 12 + 1, 1)


def _partition_name(month: date) -> str:
    return f"{TABLE}_{month.year:04d}_{month.month:02d}"


async def _partitions(session: AsyncSession) -> tuple[set[str], str | None]:
    """Month partitions and the DEFAULT partition of daily_usage."""
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
    months = {name for name, is_default in rows if not is_default}
    default = next((name for name, is_default in rows if is_default), None)
    return months, default


async def _create_months(
    session: AsyncSession, existing: set[str], default: str | None, months: list[date]
) -> list[str]:
    created = []
    for month in months:
        name = _partition_name(month)
        if name in existing:
            continue
        lower, upper = _bound(month), _bound(_add_months(month, 1))
        if default is not None:
            stray = (
                await session.execute(
                    text(f'SELECT count(*) FROM "{default}" WHERE "{COLUMN}" >= {lower} AND "{COLUMN}" < {upper}')
                )
            ).scalar_one()
            if stray:
                raise DefaultPartitionHasRowsError(
                    f"{default} holds {stray} row(s) for {month:%Y-%m}; move them out before {name} can be created"
                )
        await session.execute(
            text(f'CREATE TABLE "{name}" PARTITION OF "{TABLE}" FOR VALUES FROM ({lower}) TO ({upper})')
        )
        created.append(name)
    return created


async def rollover(today: date) -> None:
    current = today.replace(day=1)
    wanted = [_add_months(current, i) for i in range(get_settings().PARTITION_MONTHS_AHEAD + 1)]

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

            existing, default = await _partitions(session)
            created = await _create_months(session, existing, default, wanted)

    logger.info(
        "Partition rollover done | table=%s current=%s created=%s", TABLE, f"{current:%Y-%m}", created,
    )


async def run() -> None:
    logger.info("Starting monthly partition rollover")
    await rollover(datetime.now(timezone.utc).date())
