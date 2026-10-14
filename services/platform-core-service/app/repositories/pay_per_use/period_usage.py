"""Where a Usage Dashboard period's Postgres figures come from.

usage_events (occurred_at in [start, end)) serves ``today``, and every other
period too until the daily_usage rollup is switched on
(USAGE_DAILY_ROLLUP_ENABLED, off by default). With it on, past periods read
daily_usage (usage_date, the IST day, between the period's first and last
day). Both tables carry the same unit and cost columns; only the time
column, the total-cost column and the unit-label column are named
differently.

Usage rows only: the Budget and Applications tabs show billed usage, so
request rows (one per request: a status, no units or cost — see UsageEvent)
are left out, and so are daily_usage groups made only of them (requests that
failed before anything was billed).

Days before usage_events begins come from the Prometheus backfill (pyjob
usage_backfill): daily_usage rows with source 'backfill', estimates, covering
the span usage_backfill records — up to the instant usage_events takes over,
so the two never overlap. period_sources() adds them to whichever source the
period reads; the rollup source reads rollup rows only.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time as day_start, timezone
from typing import Any, Optional

from sqlalchemy import Boolean, func, literal_column, not_, select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.sql.elements import ColumnElement

from app.core.config import settings
from app.models.pay_per_use.daily_usage import SOURCE_BACKFILL, SOURCE_ROLLUP, DailyUsage, UsageBackfill
from app.models.pay_per_use.usage_event import REQUEST_ROWS, UsageEvent
from app.utils.usage_period import IST, UsagePeriod


@dataclass(frozen=True)
class PeriodSource:
    model: Any                      # UsageEvent or DailyUsage
    time_column: ColumnElement      # occurred_at / usage_date
    in_period: ColumnElement        # WHERE clause selecting the period's usage rows
    total_cost: ColumnElement       # total_cost / cost (generated)
    unit: ColumnElement             # unit_of_measurement / unit


@dataclass(frozen=True)
class Backfill:
    """The span the Prometheus backfill covers: first_day's IST midnight up
    to until, where usage_events takes over. Figures inside it are estimates."""
    first_day: date
    until: datetime

    @property
    def start(self) -> datetime:
        return datetime.combine(self.first_day, day_start(), tzinfo=IST).astimezone(timezone.utc)

    def estimated_until(self, start: datetime, end: datetime) -> Optional[datetime]:
        """Where the estimates in [start, end) end, or None when the range
        doesn't overlap the backfill."""
        if start >= self.until or end <= self.start:
            return None
        return min(end, self.until)


async def get_backfill(db: AsyncSession) -> Optional[Backfill]:
    """The backfill's span, None when there's no backfill (one row by primary key)."""
    row = (await db.execute(select(UsageBackfill.first_day, UsageBackfill.until))).first()
    return Backfill(row.first_day, row.until) if row is not None else None


def daily_rollup_enabled() -> bool:
    return settings.usage_daily_rollup_enabled


def _daily_usage_source(period: UsagePeriod, source: str) -> PeriodSource:
    return PeriodSource(
        model=DailyUsage,
        time_column=DailyUsage.usage_date,
        # daily_usage rows carry no status: a group made only of request
        # rows (REQUEST_ROWS) is one with no units and no cost.
        in_period=(DailyUsage.source == source)
        & DailyUsage.usage_date.between(period.from_date, period.to_date)
        & ((DailyUsage.total_units > 0) | (DailyUsage.cost > 0)),
        total_cost=DailyUsage.cost,
        unit=DailyUsage.unit,
    )


def period_sources(period: UsagePeriod, backfill: Optional[Backfill]) -> list[PeriodSource]:
    """period_source(period), plus the backfill's rows when the period
    overlaps it. Query each and add the results up."""
    sources = [period_source(period)]
    if backfill is not None and backfill.estimated_until(period.start, period.end) is not None:
        sources.append(_daily_usage_source(period, SOURCE_BACKFILL))
    return sources


def period_source(period: UsagePeriod) -> PeriodSource:
    """Where the period's recorded usage is: the rollup's rows or usage_events
    (the backfill's estimates aside, see period_sources)."""
    if period.uses_daily_usage and daily_rollup_enabled():
        return _daily_usage_source(period, SOURCE_ROLLUP)
    return PeriodSource(
        model=UsageEvent,
        time_column=UsageEvent.occurred_at,
        in_period=(UsageEvent.occurred_at >= period.start) & (UsageEvent.occurred_at < period.end)
        & not_(literal_column(f"({REQUEST_ROWS})", Boolean)),
        total_cost=UsageEvent.total_cost,
        unit=UsageEvent.unit_of_measurement,
    )


def tenant_pks(tenant_ids: list[str]) -> list[int]:
    """usage_events/daily_usage.tenant_id is an integer; tenant ids arrive as
    strings (quota_usage, query params)."""
    return [int(t) for t in tenant_ids if t and t.isdigit()]


async def usage_data_from(
    db: AsyncSession, period: UsagePeriod, backfill: Optional[Backfill] = None,
) -> Optional[datetime]:
    """When the data period_source(period) reads begins inside ``period``:
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
    more than the period query itself does (via the occurred_at BRIN).

    With a ``backfill`` overlapping the period, data begins where the
    backfill does (it ends where usage_events takes over)."""
    if backfill is not None and backfill.estimated_until(period.start, period.end) is not None:
        return max(period.start, backfill.start)
    source = period_source(period)
    if source.model is DailyUsage:
        before = DailyUsage.usage_date < period.from_date
    else:
        before = UsageEvent.occurred_at < period.start
    if await db.scalar(select(source.time_column).where(before).limit(1)) is not None:
        return period.start
    first = await db.scalar(select(func.min(source.time_column)).where(source.in_period))
    if first is None:
        return None
    if not isinstance(first, datetime):  # daily_usage.usage_date: an IST day
        first = datetime.combine(first, day_start(), tzinfo=IST).astimezone(timezone.utc)
    return first
