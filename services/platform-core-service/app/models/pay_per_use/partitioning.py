"""Monthly range partitions of usage_events and daily_usage.

The ORM models map the partitioned parent tables only. Postgres routes every
row written to the parent into its month's partition, so code never names a
partition. The partitions themselves are DDL: migrations 3b5d7f9a1c2e and
4c6e8a0b2d3f create the current and next month plus a DEFAULT partition, and
the scheduled partition job creates each later month with
``monthly_partition_ddl`` before that month starts.

A month whose rows have already landed in the DEFAULT partition can't get its
own partition until those rows are moved out, so the job must stay ahead.
"""
from datetime import date

USAGE_EVENTS = "usage_events"
DAILY_USAGE = "daily_usage"

# usage_events is partitioned on occurred_at (timestamptz), by UTC month, so
# its bounds carry an explicit +00 offset and don't depend on the session's
# TimeZone. daily_usage is partitioned on usage_date (a date), so plain dates.
_TIMESTAMP_BOUNDS = {USAGE_EVENTS: True, DAILY_USAGE: False}


def month_start(day: date) -> date:
    return day.replace(day=1)


def next_month_start(day: date) -> date:
    first = month_start(day)
    return date(first.year + first.month // 12, first.month % 12 + 1, 1)


def partition_name(table: str, month: date) -> str:
    """e.g. usage_events_2026_10."""
    return f"{table}_{month:%Y_%m}"


def default_partition_name(table: str) -> str:
    return f"{table}_default"


def monthly_partition_ddl(table: str, month: date) -> str:
    """CREATE TABLE ... PARTITION OF for the month containing ``month``.

    Indexes, the primary key, constraints and generated columns of the parent
    are applied to the new partition by Postgres; nothing else is needed.
    """
    if table not in _TIMESTAMP_BOUNDS:
        raise ValueError(f"{table} is not a monthly-partitioned usage table")
    start, end = month_start(month), next_month_start(month)
    if _TIMESTAMP_BOUNDS[table]:
        bounds = f"'{start.isoformat()} 00:00:00+00'", f"'{end.isoformat()} 00:00:00+00'"
    else:
        bounds = f"'{start.isoformat()}'", f"'{end.isoformat()}'"
    return (
        f"CREATE TABLE IF NOT EXISTS {partition_name(table, start)} PARTITION OF {table} "
        f"FOR VALUES FROM ({bounds[0]}) TO ({bounds[1]})"
    )
