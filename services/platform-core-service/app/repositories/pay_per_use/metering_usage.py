"""usage_events / daily_usage reads behind the Usage Dashboard's metering tabs
(Overview, Model consumption) — see UsageEventsMeteringService.

Requests and failures are counted from request rows only (status_code set:
one per API-key request, written from its request span), units from usage
rows (see UsageEvent), so a request is counted once whatever usage rows it
has. A request is failed when its status is 400 or above.

Whole IST days read the daily_usage rollup when it's enabled and has the day;
everything else — today, partial days at a range's edges, days not rolled up
yet — reads usage_events, so a day missing from the rollup is never shown as
zero. Both give the same figures: the rollup counts requests the same way
(rows with a status_code, distinct correlation ids).
"""
from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pay_per_use.usage_event import REQUEST_ROWS
from app.repositories.pay_per_use.period_usage import daily_rollup_enabled
from app.utils.usage_period import IST

# Grouping dimensions: (daily_usage expression, usage_events expression).
_GROUPS = {
    "tenant_id": ("tenant_id", "tenant_id"),
    "service_id": ("service_id", "service_id"),
    "inference_type_id": ("inference_type_id", "inference_type_id"),
    "day": ("usage_date", "(occurred_at AT TIME ZONE 'Asia/Kolkata')::date"),
}


@dataclass
class UsageAgg:
    """Requests, failures and units for one group."""
    requests: int = 0
    failed: int = 0
    units: Decimal = field(default_factory=Decimal)
    cached_units: Decimal = field(default_factory=Decimal)
    output_units: Decimal = field(default_factory=Decimal)

    @property
    def successful(self) -> int:
        return self.requests - self.failed

    def add(self, row: Any) -> None:
        self.requests += int(row.requests or 0)
        self.failed += int(row.failed or 0)
        self.units += Decimal(row.units or 0)
        self.cached_units += Decimal(row.cached_units or 0)
        self.output_units += Decimal(row.output_units or 0)


def _ist_midnight(day: date) -> datetime:
    return datetime.combine(day, time(), tzinfo=IST).astimezone(timezone.utc)


def _ist_day(instant: datetime) -> date:
    return instant.astimezone(IST).date()


def _merge_intervals(intervals: Iterable[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    merged: list[tuple[datetime, datetime]] = []
    for start, end in sorted(i for i in intervals if i[0] < i[1]):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


class MeteringUsageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        # The metering routes gather several reads at once, and they share one
        # request-scoped AsyncSession, which isn't safe for concurrent use:
        # every query on it goes through this lock.
        self.lock = asyncio.Lock()

    async def _all(self, sql: str, params: dict) -> list:
        async with self.lock:
            return (await self._db.execute(text(sql), params)).all()

    async def _scalar(self, sql: str, params: dict):
        async with self.lock:
            return await self._db.scalar(text(sql), params)

    @staticmethod
    def _filters(tenant_id: Optional[int], type_ids: Optional[list[int]], params: dict) -> str:
        clauses = []
        if tenant_id is not None:
            clauses.append("tenant_id = :tenant_id")
            params["tenant_id"] = tenant_id
        if type_ids is not None:
            clauses.append("inference_type_id = ANY(:type_ids)")
            params["type_ids"] = list(type_ids)
        return "".join(f" AND {c}" for c in clauses)

    @staticmethod
    def _rollup_days(start: datetime, end: datetime) -> list[date]:
        """Whole IST days inside [start, end), today excluded (not complete):
        the days the rollup can answer."""
        if not daily_rollup_enabled():
            return []
        today = _ist_day(datetime.now(timezone.utc))
        day = _ist_day(start)
        if _ist_midnight(day) < start:
            day += timedelta(days=1)
        days = []
        while _ist_midnight(day + timedelta(days=1)) <= end and day < today:
            days.append(day)
            day += timedelta(days=1)
        return days

    async def aggregate(
        self,
        start: datetime,
        end: datetime,
        group_by: tuple[str, ...] = (),
        *,
        tenant_id: Optional[int] = None,
        type_ids: Optional[list[int]] = None,
    ) -> dict[tuple, UsageAgg]:
        """{group key: UsageAgg} over [start, end), grouped by ``group_by``
        (any of tenant_id, service_id, inference_type_id, day — the IST day).
        ``type_ids`` keeps those catalogue types only ([] matches nothing)."""
        result: dict[tuple, UsageAgg] = {}
        days = self._rollup_days(start, end)
        rolled: set[date] = set()

        if days:
            params: dict = {"days": days}
            where = self._filters(tenant_id, type_ids, params)
            cols = [_GROUPS[g][0] for g in group_by]
            select_cols = ", ".join(f"{c} AS g{i}" for i, c in enumerate(cols))
            rows = await self._all(
                f"SELECT usage_date AS d{', ' + select_cols if cols else ''},"
                " sum(request_count) AS requests, sum(failed_count) AS failed,"
                " sum(total_units) AS units, sum(cached_input_units) AS cached_units,"
                " sum(output_units) AS output_units"
                f" FROM daily_usage WHERE usage_date = ANY(:days){where}"
                f" GROUP BY usage_date{''.join(', ' + c for c in cols)}",
                params,
            )
            for row in rows:
                rolled.add(row.d)
                key = tuple(getattr(row, f"g{i}") for i in range(len(cols)))
                result.setdefault(key, UsageAgg()).add(row)

        # Everything the rollup didn't answer: partial days at the edges, today,
        # and whole days it has no rows for (not rolled up yet, or no usage).
        intervals = [(start, end)] if not days else [
            (start, _ist_midnight(days[0])),
            (_ist_midnight(days[-1] + timedelta(days=1)), end),
            *((_ist_midnight(d), _ist_midnight(d + timedelta(days=1))) for d in days if d not in rolled),
        ]
        intervals = _merge_intervals(intervals)
        if intervals:
            params = {}
            ranges = []
            for i, (s, e) in enumerate(intervals):
                ranges.append(f"(occurred_at >= :s{i} AND occurred_at < :e{i})")
                params[f"s{i}"], params[f"e{i}"] = s, e
            where = self._filters(tenant_id, type_ids, params)
            exprs = [_GROUPS[g][1] for g in group_by]
            select_cols = "".join(f"{e} AS g{i}, " for i, e in enumerate(exprs))
            group_clause = f" GROUP BY {', '.join(exprs)}" if exprs else ""
            rows = await self._all(
                f"SELECT {select_cols}"
                " count(DISTINCT correlation_id) FILTER (WHERE status_code IS NOT NULL) AS requests,"
                " count(DISTINCT correlation_id) FILTER (WHERE status_code >= 400) AS failed,"
                " sum(total_units) AS units, sum(cached_input_units) AS cached_units,"
                " sum(output_units) AS output_units"
                f" FROM usage_events WHERE ({' OR '.join(ranges)}){where}{group_clause}",
                params,
            )
            for row in rows:
                if not exprs and row.requests == 0 and row.units is None:
                    continue  # the ungrouped aggregate over no rows
                key = tuple(getattr(row, f"g{i}") for i in range(len(exprs)))
                result.setdefault(key, UsageAgg()).add(row)
        return result

    async def request_buckets(
        self,
        start: datetime,
        end: datetime,
        step_seconds: int,
        *,
        tenant_id: Optional[int] = None,
        type_ids: Optional[list[int]] = None,
    ) -> dict[int, tuple[int, int]]:
        """{bucket index: (requests, failed)} over [start, end) in buckets of
        ``step_seconds`` from ``start`` — from usage_events, for sub-day steps
        (the rollup has nothing finer than a day)."""
        params: dict = {"start": start, "end": end, "step": step_seconds}
        where = self._filters(tenant_id, type_ids, params)
        rows = await self._all(
            "SELECT floor(extract(epoch FROM occurred_at - :start) / :step)::int AS bucket,"
            " count(DISTINCT correlation_id) FILTER (WHERE status_code IS NOT NULL) AS requests,"
            " count(DISTINCT correlation_id) FILTER (WHERE status_code >= 400) AS failed"
            f" FROM usage_events WHERE occurred_at >= :start AND occurred_at < :end{where}"
            " GROUP BY 1",
            params,
        )
        return {row.bucket: (int(row.requests), int(row.failed)) for row in rows}

    async def request_rows_from(self, start: datetime, end: datetime) -> Optional[datetime]:
        """When request rows begin inside [start, end): ``start`` when there
        are request rows from before it (fully covered), else the first one
        inside, else None. Both reads use the partial index on request rows
        (ix_usage_events_request_rows), never a scan."""
        before = await self._scalar(
            f"SELECT 1 FROM usage_events WHERE occurred_at < :start AND {REQUEST_ROWS} LIMIT 1",
            {"start": start},
        )
        if before is not None:
            return start
        return await self._scalar(
            f"SELECT min(occurred_at) FROM usage_events"
            f" WHERE occurred_at >= :start AND occurred_at < :end AND {REQUEST_ROWS}",
            {"start": start, "end": end},
        )

    async def first_usage(self, tenant_id: Optional[int]) -> Optional[datetime]:
        """When API-key usage begins: the tenant's first usage_events row (by
        its (tenant_id, occurred_at) index), or platform-wide the first day in
        the rollup — usage_events has no index to answer a platform-wide min.
        The rollup only covers the days since it started running, so rows
        from before its first day are checked too: a range read of just that
        stretch (BRIN). Without a rollup, the whole table is read."""
        if tenant_id is not None:
            return await self._scalar(
                "SELECT min(occurred_at) FROM usage_events WHERE tenant_id = :tenant_id",
                {"tenant_id": tenant_id},
            )
        first_day = (
            await self._scalar("SELECT min(usage_date) FROM daily_usage", {})
            if daily_rollup_enabled() else None
        )
        if first_day is None:
            return await self._scalar("SELECT min(occurred_at) FROM usage_events", {})
        earlier = await self._scalar(
            "SELECT min(occurred_at) FROM usage_events WHERE occurred_at < :before",
            {"before": _ist_midnight(first_day)},
        )
        return earlier or _ist_midnight(first_day)
