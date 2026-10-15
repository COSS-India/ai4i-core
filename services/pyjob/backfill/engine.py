"""One-off backfill of the Usage Dashboard's LLM history from Prometheus.

usage_events only has data from the day its writer shipped; before that the
dashboard read Prometheus. This job copies Prometheus' daily LLM totals for
the days BACKFILL_FROM .. BACKFILL_TO (IST, both inclusive) into daily_usage,
as estimated rows (source = 'backfill'):

    cd services/pyjob
    PROMETHEUS_URL=... BACKFILL_FROM=2026-10-01 BACKFILL_TO=2026-10-07 python -m backfill
    python -m backfill undo        # remove the backfilled rows

The flow:

    1. Check the dates, and that usage_events has no rows before the end of
       BACKFILL_TO (those days would be counted twice).
    2. Create the daily_usage month partitions the dates need.
    3. Load once into memory the few details the rows need: institutions,
       applications, single-key applications, tiers, LLM services and their
       prices, the LLM inference type.
    4. For each day:
         a. ask Prometheus for the day's LLM requests, successful requests and
            prompt / completion tokens, per institution, application and service
            (the same queries the Prometheus-backed dashboard used, release-2.8);
         b. build one row per institution, application and service, with cost =
            tokens x the service's price (today's price);
         c. write the day's rows (replacing that day's earlier backfill rows).

The rows are estimates: Prometheus' daily counter growth, today's prices, the
institution's current tier, and an API key only when the application has just
one (Prometheus can't tell an application's keys apart).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional
from zoneinfo import ZoneInfo

import httpx
from ai4i_core.logging import get_logger
from sqlalchemy import text

from backfill.config import get_settings
from bootstrap.database import auth_session, platform_core_session
from jobs.monthly_partition_rollover import _create_months, _partitions

logger = get_logger(__name__)

IST = ZoneInfo("Asia/Kolkata")
SOURCE = "backfill"
DAY_SECONDS = 86_400

# The Prometheus-backed dashboard's selectors (release-2.8 metering_service /
# metering_promql_builder): real institutions, API-key traffic only (auth_type
# is absent on older series, so it's matched as "api_key or empty"), and for
# requests the LLM chat paths only.
REQUESTS_METRIC = "telemetry_obsv_requests_total"
LLM_TOKENS_METRIC = "telemetry_obsv_llm_tokens_processed_sum"
LLM_CHAT_PATHS = r"/api/v1/chat(/completions)?"
BASE_SELECTORS = 'tenant!="unknown",auth_type=~"api_key|"'
# One row per institution, application and service.
GROUP_BY = "tenant_id, application_id, service_id"


class BackfillError(RuntimeError):
    pass


# ── Prometheus ─────────────────────────────────────────────────────────────


def sum_over_day(metric: str, group_by: str) -> str:
    """A counter's growth over the day before the evaluation time, summed by
    ``group_by``: release-2.8's sum_over_window_by. Series that started during
    the day count their raw value (increase() would extrapolate them), the
    rest their increase()."""
    window = f"{DAY_SECONDS}s"
    return f"sum by({group_by}) (({metric} unless {metric} offset {window}) or (increase({metric}[{window}]) > 0))"


def day_queries(path_label: str) -> dict[str, str]:
    """The day's queries, evaluated at the day's end (the next IST midnight)."""
    requests = f'{REQUESTS_METRIC}{{{BASE_SELECTORS},{path_label}=~"{LLM_CHAT_PATHS}"}}'
    successful = f'{REQUESTS_METRIC}{{{BASE_SELECTORS},{path_label}=~"{LLM_CHAT_PATHS}",status_code=~"2.."}}'
    tokens = f'{LLM_TOKENS_METRIC}{{{BASE_SELECTORS},token_type=~"prompt|completion"}}'
    return {
        "requests": sum_over_day(requests, GROUP_BY),
        "successful": sum_over_day(successful, GROUP_BY),
        "tokens": sum_over_day(tokens, f"{GROUP_BY}, token_type"),
    }


async def query(client: httpx.AsyncClient, base_url: str, promql: str, at: datetime) -> list[dict]:
    """An instant query evaluated at ``at``: the result vector."""
    response = await client.get(f"{base_url}/api/v1/query", params={"query": promql, "time": at.timestamp()})
    response.raise_for_status()
    body = response.json()
    if body.get("status") != "success":
        raise BackfillError(f"Prometheus query failed: {body.get('error') or body}")
    return body["data"]["result"]


# ── What the rows need, loaded once ────────────────────────────────────────


@dataclass
class LlmService:
    name: str
    model_name: Optional[str]
    input_rate: Decimal    # ₹ per input token
    output_rate: Decimal   # ₹ per output token


@dataclass
class Lookups:
    tenants: dict[int, tuple]            # tenant id → (name, allocated_budget, tier_id)
    applications: dict[int, str]         # application id → name
    single_keys: dict[int, int]          # application id → its only API key
    tiers: dict[str, str]                # tier id → name
    services: dict[str, LlmService]      # service id → name, model, prices (LLM services)
    llm_type_id: Optional[int]           # inference_types id of "llm"
    llm_unit: Optional[str]


def token_rates(unit_rate, cost_per_unit, unit_size, output_cost_per_unit) -> tuple[Decimal, Decimal]:
    """(₹ per input token, ₹ per output token), as the PPU consumer prices LLM
    usage (payperuse_consumer/_billing.py calculate_llm_cost): the input
    price is unit_rate, else cost_per_unit / unit_size; the output price is
    output_cost_per_unit / unit_size, else the input price."""
    input_rate = Decimal(0)
    if unit_rate:
        input_rate = Decimal(str(unit_rate))
    elif cost_per_unit and unit_size:
        input_rate = Decimal(str(cost_per_unit)) / int(unit_size)
    output_rate = input_rate
    if output_cost_per_unit is not None and unit_size:
        output_rate = Decimal(str(output_cost_per_unit)) / int(unit_size)
    return input_rate, output_rate


async def load_lookups() -> Lookups:
    async with auth_session() as auth:
        tenants = {
            r.id: (r.name, r.allocated_budget, str(r.tier_id) if r.tier_id else None)
            for r in await auth.execute(text("SELECT id, name, allocated_budget, tier_id FROM tenants"))
        }
        applications = {r.id: r.name for r in await auth.execute(text("SELECT id, name FROM applications"))}
        # Every key an application ever had, revoked ones too: with more than
        # one, Prometheus can't tell which one made a call.
        single_keys = {
            r.application_id: r.key_id
            for r in await auth.execute(text(
                "SELECT application_id, min(id) AS key_id FROM api_key"
                " WHERE application_id IS NOT NULL GROUP BY application_id HAVING count(*) = 1"
            ))
        }
    async with platform_core_session() as core:
        tiers = {str(r.id): r.name for r in await core.execute(text("SELECT id, name FROM tiers"))}
        # Soft-deleted services too: their last price is their current one.
        services = {
            r.service_id: LlmService(
                r.name, r.model_name,
                *token_rates(r.unit_rate, r.cost_per_unit, r.unit_size, r.output_cost_per_unit),
            )
            for r in await core.execute(text(
                "SELECT s.service_id, s.name, m.name AS model_name, s.unit_rate, s.cost_per_unit,"
                " s.unit_size, s.output_cost_per_unit"
                " FROM mm_services s LEFT JOIN mm_models m ON m.model_id = s.model_id"
                " WHERE lower(s.task_type) = 'llm'"
            ))
        }
        llm = (await core.execute(text("SELECT id, unit FROM inference_types WHERE name = 'llm'"))).first()
    return Lookups(tenants, applications, single_keys, tiers, services,
                   llm.id if llm else None, llm.unit if llm else None)


# ── One day ────────────────────────────────────────────────────────────────


def _label_int(value: Optional[str]) -> Optional[int]:
    return int(value) if value and value.isdigit() and int(value) > 0 else None


def _whole(value: Decimal) -> Decimal:
    return value.quantize(Decimal(1), ROUND_HALF_UP)


def build_day_rows(day: date, results: dict[str, list[dict]], lookups: Lookups) -> list[dict]:
    """The day's daily_usage rows from its query results: one per institution,
    application and service. Series without a numeric tenant_id are skipped."""
    totals: dict[tuple, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
    for kind, series in results.items():
        for s in series:
            labels = s["metric"]
            tenant_id = _label_int(labels.get("tenant_id"))
            if tenant_id is None:
                continue
            key = (tenant_id, _label_int(labels.get("application_id")), labels.get("service_id") or None)
            name = labels.get("token_type") if kind == "tokens" else kind   # prompt / completion
            totals[key][name] += Decimal(str(s["value"][1]))

    rows = []
    for (tenant_id, application_id, service_id), t in totals.items():
        requests = int(_whole(t["requests"]))
        failed = max(0, requests - int(_whole(t["successful"])))
        prompt, completion = _whole(t["prompt"]), _whole(t["completion"])
        if requests == 0 and prompt + completion == 0:
            continue
        tenant_name, allocated_budget, tier_id = lookups.tenants.get(tenant_id, (None, None, None))
        if application_id not in lookups.applications:
            application_id = None
        service = lookups.services.get(service_id)
        if service is None:
            service_id = None     # not an LLM service in mm_services: no name, no price
        rows.append({
            "usage_date": day,
            "billing_month": f"{day:%Y-%m}",
            "tenant_id": tenant_id,
            "tenant_name": tenant_name,
            "allocated_budget": allocated_budget,
            "application_id": application_id,
            "application_name": lookups.applications.get(application_id),
            "api_key_id": lookups.single_keys.get(application_id),
            "tier_id": tier_id if tier_id in lookups.tiers else None,
            "tier_name": lookups.tiers.get(tier_id),
            "service_id": service_id,
            "service_name": service.name if service else None,
            "model_name": service.model_name if service else None,
            "inference_type_id": lookups.llm_type_id,
            "task_type": "llm",
            "unit": lookups.llm_unit,
            "request_count": requests,
            "success_count": requests - failed,
            "failed_count": failed,
            "total_units": prompt + completion,
            "cached_input_units": Decimal(0),
            "output_units": completion,
            "input_units_cost": prompt * service.input_rate if service else Decimal(0),
            "cached_input_units_cost": Decimal(0),
            "output_units_cost": completion * service.output_rate if service else Decimal(0),
        })
    return rows


_COLUMNS = (
    "usage_date", "billing_month", "tenant_id", "tenant_name", "allocated_budget",
    "application_id", "application_name", "api_key_id", "tier_id", "tier_name",
    "service_id", "service_name", "model_name", "inference_type_id", "task_type", "unit",
    "request_count", "success_count", "failed_count",
    "total_units", "cached_input_units", "output_units",
    "input_units_cost", "cached_input_units_cost", "output_units_cost",
)
# source is a native enum: SOURCE is a fixed constant, written as a literal.
_INSERT = text(
    f"INSERT INTO daily_usage ({', '.join(_COLUMNS)}, source)"
    f" VALUES ({', '.join(':' + c for c in _COLUMNS)}, '{SOURCE}')"
)
_DELETE_DAY = text(f"DELETE FROM daily_usage WHERE source = '{SOURCE}' AND usage_date = :day")
_LOCK = text("SELECT pg_try_advisory_xact_lock(hashtext('pyjob:usage_backfill'))")


async def write_day(day: date, rows: list[dict]) -> None:
    """Replace the day's backfill rows with ``rows``, in one transaction."""
    async with platform_core_session() as session:
        async with session.begin():
            if not (await session.execute(_LOCK)).scalar_one():
                raise BackfillError("another usage backfill (or undo) is running")
            await session.execute(_DELETE_DAY, {"day": day})
            if rows:
                await session.execute(_INSERT, rows)


# ── Before the loop ────────────────────────────────────────────────────────


def _ist_midnight(day: date) -> datetime:
    return datetime.combine(day, time(), tzinfo=IST)


async def check_no_recorded_usage_before(end: datetime) -> None:
    """Refuse when usage_events has rows before ``end``: those days already
    have recorded usage, which the dashboard reads too."""
    async with platform_core_session() as session:
        found = await session.scalar(
            text("SELECT occurred_at FROM usage_events WHERE occurred_at < :end LIMIT 1"), {"end": end},
        )
    if found is not None:
        raise BackfillError(
            f"usage_events has rows before {end.isoformat()} (e.g. {found.isoformat()}): set BACKFILL_TO"
            " to a day before usage_events begins, or those days would be counted twice."
        )


async def create_partitions(first: date, last: date) -> None:
    """daily_usage is partitioned by month; the migration and the monthly job
    only create current and future months. Create the past ones the days need."""
    days = [first + timedelta(days=n) for n in range((last - first).days + 1)]
    months = sorted({date(d.year, d.month, 1) for d in days})
    async with platform_core_session() as session:
        async with session.begin():
            existing, default = await _partitions(session)
            missing = [m for m in months if m not in existing]
            if missing:
                await session.execute(text("SET LOCAL lock_timeout = '30s'"))
                await session.execute(text("LOCK TABLE daily_usage IN ACCESS EXCLUSIVE MODE"))
                await _create_months(session, default, missing)
                logger.info("Created daily_usage partitions | months=%s", [f"{m:%Y-%m}" for m in missing])


# ── Entry point ────────────────────────────────────────────────────────────


async def run() -> None:
    settings = get_settings()
    first, last = settings.BACKFILL_FROM, settings.BACKFILL_TO
    if not settings.PROMETHEUS_URL or first is None or last is None:
        raise BackfillError("PROMETHEUS_URL, BACKFILL_FROM and BACKFILL_TO must be set")
    if first > last:
        raise BackfillError(f"BACKFILL_FROM ({first}) is after BACKFILL_TO ({last})")
    if last >= datetime.now(IST).date():
        raise BackfillError(f"BACKFILL_TO ({last}) must be a past day")

    await check_no_recorded_usage_before(_ist_midnight(last + timedelta(days=1)))
    await create_partitions(first, last)
    lookups = await load_lookups()
    logger.info(
        "Starting usage backfill | days=%s..%s tenants=%d applications=%d llm_services=%d",
        first, last, len(lookups.tenants), len(lookups.applications), len(lookups.services),
    )

    queries = day_queries(settings.PROMETHEUS_API_PATH_LABEL)
    base_url = settings.PROMETHEUS_URL.rstrip("/")
    async with httpx.AsyncClient(timeout=settings.PROMETHEUS_TIMEOUT_SECONDS) as client:
        day = first
        while day <= last:
            day_end = _ist_midnight(day + timedelta(days=1))
            results = {kind: await query(client, base_url, promql, day_end) for kind, promql in queries.items()}
            rows = build_day_rows(day, results, lookups)
            await write_day(day, rows)
            logger.info(
                "Backfilled | day=%s rows=%d requests=%d tokens=%s cost=%s",
                day, len(rows), sum(r["request_count"] for r in rows),
                sum((r["total_units"] for r in rows), Decimal(0)),
                sum((r["input_units_cost"] + r["output_units_cost"] for r in rows), Decimal(0)),
            )
            day += timedelta(days=1)
