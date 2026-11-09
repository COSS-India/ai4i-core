"""Daily partitions for usage_events and the daily_usage rollup.

Run by k8s every day at 00:00 IST (30 18 * * * in UTC). Days are IST days,
the Usage Dashboard's day: usage_events is partitioned on occurred_at by IST
day, and daily_usage.usage_date is the IST day of it,
(occurred_at AT TIME ZONE 'Asia/Kolkata')::date (see the
create_daily_usage_table migration). Timestamps stay UTC; only the day
boundaries are IST midnight.

1. Partitions of usage_events, in one transaction:

   - Every partition that isn't one IST day, named for that day
     (usage_events_YYYY_MM_DD from IST midnight to the next), is detached
     and its rows are moved into IST day partitions: the UTC month partitions
     the migration creates, and UTC day partitions from before days were IST.
     This only does work on the first run after the migration or that change;
     later runs find nothing to convert.
   - Day partitions are created for today and the next USAGE_EVENTS_DAYS_AHEAD
     days, and for every earlier day that has rows to restore — except the
     DEFAULT partition's days before the retention cutoff: a past day with
     no partition is one step 3 dropped, so those rows arrived late and stay
     in DEFAULT for step 3 to add. Rows the DEFAULT partition holds for a
     day being created are moved into it first, since Postgres refuses the
     new range otherwise.
   - Past day partitions are dropped by step 3 only.

   The parent is locked ACCESS EXCLUSIVE for the transaction, so writers wait
   instead of sending rows to the DEFAULT partition mid-conversion. The
   conversion rewrites every row once; later runs only create empty
   partitions, which is quick.

2. Rollup of yesterday and the USAGE_ROLLUP_LOOKBACK_DAYS before it into
   daily_usage, one transaction per day, so events that arrive late are
   picked up. Each day is aggregated per dimension key and upserted; rows of
   that day the run did not write (a combination that no longer exists) are
   deleted. billing_month is the UTC month of occurred_at, as the PPU
   consumer bills it, so the 00:00-05:30 IST rows of the 1st get their own
   row under the previous month. Names come from tiers, mm_services and mm_models here and from
   tenants and applications in the auth DB. Requests are counted from the
   rows that carry a status_code: a request row (status set, no units —
   written once per API-key request) counts one each, so calls that reuse an
   X-Correlation-ID still count separately; a usage row from before request
   rows existed (status set, with units) stands in for its request and counts
   once per correlation id, as one request can have several. Rows without a
   status_code add units and cost only. A request is failed when its status
   is 400 or above, and a server error (server_error_count, the platform's
   own failures: 5xx and timeouts) when it is 500 or above. fallback_count
   is a JSON {"count", "success", "failure"} of the request rows sent to a
   fallback, split by status (failure when 400 or above). It,
   total_response_time_ms and response_time_count come from request rows
   only, which carry sent_to_fallback and response_time_ms;
   response_time_count is the average's divisor, as rows from before
   response_time_ms have none.

3. Retention: every usage_events day before the last
   USAGE_EVENTS_RETENTION_DAYS closed days is dropped, oldest first, one
   transaction per day with usage_events locked ACCESS EXCLUSIVE, so no row
   can land in the day between its last rollup and the drop. A day that
   still has its partition is rolled up a last time (picking up anything
   that arrived since the lookback last read it), then its partition and
   any DEFAULT rows of it are dropped; a failure rolls the whole day back,
   partition included, so the next run rolls it up again. A day with rows
   in DEFAULT only was dropped before: those rows arrived late (no
   partition to land in), so they are added to the day's daily_usage rows
   instead of replacing them, and deleted. A day with backfill rows
   (source = 'backfill', see services/pyjob/backfill) is dropped without a
   rollup: the dashboard already shows the backfill for it. The step is
   skipped when step 1 or any rollup failed in the same run.

   The retention is more than the lookback (bootstrap.config enforces it),
   so the rollup never re-reads a dropped day.

Re-running is safe: every step converges to the same state. A
transaction-level advisory lock per step makes an overlapping run skip the
step instead of racing; retention takes the rollup's lock.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from ai4i_core.logging import get_logger
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from bootstrap.config import get_settings
from bootstrap.database import auth_session, platform_core_session

logger = get_logger(__name__)

TABLE = "usage_events"
DEFAULT = f"{TABLE}_default"
IST = ZoneInfo("Asia/Kolkata")

# Upsert target of the rollup: uq_daily_usage_dimensions, NULLS NOT DISTINCT.
DIMENSIONS = (
    "usage_date", "tenant_id", "application_id", "api_key_id",
    "tier_id", "service_id", "inference_type_id", "billing_month",
)
MEASURES = (
    "request_count", "success_count", "failed_count",
    "fallback_count", "server_error_count", "total_response_time_ms", "response_time_count",
    "total_units", "cached_input_units", "output_units",
    "input_units_cost", "cached_input_units_cost", "output_units_cost",
)
# fallback_count is JSONB: the aggregate returns its parts as integers
# (fallback_count, fallback_success, fallback_failure) and the upsert builds it.
FALLBACK_PARTS = ("fallback_success", "fallback_failure")
FALLBACK_JSON = (
    "jsonb_build_object('count', CAST(:fallback_count AS bigint),"
    " 'success', CAST(:fallback_success AS bigint), 'failure', CAST(:fallback_failure AS bigint))"
)
NAMES = (
    "tenant_name", "allocated_budget", "application_name", "tier_name",
    "service_name", "model_name", "task_type", "unit",
)


class RowCountMismatchError(RuntimeError):
    pass


def _bound(day: date) -> str:
    # IST midnight with an explicit offset, so the bound doesn't depend on the
    # session's TimeZone. IST has no DST, so every day is 24 hours.
    return f"'{day.isoformat()} 00:00:00+05:30'"


def _day_start(day: date) -> datetime:
    return datetime.combine(day, time(), tzinfo=IST)


def _day_name(day: date) -> str:
    return f"{TABLE}_{day:%Y_%m_%d}"


def _in_days(days: Iterable[date]) -> str:
    """SQL condition matching occurred_at on any of ``days``."""
    return " OR ".join(
        f"(occurred_at >= {_bound(d)} AND occurred_at < {_bound(d + timedelta(days=1))})" for d in sorted(days)
    )


def _retention_cutoff(today: date) -> date:
    """The first day kept: today and the USAGE_EVENTS_RETENTION_DAYS closed
    days before it are; every earlier day is dropped."""
    return today - timedelta(days=get_settings().USAGE_EVENTS_RETENTION_DAYS)


async def _lock(session: AsyncSession, step: str) -> bool:
    return (
        await session.execute(
            text("SELECT pg_try_advisory_xact_lock(hashtext(:key))"),
            {"key": f"pyjob:daily_usage_consolidation:{step}"},
        )
    ).scalar_one()


async def _partitions(session: AsyncSession) -> tuple[dict[date, str], list[str], bool]:
    """The partitions of usage_events: IST day partitions by day, every other
    non-DEFAULT partition (to convert), and whether there is a DEFAULT one."""
    rows = await session.execute(
        text(
            r"""
            SELECT relname, bound = 'DEFAULT' AS is_default,
                   CAST(substring(bound FROM 'FROM \(''([^'']+)''\)') AS timestamptz)
                       AT TIME ZONE 'Asia/Kolkata' AS lower_ist,
                   CAST(substring(bound FROM 'TO \(''([^'']+)''\)') AS timestamptz)
                       AT TIME ZONE 'Asia/Kolkata' AS upper_ist
            FROM (
                SELECT c.relname, pg_get_expr(c.relpartbound, c.oid) AS bound
                FROM pg_inherits i
                JOIN pg_class c ON c.oid = i.inhrelid
                WHERE i.inhparent = CAST(:table AS regclass)
            ) p
            """
        ),
        {"table": TABLE},
    )
    days: dict[date, str] = {}
    others: list[str] = []
    has_default = False
    for name, is_default, lower, upper in rows:
        if is_default:
            has_default = True
        elif (
            lower is not None
            and lower.time() == time()
            and upper == lower + timedelta(days=1)
            and name == _day_name(lower.date())
        ):
            days[lower.date()] = name
        else:
            others.append(name)
    return days, sorted(others), has_default


async def _insertable_columns(session: AsyncSession) -> str:
    """Columns of usage_events that can be written: all but total_cost, which is generated."""
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


async def _days_with_rows(session: AsyncSession, table: str) -> set[date]:
    rows = await session.execute(
        text(f'SELECT DISTINCT (occurred_at AT TIME ZONE \'Asia/Kolkata\')::date FROM "{table}"')
    )
    return set(rows.scalars())


async def _maintain_partitions(today: date) -> None:
    settings = get_settings()

    async with platform_core_session() as session:
        async with session.begin():
            if not await _lock(session, "partitions"):
                logger.warning("Partition maintenance already running, skipping | table=%s", TABLE)
                return
            await session.execute(text("SET LOCAL lock_timeout = '30s'"))
            await session.execute(text(f'LOCK TABLE "{TABLE}" IN ACCESS EXCLUSIVE MODE'))

            days, converted, has_default = await _partitions(session)

            # Detach the partitions to convert; their rows go back in below. A
            # UTC day partition has the name of the IST day partition that
            # replaces it, so each is renamed out of the way first.
            wanted = {today + timedelta(days=i) for i in range(settings.USAGE_EVENTS_DAYS_AHEAD + 1)}
            detached = []
            for i, name in enumerate(converted):
                await session.execute(text(f'ALTER TABLE "{TABLE}" DETACH PARTITION "{name}"'))
                await session.execute(text(f'ALTER TABLE "{name}" RENAME TO "ue_convert_{i}"'))
                detached.append(f"ue_convert_{i}")
                wanted |= await _days_with_rows(session, detached[-1])
            # A past day with no partition was dropped: its DEFAULT rows are
            # late ones, left there for _drop_day to add, never partitioned
            # (a partition would make them look like the whole day).
            cutoff = _retention_cutoff(today)
            if has_default:
                wanted |= {d for d in await _days_with_rows(session, DEFAULT) if d >= cutoff}
            to_create = sorted(d for d in wanted if d not in days)

            columns = await _insertable_columns(session)

            # Rows in the DEFAULT partition for a day being created must leave
            # it first, or Postgres refuses the new partition's range.
            moved = 0
            if has_default and to_create:
                await session.execute(text(f'CREATE TEMP TABLE ue_moved (LIKE "{DEFAULT}") ON COMMIT DROP'))
                result = await session.execute(
                    text(
                        f'WITH m AS (DELETE FROM "{DEFAULT}" WHERE {_in_days(to_create)} RETURNING *) '
                        f"INSERT INTO ue_moved SELECT * FROM m"
                    )
                )
                moved = result.rowcount or 0

            for day in to_create:
                await session.execute(
                    text(
                        f'CREATE TABLE "{_day_name(day)}" PARTITION OF "{TABLE}" '
                        f"FOR VALUES FROM ({_bound(day)}) TO ({_bound(day + timedelta(days=1))})"
                    )
                )

            # Restore through the parent, which routes each row to its day.
            restored = 0
            sources = (["ue_moved"] if moved else []) + detached
            for source in sources:
                expected = (await session.execute(text(f'SELECT count(*) FROM "{source}"'))).scalar_one()
                result = await session.execute(
                    text(f'INSERT INTO "{TABLE}" ({columns}) SELECT {columns} FROM "{source}"')
                )
                if (result.rowcount or 0) != expected:
                    raise RowCountMismatchError(
                        f"restored {result.rowcount} of {expected} row(s) from {source}; rolled back"
                    )
                restored += expected
            # Every row of the detached partitions is now in an IST day partition.
            for name in detached:
                await session.execute(text(f'DROP TABLE "{name}"'))

    logger.info(
        "Partition maintenance done | table=%s today=%s converted=%s created=%s "
        "default_rows_moved=%d rows_restored=%d",
        TABLE, today, converted, [_day_name(d) for d in to_create], moved, restored,
    )


_AGGREGATE = text(
    """
    WITH agg AS (
        SELECT
            tenant_id, application_id, api_key_id, tier_id, service_id, inference_type_id,
            to_char(occurred_at AT TIME ZONE 'UTC', 'YYYY-MM') AS billing_month,
            max(task_type) AS task_type,
            max(unit_of_measurement) AS unit,
            -- request rows: one per request
            count(*) FILTER (WHERE status_code IS NOT NULL AND total_units = 0)
              -- rows from before request rows existed: stand in for their
              -- request, possibly several per request
              + count(DISTINCT correlation_id) FILTER (WHERE status_code IS NOT NULL AND total_units > 0)
              AS request_count,
            count(*) FILTER (WHERE status_code >= 400 AND total_units = 0)
              + count(DISTINCT correlation_id) FILTER (WHERE status_code >= 400 AND total_units > 0)
              AS failed_count,
            -- platform-side failures (server errors, timeouts): part of failed_count
            count(*) FILTER (WHERE status_code >= 500 AND total_units = 0)
              + count(DISTINCT correlation_id) FILTER (WHERE status_code >= 500 AND total_units > 0)
              AS server_error_count,
            -- set on request rows only; pre-cutover rows carry neither
            count(*) FILTER (WHERE sent_to_fallback AND status_code IS NOT NULL AND total_units = 0)
              AS fallback_count,
            count(*) FILTER (WHERE sent_to_fallback AND status_code < 400 AND total_units = 0)
              AS fallback_success,
            count(*) FILTER (WHERE sent_to_fallback AND status_code >= 400 AND total_units = 0)
              AS fallback_failure,
            coalesce(sum(response_time_ms) FILTER (WHERE status_code IS NOT NULL AND total_units = 0), 0)
              AS total_response_time_ms,
            count(response_time_ms) FILTER (WHERE status_code IS NOT NULL AND total_units = 0)
              AS response_time_count,
            sum(total_units) AS total_units,
            sum(cached_input_units) AS cached_input_units,
            sum(output_units) AS output_units,
            sum(input_units_cost) AS input_units_cost,
            sum(cached_input_units_cost) AS cached_input_units_cost,
            sum(output_units_cost) AS output_units_cost
        FROM usage_events
        WHERE occurred_at >= :start AND occurred_at < :end
        GROUP BY tenant_id, application_id, api_key_id, tier_id, service_id, inference_type_id,
                 to_char(occurred_at AT TIME ZONE 'UTC', 'YYYY-MM')
    )
    SELECT
        agg.*,
        agg.request_count - agg.failed_count AS success_count,
        t.name AS tier_name,
        s.name AS service_name,
        m.name AS model_name
    FROM agg
    LEFT JOIN tiers t ON t.id = agg.tier_id
    LEFT JOIN mm_services s ON s.service_id = agg.service_id
    LEFT JOIN mm_models m ON m.model_id = s.model_id
    """
)

_UPSERT = text(
    f"""
    INSERT INTO daily_usage ({", ".join(DIMENSIONS + NAMES + MEASURES)})
    VALUES ({", ".join(FALLBACK_JSON if c == "fallback_count" else f":{c}" for c in DIMENSIONS + NAMES + MEASURES)})
    ON CONFLICT ({", ".join(DIMENSIONS)}) DO UPDATE SET
        {", ".join(f"{c} = EXCLUDED.{c}" for c in NAMES + MEASURES)},
        updated_at = now()
    """
)

# now() is the transaction start, which every row upserted by this
# transaction carries in updated_at; anything older wasn't written by it.
# source = 'rollup' only: the backfill's source = 'backfill' rows
# (services/pyjob/backfill) sit on days before usage_events began and must
# never be swept by the rollup.
_DELETE_STALE = text(
    "DELETE FROM daily_usage WHERE usage_date = :usage_date AND source = 'rollup' AND updated_at < now()"
)

# Late rows of a dropped day (in DEFAULT, as the day has no partition any
# more): added to what its rows already count. Names
# stay as rolled up, filled in only where the earlier row had none.
# fallback_count's parts are added one by one.
_FALLBACK_ADD = "jsonb_build_object({})".format(", ".join(
    f"'{k}', coalesce((daily_usage.fallback_count->>'{k}')::bigint, 0)"
    f" + coalesce((EXCLUDED.fallback_count->>'{k}')::bigint, 0)"
    for k in ("count", "success", "failure")
))
_UPSERT_ADD = text(
    f"""
    INSERT INTO daily_usage ({", ".join(DIMENSIONS + NAMES + MEASURES)})
    VALUES ({", ".join(FALLBACK_JSON if c == "fallback_count" else f":{c}" for c in DIMENSIONS + NAMES + MEASURES)})
    ON CONFLICT ({", ".join(DIMENSIONS)}) DO UPDATE SET
        {", ".join(f"{c} = coalesce(daily_usage.{c}, EXCLUDED.{c})" for c in NAMES)},
        {", ".join(
            f"{c} = {_FALLBACK_ADD}" if c == "fallback_count" else f"{c} = daily_usage.{c} + EXCLUDED.{c}"
            for c in MEASURES
        )},
        updated_at = now()
    """
)

_HAS_BACKFILL = text("SELECT 1 FROM daily_usage WHERE usage_date = :usage_date AND source = 'backfill' LIMIT 1")


async def _auth_names(
    tenant_ids: set[int], application_ids: set[int]
) -> tuple[dict[int, tuple[str, Any]], dict[int, str]]:
    """Tenant (name, allocated_budget) and application name by id, from the auth DB."""
    tenants: dict[int, tuple[str, Any]] = {}
    applications: dict[int, str] = {}
    if not tenant_ids and not application_ids:
        return tenants, applications
    async with auth_session() as session:
        if tenant_ids:
            rows = await session.execute(
                text("SELECT id, name, allocated_budget FROM tenants WHERE id IN :ids").bindparams(
                    bindparam("ids", expanding=True)
                ),
                {"ids": list(tenant_ids)},
            )
            tenants = {row.id: (row.name, row.allocated_budget) for row in rows}
        if application_ids:
            rows = await session.execute(
                text("SELECT id, name FROM applications WHERE id IN :ids").bindparams(
                    bindparam("ids", expanding=True)
                ),
                {"ids": list(application_ids)},
            )
            applications = {row.id: row.name for row in rows}
    return tenants, applications


async def _summarise(session: AsyncSession, day: date) -> list[dict]:
    """The day's daily_usage rows, aggregated from its usage_events rows."""
    groups = (
        await session.execute(
            _AGGREGATE, {"start": _day_start(day), "end": _day_start(day + timedelta(days=1))}
        )
    ).mappings().all()
    tenants, applications = await _auth_names(
        {g["tenant_id"] for g in groups if g["tenant_id"] is not None},
        {g["application_id"] for g in groups if g["application_id"] is not None},
    )

    rows = []
    for g in groups:
        tenant_name, allocated_budget = tenants.get(g["tenant_id"], (None, None))
        rows.append({
            **{c: g[c] for c in DIMENSIONS[1:-1] + MEASURES + FALLBACK_PARTS},
            "usage_date": day,
            "billing_month": g["billing_month"],
            "tenant_name": tenant_name,
            "allocated_budget": allocated_budget,
            "application_name": applications.get(g["application_id"]),
            "tier_name": g["tier_name"],
            "service_name": g["service_name"],
            "model_name": g["model_name"],
            "task_type": g["task_type"],
            "unit": g["unit"],
        })
    return rows


def _totals(rows: list[dict]) -> tuple[int, Any]:
    return (
        sum(r["request_count"] for r in rows),
        sum(r["input_units_cost"] + r["cached_input_units_cost"] + r["output_units_cost"] for r in rows),
    )


async def _rollup_day(day: date) -> None:
    async with platform_core_session() as session:
        async with session.begin():
            if not await _lock(session, "rollup"):
                logger.warning("Rollup already running, skipping | usage_date=%s", day)
                return

            rows = await _summarise(session, day)
            if rows:
                await session.execute(_UPSERT, rows)
            stale = (await session.execute(_DELETE_STALE, {"usage_date": day})).rowcount or 0

    requests, cost = _totals(rows)
    logger.info(
        "Rollup done | usage_date=%s rows=%d stale_rows_deleted=%d requests=%d cost=%s",
        day, len(rows), stale, requests, cost,
    )


async def _expired_days(today: date) -> tuple[dict[date, str | None], bool]:
    """Days before the retention cutoff that still have usage_events rows,
    with their day partition (None: their rows are in DEFAULT only — late
    rows of a day dropped before), and whether there is a DEFAULT partition."""
    cutoff = _retention_cutoff(today)
    async with platform_core_session() as session:
        days, _, has_default = await _partitions(session)
        expired: dict[date, str | None] = {d: name for d, name in days.items() if d < cutoff}
        if has_default:
            rows = await session.execute(
                text(
                    f"SELECT DISTINCT (occurred_at AT TIME ZONE 'Asia/Kolkata')::date FROM \"{DEFAULT}\" "
                    f"WHERE occurred_at < {_bound(cutoff)}"
                )
            )
            for day in rows.scalars():
                expired.setdefault(day, None)
    return expired, has_default


async def _drop_day(day: date, partition: str | None, has_default: bool) -> None:
    """Roll ``day`` up a last time and drop its usage_events rows, in one
    transaction (see the module docstring, step 3)."""
    async with platform_core_session() as session:
        async with session.begin():
            if not await _lock(session, "rollup"):
                logger.warning("Rollup already running, retention skipped | usage_date=%s", day)
                return
            # Taken before the day is read: a row written between the rollup
            # and the drop would be lost with the partition.
            await session.execute(text("SET LOCAL lock_timeout = '30s'"))
            await session.execute(text(f'LOCK TABLE "{TABLE}" IN ACCESS EXCLUSIVE MODE'))

            if await session.scalar(_HAS_BACKFILL, {"usage_date": day}) is not None:
                mode, rows = "backfill", []
            elif partition is None:
                # Late rows only: the day's other rows are already counted.
                mode, rows = "late_rows_added", await _summarise(session, day)
                if rows:
                    await session.execute(_UPSERT_ADD, rows)
            else:
                mode, rows = "rolled_up", await _summarise(session, day)
                # No rows left to read (none recorded): keep whatever
                # daily_usage has rather than sweep it.
                if rows:
                    await session.execute(_UPSERT, rows)
                    await session.execute(_DELETE_STALE, {"usage_date": day})

            if partition:
                await session.execute(text(f'ALTER TABLE "{TABLE}" DETACH PARTITION "{partition}"'))
                await session.execute(text(f'DROP TABLE "{partition}"'))
            default_rows = 0
            if has_default:
                result = await session.execute(text(f'DELETE FROM "{DEFAULT}" WHERE {_in_days([day])}'))
                default_rows = result.rowcount or 0

    requests, cost = _totals(rows)
    logger.info(
        "Retention dropped day | usage_date=%s mode=%s partition=%s default_rows_deleted=%d "
        "rows=%d requests=%d cost=%s",
        day, mode, partition, default_rows, len(rows), requests, cost,
    )


async def consolidate(today: date) -> None:
    failed = []
    # A partition failure must not stop the rollup: every closed day already
    # sits in a partition or in the DEFAULT partition, and the rollup only
    # reads usage_events.
    try:
        await _maintain_partitions(today)
    except Exception:
        logger.exception("Partition maintenance failed | table=%s", TABLE)
        failed.append("partitions")

    yesterday = today - timedelta(days=1)
    for back in range(get_settings().USAGE_ROLLUP_LOOKBACK_DAYS, -1, -1):
        day = yesterday - timedelta(days=back)
        try:
            await _rollup_day(day)
        except Exception:
            logger.exception("Rollup failed | usage_date=%s", day)
            failed.append(f"rollup {day}")

    # Nothing is dropped after a failure: the next run retries it first.
    if failed:
        logger.warning("Retention skipped after a failed step | table=%s failed=%s", TABLE, failed)
    else:
        try:
            expired, has_default = await _expired_days(today)
        except Exception:
            logger.exception("Retention failed | table=%s", TABLE)
            failed.append("retention")
            expired, has_default = {}, False
        for day, partition in sorted(expired.items()):
            try:
                await _drop_day(day, partition, has_default)
            except Exception:
                logger.exception("Retention failed | usage_date=%s", day)
                failed.append(f"retention {day}")
    if failed:
        raise RuntimeError(f"Daily usage consolidation failed for: {', '.join(failed)}")


async def run() -> None:
    logger.info("Starting daily usage consolidation")
    await consolidate(datetime.now(IST).date())
