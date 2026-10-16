"""Where a Usage Dashboard period's Postgres figures come from.

usage_events (occurred_at in [start, end)) serves ``today``, and every other
period too until the daily_usage rollup is switched on
(USAGE_DAILY_ROLLUP_ENABLED, off by default). With it on, a period's whole
past days read daily_usage (usage_date, the IST day), and today, when the
period runs up to now (last 7 days, a custom range ending today), reads
usage_events: the rollup only has a day once it has ended. Callers query
each of period_sources(period) and add the results up; nothing read here is
written back. Both tables carry the same unit and cost columns; only the
time column, the total-cost column and the unit-label column are named
differently.

Usage rows only: the Budget and Applications tabs show billed usage, so
request rows (one per request: a status, no units or cost — see UsageEvent)
are left out, and so are daily_usage groups made only of them (requests that
failed before anything was billed).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time as day_start, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import Boolean, func, literal_column, not_, select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.sql.elements import ColumnElement

from app.core.config import settings
from app.models.pay_per_use.daily_usage import DailyUsage
from app.models.pay_per_use.usage_event import REQUEST_ROWS, UsageEvent
from app.utils.usage_period import IST, UsagePeriod, ist_midnight


@dataclass(frozen=True)
class PeriodSource:
    model: Any                      # UsageEvent or DailyUsage
    time_column: ColumnElement      # occurred_at / usage_date
    in_period: ColumnElement        # WHERE clause selecting the period's usage rows
    total_cost: ColumnElement       # total_cost / cost (generated)
    unit: ColumnElement             # unit_of_measurement / unit


def daily_rollup_enabled() -> bool:
    return settings.usage_daily_rollup_enabled


def _daily_usage_source(first_day: date, last_day: date) -> PeriodSource:
    return PeriodSource(
        model=DailyUsage,
        time_column=DailyUsage.usage_date,
        # daily_usage rows carry no status: a group made only of request
        # rows (REQUEST_ROWS) is one with no units and no cost.
        in_period=DailyUsage.usage_date.between(first_day, last_day)
        & ((DailyUsage.total_units > 0) | (DailyUsage.cost > 0)),
        total_cost=DailyUsage.cost,
        unit=DailyUsage.unit,
    )


def _usage_events_source(start: datetime, end: datetime) -> PeriodSource:
    return PeriodSource(
        model=UsageEvent,
        time_column=UsageEvent.occurred_at,
        in_period=(UsageEvent.occurred_at >= start) & (UsageEvent.occurred_at < end)
        & not_(literal_column(f"({REQUEST_ROWS})", Boolean)),
        total_cost=UsageEvent.total_cost,
        unit=UsageEvent.unit_of_measurement,
    )


def period_sources(period: UsagePeriod) -> list[PeriodSource]:
    """Where the period's usage is, earliest first. Without the rollup (or
    for ``today``): usage_events for the whole period. With it: daily_usage
    for the period's whole days, and usage_events for its last day when that
    is today, up to now (the period's end) — that day isn't rolled up yet."""
    if not (period.uses_daily_usage and daily_rollup_enabled()):
        return [_usage_events_source(period.start, period.end)]
    last_day_whole = period.end >= ist_midnight(period.to_date + timedelta(days=1))
    last_rolled_day = period.to_date if last_day_whole else period.to_date - timedelta(days=1)
    sources = []
    if last_rolled_day >= period.from_date:
        sources.append(_daily_usage_source(period.from_date, last_rolled_day))
    if not last_day_whole:
        sources.append(_usage_events_source(max(period.start, ist_midnight(period.to_date)), period.end))
    return sources


def tenant_pks(tenant_ids: list[str]) -> list[int]:
    """usage_events/daily_usage.tenant_id is an integer; tenant ids arrive as
    strings (quota_usage, query params)."""
    return [int(t) for t in tenant_ids if t and t.isdigit()]


async def usage_data_from(db: AsyncSession, period: UsagePeriod) -> Optional[datetime]:
    """When the data period_sources(period) read begins inside ``period``:
    ``period.start`` when the table holds rows from before it (the period is
    fully covered), else the first row inside the period, else None (no data
    for the period at all). Platform-wide on purpose: it marks when recording
    began, so a period before it reads as "no data" rather than as "no usage"
    for any one institution.

    Bounded on purpose — never min() over the whole table, which no index on
    usage_events can answer (BRIN can't serve a min) and would scan every
    partition: the "anything earlier?" probe stops at the first row it finds
    (partitions older than the period hold rows whenever it's covered), and
    the in-period min() only runs when there's nothing earlier, reading no
    more than the period query itself does (via the occurred_at BRIN)."""
    sources = period_sources(period)
    earliest = sources[0]     # the probe for earlier rows asks the source the period starts in
    if earliest.model is DailyUsage:
        before = DailyUsage.usage_date < period.from_date
    else:
        before = UsageEvent.occurred_at < period.start
    if await db.scalar(select(earliest.time_column).where(before).limit(1)) is not None:
        return period.start
    for source in sources:
        first = await db.scalar(select(func.min(source.time_column)).where(source.in_period))
        if first is not None:
            if not isinstance(first, datetime):  # daily_usage.usage_date: an IST day
                first = datetime.combine(first, day_start(), tzinfo=IST).astimezone(timezone.utc)
            return first
    return None
