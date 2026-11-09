"""usage_events / daily_usage reads behind the Usage Dashboard's metering tabs
(Overview, Model consumption) — see UsageEventsMeteringService.

Requests and failures are counted from request rows (one per API-key
request, written from its request span: one row, one request — not distinct
correlation ids, which a client can reuse across calls via X-Correlation-ID),
units from usage rows (see UsageEvent), so a request is counted once whatever
usage rows it has. Rows from before the cut-over (PRE_CUTOVER_ROWS) are
counted by distinct correlation id, as the request they stand in for may have
several. A request is failed when its status is 400 or above. Fallback
requests (sent to a fallback service) are request rows with sent_to_fallback (daily_usage.fallback_count
in the rollup, a JSON of count / success / failure); they are part of the
request total, never added to it. A fallback request failed when its status
is 400 or above; it is part of the failures too.

Whole IST days read the daily_usage rollup when it has the day; everything
else — today, partial days at a range's edges, days not rolled up yet —
reads usage_events, so a day missing from the rollup is never shown as zero.
The rollup counts requests the same way (request rows one each, older
status-carrying rows once per correlation id), so both paths agree.

pyjob's daily_usage_consolidation drops usage_events days past its retention
once rolled up; only daily_usage has them then (a dropped day: rollup rows,
no usage_events rows). A partial day at a range's edge on such a day can't be
cut at the hour any more, so it counts whole when the range runs to its end
(a range starting mid-day) and not at all otherwise (a range ending mid-day):
back-to-back ranges still count each day once. Sub-day buckets
(request_buckets) have no rows there, and the reads of when data begins fall
back to daily_usage's rollup rows.
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

from app.models.pay_per_use.usage_event import PRE_CUTOVER_ROWS, REQUEST_ROWS
from app.utils.usage_period import IST

# Requests and failed requests among usage_events rows (see the module docstring).
_REQUESTS = (
    f"count(*) FILTER (WHERE {REQUEST_ROWS})"
    f" + count(DISTINCT correlation_id) FILTER (WHERE {PRE_CUTOVER_ROWS})"
)
_FAILED = (
    f"count(*) FILTER (WHERE {REQUEST_ROWS} AND status_code >= 400)"
    f" + count(DISTINCT correlation_id) FILTER (WHERE {PRE_CUTOVER_ROWS} AND status_code >= 400)"
)
# Server errors and timeouts (status 500 or above): part of the failures.
_SERVER_ERRORS = (
    f"count(*) FILTER (WHERE {REQUEST_ROWS} AND status_code >= 500)"
    f" + count(DISTINCT correlation_id) FILTER (WHERE {PRE_CUTOVER_ROWS} AND status_code >= 500)"
)
# Requests sent to a fallback service: request rows only (older rows predate the flag).
_FALLBACK = f"count(*) FILTER (WHERE {REQUEST_ROWS} AND sent_to_fallback)"
# Fallback requests that still failed: part of both _FALLBACK and _FAILED.
_FALLBACK_FAILED = f"count(*) FILTER (WHERE {REQUEST_ROWS} AND sent_to_fallback AND status_code >= 400)"

# Grouping dimensions: (daily_usage expression, usage_events expression).
_GROUPS = {
    "tenant_id": ("tenant_id", "tenant_id"),
    "service_id": ("service_id", "service_id"),
    "inference_type_id": ("inference_type_id", "inference_type_id"),
    "day": ("usage_date", "(occurred_at AT TIME ZONE 'Asia/Kolkata')::date"),
}


@dataclass
class UsageAgg:
    """Requests, failures, requests sent to a fallback and units for one group."""
    requests: int = 0
    failed: int = 0
    fallback: int = 0
    fallback_failed: int = 0
    units: Decimal = field(default_factory=Decimal)
    cached_units: Decimal = field(default_factory=Decimal)
    output_units: Decimal = field(default_factory=Decimal)

    @property
    def successful(self) -> int:
        return self.requests - self.failed

    @property
    def fallback_successful(self) -> int:
        return self.fallback - self.fallback_failed

    def add(self, row: Any) -> None:
        self.requests += int(row.requests or 0)
        self.failed += int(row.failed or 0)
        self.fallback += int(row.fallback or 0)
        self.fallback_failed += int(row.fallback_failed or 0)
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
    def _day_pieces(start: datetime, end: datetime) -> list[tuple[date, datetime, datetime]]:
        """[start, end) cut at IST midnights: (day, piece start, piece end)."""
        pieces = []
        day = _ist_day(start)
        while _ist_midnight(day) < end:
            piece = (max(start, _ist_midnight(day)), min(end, _ist_midnight(day + timedelta(days=1))))
            if piece[0] < piece[1]:
                pieces.append((day, *piece))
            day += timedelta(days=1)
        return pieces

    async def _dropped(self, days: Iterable[date]) -> set[date]:
        """Those of ``days`` whose usage_events rows were dropped: in
        daily_usage, with no usage_events row left (see the module docstring)."""
        days = sorted(set(days))
        if not days:
            return set()
        rows = await self._all(
            "SELECT d FROM unnest(CAST(:days AS date[])) AS d"
            " WHERE EXISTS (SELECT 1 FROM daily_usage u WHERE u.usage_date = d)"
            " AND NOT EXISTS (SELECT 1 FROM usage_events e"
            "  WHERE e.occurred_at >= d::timestamp AT TIME ZONE 'Asia/Kolkata'"
            "  AND e.occurred_at < (d + 1)::timestamp AT TIME ZONE 'Asia/Kolkata')",
            {"days": days},
        )
        return {row.d for row in rows}

    async def _split_days(
        self, start: datetime, end: datetime,
    ) -> tuple[list[date], list[tuple[date, datetime, datetime]], set[date]]:
        """[start, end) as (whole days for the rollup, partial pieces, dropped
        partial days). A partial day whose usage_events rows are gone counts
        whole when the range runs to its end, else not at all (see the module
        docstring), so it joins the whole days or is left out."""
        today = _ist_day(datetime.now(timezone.utc))
        pieces = self._day_pieces(start, end)
        # Whole days before today (complete): the days the rollup can answer.
        days = [
            d for d, s, e in pieces
            if d < today and s == _ist_midnight(d) and e == _ist_midnight(d + timedelta(days=1))
        ]
        partial = [(d, s, e) for d, s, e in pieces if d not in days]
        # Only edge days matter: a whole day the rollup has is read from it.
        dropped = await self._dropped({d for d, _, _ in partial if d < today})
        days = sorted(days + [
            d for d, _, e in partial if d in dropped and e == _ist_midnight(d + timedelta(days=1))
        ])
        return days, partial, dropped

    async def _add_rollup(
        self, result: dict[tuple, UsageAgg], days: list[date], group_by: tuple[str, ...],
        tenant_id: Optional[int], type_ids: Optional[list[int]],
    ) -> set[date]:
        """Add ``days``' daily_usage rows to ``result``; the days it had rows for."""
        if not days:
            return set()
        params: dict = {"days": days}
        where = self._filters(tenant_id, type_ids, params)
        cols = [_GROUPS[g][0] for g in group_by]
        select_cols = ", ".join(f"{c} AS g{i}" for i, c in enumerate(cols))
        rows = await self._all(
            f"SELECT usage_date AS d{', ' + select_cols if cols else ''},"
            " sum(request_count) AS requests, sum(failed_count) AS failed,"
            " sum((fallback_count->>'count')::bigint) AS fallback,"
            " sum((fallback_count->>'failure')::bigint) AS fallback_failed,"
            " sum(total_units) AS units, sum(cached_input_units) AS cached_units,"
            " sum(output_units) AS output_units"
            f" FROM daily_usage WHERE usage_date = ANY(:days){where}"
            f" GROUP BY usage_date{''.join(', ' + c for c in cols)}",
            params,
        )
        for row in rows:
            key = tuple(getattr(row, f"g{i}") for i in range(len(cols)))
            result.setdefault(key, UsageAgg()).add(row)
        return {row.d for row in rows}

    async def _add_usage_events(
        self, result: dict[tuple, UsageAgg], intervals: list[tuple[datetime, datetime]],
        group_by: tuple[str, ...], tenant_id: Optional[int], type_ids: Optional[list[int]],
    ) -> None:
        """Add the usage_events rows inside ``intervals`` to ``result``."""
        if not intervals:
            return
        params: dict = {}
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
            f" {_REQUESTS} AS requests, {_FAILED} AS failed, {_FALLBACK} AS fallback,"
            f" {_FALLBACK_FAILED} AS fallback_failed,"
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
        days, partial, dropped = await self._split_days(start, end)
        rolled = await self._add_rollup(result, days, group_by, tenant_id, type_ids)
        # Everything the rollup didn't answer: partial days at the edges, today,
        # and whole days it has no rows for (not rolled up yet, or no usage).
        # Dropped days have no usage_events rows to add.
        intervals = _merge_intervals([
            *((s, e) for d, s, e in partial if d not in dropped),
            *((_ist_midnight(d), _ist_midnight(d + timedelta(days=1))) for d in days if d not in rolled),
        ])
        await self._add_usage_events(result, intervals, group_by, tenant_id, type_ids)
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
        (the rollup has nothing finer than a day), so none on days whose
        usage_events rows were dropped."""
        params: dict = {"start": start, "end": end, "step": step_seconds}
        where = self._filters(tenant_id, type_ids, params)
        rows = await self._all(
            "SELECT floor(extract(epoch FROM occurred_at - :start) / :step)::int AS bucket,"
            f" {_REQUESTS} AS requests, {_FAILED} AS failed"
            f" FROM usage_events WHERE occurred_at >= :start AND occurred_at < :end{where}"
            " GROUP BY 1",
            params,
        )
        return {row.bucket: (int(row.requests), int(row.failed)) for row in rows}

    async def request_rows_from(self, start: datetime, end: datetime) -> Optional[datetime]:
        """When request rows begin inside [start, end): ``start`` when there
        are request rows from before it (fully covered), else the first one
        inside, else None. The usage_events reads use the partial index on
        request rows (ix_usage_events_request_rows), never a scan. With none
        before start (their days were dropped), daily_usage's rollup rows
        answer by the day: a rolled-up day with requests before start's
        covers it, and the first one inside the range before the first
        usage_events request row begins at its midnight (or at start)."""
        before = await self._scalar(
            f"SELECT 1 FROM usage_events WHERE occurred_at < :start AND {REQUEST_ROWS} LIMIT 1",
            {"start": start},
        )
        if before is not None:
            return start
        first_day = _ist_day(start)
        if await self._scalar(
            "SELECT 1 FROM daily_usage WHERE source = 'rollup' AND request_count > 0"
            " AND usage_date < :before LIMIT 1",
            {"before": first_day},
        ) is not None:
            return start
        first = await self._scalar(
            f"SELECT min(occurred_at) FROM usage_events"
            f" WHERE occurred_at >= :start AND occurred_at < :end AND {REQUEST_ROWS}",
            {"start": start, "end": end},
        )
        # A dropped day before the first usage_events request row begins earlier.
        last_day = _ist_day(first) - timedelta(days=1) if first else _ist_day(end - timedelta(microseconds=1))
        dropped_first = await self._scalar(
            "SELECT min(usage_date) FROM daily_usage WHERE source = 'rollup' AND request_count > 0"
            " AND usage_date BETWEEN :first_day AND :last_day",
            {"first_day": first_day, "last_day": last_day},
        )
        if dropped_first is not None:
            return max(start, _ist_midnight(dropped_first))
        return first

    async def fallbacks_recorded_by(self, at: datetime) -> bool:
        """Whether request rows carried the fallback flag by ``at``: the last
        request row before it has a response time, written with the flag (rows
        from before migration ea3961c258e4 have neither). One step back along
        the request-row index (ix_usage_events_request_rows). With no
        usage_events request row before ``at`` (their days were dropped), a
        rolled-up day before at's with response times answers it (the
        backfill's estimates don't count: the flag wasn't recorded then)."""
        last = await self._scalar(
            f"SELECT response_time_ms IS NOT NULL FROM usage_events WHERE occurred_at < :at AND {REQUEST_ROWS}"
            " ORDER BY occurred_at DESC LIMIT 1",
            {"at": at},
        )
        if last is not None:
            return bool(last)
        return await self._scalar(
            "SELECT 1 FROM daily_usage WHERE source = 'rollup' AND response_time_count > 0"
            " AND usage_date < :before LIMIT 1",
            {"before": _ist_day(at)},
        ) is not None

    async def server_errors(self, start: datetime, end: datetime) -> tuple[int, int]:
        """(requests, server errors) in [start, end), both from usage_events,
        which has every day's status codes. Not from daily_usage: days rolled
        up before migration ea3961c258e4 keep server_error_count at 0."""
        row = (await self._all(
            f"SELECT {_REQUESTS} AS requests, {_SERVER_ERRORS} AS server_errors FROM usage_events"
            " WHERE occurred_at >= :start AND occurred_at < :end",
            {"start": start, "end": end},
        ))[0]
        return int(row.requests or 0), int(row.server_errors or 0)

    async def response_times_from(self, end: datetime) -> Optional[datetime]:
        """When request rows began carrying a response time (and the fallback
        flag, written with it), if before ``end``; None when not yet. Walks
        the request-row index (ix_usage_events_request_rows) in time order."""
        return await self._scalar(
            f"SELECT occurred_at FROM usage_events WHERE occurred_at < :end AND {REQUEST_ROWS}"
            " AND response_time_ms IS NOT NULL ORDER BY occurred_at LIMIT 1",
            {"end": end},
        )

    async def response_time_p95(self, start: datetime, end: datetime) -> Optional[float]:
        """The 95th-percentile response time (ms) of the requests in
        [start, end), failed ones included; None when none has one. Read from
        usage_events: a percentile can't be combined from daily figures."""
        return await self._scalar(
            "SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY response_time_ms) FROM usage_events"
            f" WHERE occurred_at >= :start AND occurred_at < :end AND {REQUEST_ROWS}"
            " AND response_time_ms IS NOT NULL",
            {"start": start, "end": end},
        )

    async def first_usage(self, tenant_id: Optional[int]) -> Optional[datetime]:
        """When API-key usage begins: the first day in the rollup (the
        tenant's, by ix_daily_usage_tenant_date), as usage_events drops old
        days. The tenant's first usage_events row on or before that day (by
        its (tenant_id, occurred_at) index) gives the exact time, while that
        day is kept. Platform-wide, usage_events has no index to answer a min,
        so only the stretch before the rollup's first day is read (BRIN): the
        rollup only covers the days since it started running. With no rollup
        rows, usage_events alone answers."""
        if tenant_id is not None:
            first_day = await self._scalar(
                "SELECT min(usage_date) FROM daily_usage WHERE tenant_id = :tenant_id", {"tenant_id": tenant_id},
            )
            if first_day is None:
                return await self._scalar(
                    "SELECT min(occurred_at) FROM usage_events WHERE tenant_id = :tenant_id",
                    {"tenant_id": tenant_id},
                )
            earlier = await self._scalar(
                "SELECT min(occurred_at) FROM usage_events WHERE tenant_id = :tenant_id AND occurred_at < :before",
                {"tenant_id": tenant_id, "before": _ist_midnight(first_day + timedelta(days=1))},
            )
            return earlier or _ist_midnight(first_day)
        first_day = await self._scalar("SELECT min(usage_date) FROM daily_usage", {})
        if first_day is None:
            return await self._scalar("SELECT min(occurred_at) FROM usage_events", {})
        earlier = await self._scalar(
            "SELECT min(occurred_at) FROM usage_events WHERE occurred_at < :before",
            {"before": _ist_midnight(first_day)},
        )
        return earlier or _ist_midnight(first_day)
