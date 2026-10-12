"""Daily partitions for usage_events and the daily_usage rollup.

Run by k8s every day at 00:00 UTC. Days are UTC days: usage_events is
partitioned on occurred_at, and daily_usage.usage_date is the UTC day of it
(see the create_usage_events_table and create_daily_usage_table migrations).

1. Partitions of usage_events, in one transaction:

   - Month partitions (usage_events_YYYY_MM, as the migration creates them)
     are detached, and their rows are moved into day partitions
     (usage_events_YYYY_MM_DD). This only does work on the first run after
     the migration; later runs find no month partitions.
   - Day partitions are created for today and the next USAGE_EVENTS_DAYS_AHEAD
     days, and for every earlier day that has rows to restore. Rows the
     DEFAULT partition holds for a day being created are moved into it first,
     since Postgres refuses the new range otherwise.
   - Past day partitions are never dropped.

   The parent is locked ACCESS EXCLUSIVE for the transaction, so writers wait
   instead of sending rows to the DEFAULT partition mid-conversion. The
   conversion rewrites every row once; later runs only create empty
   partitions, which is quick.

2. Rollup of yesterday and the USAGE_ROLLUP_LOOKBACK_DAYS before it into
   daily_usage, one transaction per day, so events that arrive late are
   picked up. Each day is aggregated per dimension key and upserted; rows of
   that day the run did not write (a combination that no longer exists) are
   deleted. Names come from tiers, mm_services and mm_models here and from
   tenants and applications in the auth DB. Requests are counted once per
   correlation id; rows without a status_code add units and cost but are not
   counted, and a request is failed if any of its rows has status >= 400.

Re-running is safe: both steps converge to the same state. A
transaction-level advisory lock per step makes an overlapping run skip the
step instead of racing.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from ai4i_core.logging import get_logger
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from bootstrap.config import get_settings
from bootstrap.database import auth_session, platform_core_session

logger = get_logger(__name__)

TABLE = "usage_events"
DEFAULT = f"{TABLE}_default"
_MONTH_RE = re.compile(rf"^{TABLE}_(\d{{4}})_(\d{{2}})$")
_DAY_RE = re.compile(rf"^{TABLE}_(\d{{4}})_(\d{{2}})_(\d{{2}})$")

# Upsert target of the rollup: uq_daily_usage_dimensions, NULLS NOT DISTINCT.
DIMENSIONS = (
    "usage_date", "tenant_id", "application_id", "api_key_id",
    "tier_id", "service_id", "inference_type_id", "billing_month",
)
MEASURES = (
    "request_count", "success_count", "failed_count",
    "total_units", "cached_input_units", "output_units",
    "input_units_cost", "cached_input_units_cost", "output_units_cost",
)
NAMES = (
    "tenant_name", "allocated_budget", "application_name", "tier_name",
    "service_name", "model_name", "task_type", "unit",
)


class RowCountMismatchError(RuntimeError):
    pass


def _bound(day: date) -> str:
    # Explicit +00 offset, as in the migration, so the bound doesn't depend on
    # the session's TimeZone.
    return f"'{day.isoformat()} 00:00:00+00'"


def _day_start(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=timezone.utc)


def _day_name(day: date) -> str:
    return f"{TABLE}_{day:%Y_%m_%d}"


def _in_days(days: Iterable[date]) -> str:
    """SQL condition matching occurred_at on any of ``days``."""
    return " OR ".join(
        f"(occurred_at >= {_bound(d)} AND occurred_at < {_bound(d + timedelta(days=1))})" for d in sorted(days)
    )


async def _lock(session: AsyncSession, step: str) -> bool:
    return (
        await session.execute(
            text("SELECT pg_try_advisory_xact_lock(hashtext(:key))"),
            {"key": f"pyjob:daily_usage_consolidation:{step}"},
        )
    ).scalar_one()


async def _partitions(session: AsyncSession) -> list[str]:
    """Names of the partitions of usage_events, DEFAULT included."""
    rows = await session.execute(
        text(
            """
            SELECT c.relname
            FROM pg_inherits i
            JOIN pg_class c ON c.oid = i.inhrelid
            WHERE i.inhparent = CAST(:table AS regclass)
            """
        ),
        {"table": TABLE},
    )
    return list(rows.scalars())


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
        text(f'SELECT DISTINCT (occurred_at AT TIME ZONE \'UTC\')::date FROM "{table}"')
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

            partitions = await _partitions(session)
            months = sorted(name for name in partitions if _MONTH_RE.match(name))
            days = {
                date(int(m[1]), int(m[2]), int(m[3])): name
                for name in partitions
                if (m := _DAY_RE.match(name))
            }
            has_default = DEFAULT in partitions

            # Detach the month partitions; their retained rows go back in below.
            wanted = {today + timedelta(days=i) for i in range(settings.USAGE_EVENTS_DAYS_AHEAD + 1)}
            for name in months:
                await session.execute(text(f'ALTER TABLE "{TABLE}" DETACH PARTITION "{name}"'))
                wanted |= await _days_with_rows(session, name)
            if has_default:
                wanted |= await _days_with_rows(session, DEFAULT)
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
            sources = (["ue_moved"] if moved else []) + months
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
            # Every row of the detached month partitions is now in a day partition.
            for name in months:
                await session.execute(text(f'DROP TABLE "{name}"'))

    logger.info(
        "Partition maintenance done | table=%s today=%s converted=%s created=%s "
        "default_rows_moved=%d rows_restored=%d",
        TABLE, today, months, [_day_name(d) for d in to_create], moved, restored,
    )


_AGGREGATE = text(
    """
    WITH agg AS (
        SELECT
            tenant_id, application_id, api_key_id, tier_id, service_id, inference_type_id,
            max(task_type) AS task_type,
            max(unit_of_measurement) AS unit,
            count(DISTINCT correlation_id) FILTER (WHERE status_code IS NOT NULL) AS request_count,
            count(DISTINCT correlation_id) FILTER (WHERE status_code >= 400) AS failed_count,
            sum(total_units) AS total_units,
            sum(cached_input_units) AS cached_input_units,
            sum(output_units) AS output_units,
            sum(input_units_cost) AS input_units_cost,
            sum(cached_input_units_cost) AS cached_input_units_cost,
            sum(output_units_cost) AS output_units_cost
        FROM usage_events
        WHERE occurred_at >= :start AND occurred_at < :end
        GROUP BY tenant_id, application_id, api_key_id, tier_id, service_id, inference_type_id
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
    VALUES ({", ".join(f":{c}" for c in DIMENSIONS + NAMES + MEASURES)})
    ON CONFLICT ({", ".join(DIMENSIONS)}) DO UPDATE SET
        {", ".join(f"{c} = EXCLUDED.{c}" for c in NAMES + MEASURES)},
        updated_at = now()
    """
)

# now() is the transaction start, which every row upserted by this
# transaction carries in updated_at; anything older wasn't written by it.
_DELETE_STALE = text("DELETE FROM daily_usage WHERE usage_date = :usage_date AND updated_at < now()")


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


async def _rollup_day(day: date) -> None:
    async with platform_core_session() as session:
        async with session.begin():
            if not await _lock(session, "rollup"):
                logger.warning("Rollup already running, skipping | usage_date=%s", day)
                return

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
                    **{c: g[c] for c in DIMENSIONS[1:-1] + MEASURES},
                    "usage_date": day,
                    "billing_month": f"{day:%Y-%m}",
                    "tenant_name": tenant_name,
                    "allocated_budget": allocated_budget,
                    "application_name": applications.get(g["application_id"]),
                    "tier_name": g["tier_name"],
                    "service_name": g["service_name"],
                    "model_name": g["model_name"],
                    "task_type": g["task_type"],
                    "unit": g["unit"],
                })
            if rows:
                await session.execute(_UPSERT, rows)
            stale = (await session.execute(_DELETE_STALE, {"usage_date": day})).rowcount or 0

    logger.info(
        "Rollup done | usage_date=%s rows=%d stale_rows_deleted=%d requests=%d cost=%s",
        day, len(rows), stale,
        sum(r["request_count"] for r in rows),
        sum(r["input_units_cost"] + r["cached_input_units_cost"] + r["output_units_cost"] for r in rows),
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
    if failed:
        raise RuntimeError(f"Daily usage consolidation failed for: {', '.join(failed)}")


async def run() -> None:
    logger.info("Starting daily usage consolidation")
    await consolidate(datetime.now(timezone.utc).date())
