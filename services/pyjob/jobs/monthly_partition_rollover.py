"""Monthly partition rollover for usage_events and daily_usage.

Run by k8s on the 1st of every month at 00:00. Schedule it in UTC: partition
months are UTC calendar months (see the create_usage_events_table and
create_daily_usage_table migrations), and this job reads the current month
in UTC.

For each table, in its own transaction:

1. Create the partitions for the current month and the next
   PARTITION_MONTHS_AHEAD months that don't exist yet, named
   <table>_YYYY_MM like the ones the migrations create.
2. Detach and drop month partitions older than the retention
   (USAGE_EVENTS_MONTHS_RETENTION / DAILY_USAGE_MONTHS_RETENTION, counting
   the current month), with no archive, and delete rows older than the same
   cutoff from the DEFAULT partition.

Re-running is safe: existing partitions are skipped and nothing past the
cutoff is left to drop. A transaction-level advisory lock per table makes an
overlapping run skip that table instead of racing.

Creating a month fails if the DEFAULT partition already holds rows for it
(Postgres refuses to attach the range). The job checks for this first and
fails with the month and row count, leaving the table unchanged; those rows
have to be moved out of the DEFAULT partition before the month can be added.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable

from ai4i_core.logging import get_logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from bootstrap.config import get_settings
from bootstrap.database import platform_core_session

logger = get_logger(__name__)


@dataclass(frozen=True)
class PartitionedTable:
    name: str
    column: str
    retention_months: int
    # Renders a month start as the SQL literal of a range bound.
    bound: Callable[[date], str]


class DefaultPartitionHasRowsError(RuntimeError):
    pass


def _timestamptz_bound(month: date) -> str:
    # Explicit +00 offset, as in the migration, so the bound doesn't depend on
    # the session's TimeZone.
    return f"'{month.isoformat()} 00:00:00+00'"


def _date_bound(month: date) -> str:
    return f"'{month.isoformat()}'"


def _add_months(month: date, n: int) -> date:
    index = month.year * 12 + (month.month - 1) + n
    return date(index // 12, index % 12 + 1, 1)


def _partition_name(table: str, month: date) -> str:
    return f"{table}_{month.year:04d}_{month.month:02d}"


def _tables() -> list[PartitionedTable]:
    settings = get_settings()
    return [
        PartitionedTable("usage_events", "occurred_at", settings.USAGE_EVENTS_MONTHS_RETENTION, _timestamptz_bound),
        PartitionedTable("daily_usage", "usage_date", settings.DAILY_USAGE_MONTHS_RETENTION, _date_bound),
    ]


async def _partitions(session: AsyncSession, table: str) -> tuple[list[str], str | None]:
    """Month partitions and the DEFAULT partition of ``table``."""
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
            {"table": table},
        )
    ).all()
    months = [name for name, is_default in rows if not is_default]
    default = next((name for name, is_default in rows if is_default), None)
    return months, default


async def _create_months(
    session: AsyncSession, spec: PartitionedTable, existing: set[str], default: str | None, months: list[date]
) -> list[str]:
    created = []
    for month in months:
        name = _partition_name(spec.name, month)
        if name in existing:
            continue
        lower, upper = spec.bound(month), spec.bound(_add_months(month, 1))
        if default is not None:
            stray = (
                await session.execute(
                    text(
                        f'SELECT count(*) FROM "{default}" '
                        f'WHERE "{spec.column}" >= {lower} AND "{spec.column}" < {upper}'
                    )
                )
            ).scalar_one()
            if stray:
                raise DefaultPartitionHasRowsError(
                    f"{default} holds {stray} row(s) for {month:%Y-%m}; move them out before {name} can be created"
                )
        await session.execute(
            text(f'CREATE TABLE "{name}" PARTITION OF "{spec.name}" FOR VALUES FROM ({lower}) TO ({upper})')
        )
        created.append(name)
    return created


async def _drop_expired(
    session: AsyncSession, spec: PartitionedTable, existing: list[str], default: str | None, cutoff: date
) -> tuple[list[str], int]:
    pattern = re.compile(rf"^{re.escape(spec.name)}_(\d{{4}})_(\d{{2}})$")
    dropped = []
    for name in sorted(existing):
        match = pattern.match(name)
        # Only partitions named by month are ours to drop.
        if not match or date(int(match[1]), int(match[2]), 1) >= cutoff:
            continue
        await session.execute(text(f'ALTER TABLE "{spec.name}" DETACH PARTITION "{name}"'))
        await session.execute(text(f'DROP TABLE "{name}"'))
        dropped.append(name)

    purged = 0
    if default is not None:
        result = await session.execute(
            text(f'DELETE FROM "{default}" WHERE "{spec.column}" < {spec.bound(cutoff)}')
        )
        purged = result.rowcount or 0
    return dropped, purged


async def _rollover_table(spec: PartitionedTable, current: date, months_ahead: int) -> None:
    async with platform_core_session() as session:
        async with session.begin():
            locked = (
                await session.execute(
                    text("SELECT pg_try_advisory_xact_lock(hashtext(:key))"),
                    {"key": f"pyjob:monthly_partition_rollover:{spec.name}"},
                )
            ).scalar_one()
            if not locked:
                logger.warning("Partition rollover already running, skipping | table=%s", spec.name)
                return

            existing, default = await _partitions(session, spec.name)
            wanted = [_add_months(current, i) for i in range(months_ahead + 1)]
            created = await _create_months(session, spec, set(existing), default, wanted)

            cutoff = _add_months(current, -(spec.retention_months - 1))
            dropped, purged = await _drop_expired(session, spec, existing, default, cutoff)

    logger.info(
        "Partition rollover done | table=%s current=%s keep_from=%s created=%s dropped=%s default_rows_deleted=%d",
        spec.name, f"{current:%Y-%m}", f"{cutoff:%Y-%m}", created, dropped, purged,
    )


async def rollover(today: date) -> None:
    current = today.replace(day=1)
    months_ahead = get_settings().PARTITION_MONTHS_AHEAD
    failed = []
    # One table failing (e.g. stray rows in its DEFAULT partition) must not
    # stop the other from rolling over.
    for spec in _tables():
        try:
            await _rollover_table(spec, current, months_ahead)
        except Exception:
            logger.exception("Partition rollover failed | table=%s", spec.name)
            failed.append(spec.name)
    if failed:
        raise RuntimeError(f"Partition rollover failed for: {', '.join(failed)}")


async def run() -> None:
    logger.info("Starting monthly partition rollover")
    await rollover(datetime.now(timezone.utc).date())
