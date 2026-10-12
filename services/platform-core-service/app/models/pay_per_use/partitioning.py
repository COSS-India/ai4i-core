"""Range partitions of usage_events (by UTC day) and daily_usage (by month).

The ORM models map the partitioned parent tables only. Postgres routes every
row written to the parent into its partition, so code never names a
partition. The partitions themselves are DDL, plus a DEFAULT partition on each
table:

- usage_events: migration 3b5d7f9a1c2e creates month partitions. pyjob's
  daily_usage_consolidation job converts them into day partitions
  (usage_events_YYYY_MM_DD) on its first run, then keeps the days ahead
  created and drops expired ones every day.
- daily_usage: migration 4c6e8a0b2d3f creates the current and next month, and
  pyjob's monthly_partition_rollover job creates each later month, as
  ``monthly_partition_ddl`` does, before that month starts.

A month whose rows have already landed in daily_usage's DEFAULT partition
can't get its own partition until those rows are moved out, so the job must
stay ahead.
"""
from datetime import date

USAGE_EVENTS = "usage_events"
DAILY_USAGE = "daily_usage"


def month_start(day: date) -> date:
    return day.replace(day=1)


def next_month_start(day: date) -> date:
    first = month_start(day)
    return date(first.year + first.month // 12, first.month % 12 + 1, 1)


def partition_name(table: str, month: date) -> str:
    """e.g. daily_usage_2026_10."""
    return f"{table}_{month:%Y_%m}"


def default_partition_name(table: str) -> str:
    return f"{table}_default"


def monthly_partition_ddl(table: str, month: date) -> str:
    """CREATE TABLE ... PARTITION OF for the month containing ``month``.

    Indexes, the primary key, constraints and generated columns of the parent
    are applied to the new partition by Postgres; nothing else is needed.
    """
    if table != DAILY_USAGE:
        raise ValueError(f"{table} is not a monthly-partitioned usage table")
    # daily_usage is partitioned on usage_date (a date), so plain date bounds.
    start, end = month_start(month), next_month_start(month)
    return (
        f"CREATE TABLE IF NOT EXISTS {partition_name(table, start)} PARTITION OF {table} "
        f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')"
    )
