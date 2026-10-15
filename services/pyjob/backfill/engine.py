"""One-off backfill of the Usage Dashboard's history from Prometheus.

usage_events only has data from the day its writer shipped; before that the
dashboard read Prometheus, which keeps a limited number of days (15 by
default) and drops the oldest every day. This job keeps what Prometheus still
has, as estimated daily_usage rows (source = 'backfill'), for the days before
usage_events begins. It is a one-off, run by hand (not a scheduled job), once
per environment, after the migration that adds daily_usage.source:

    cd services/pyjob
    PROMETHEUS_URL=... python -m backfill          # read Prometheus → daily_usage
    python -m backfill undo                        # remove the backfilled rows

It reads Prometheus, then loads daily_usage, in one run.

Reading Prometheus
------------------
From the first whole IST day after Prometheus' oldest sample (or
USAGE_BACKFILL_FROM, which may not be earlier) up to the cut-over: the IST
midnight of the day the first usage_events row falls on (or
USAGE_BACKFILL_UNTIL). One window per IST day. The cut-over day itself is
left entirely to the rollup, so no usage_date ever holds both a backfill and
a rollup row — which is why source need not be in daily_usage's unique key.

The oldest sample is looked up, not derived from the configured retention:
size-based eviction or compaction can leave Prometheus holding less than it
says. A day whose start Prometheus no longer has would book every series'
lifetime counter as that day's growth (an established series looks born in
the window), a large overcount — so the first day must start after the
oldest sample (oldest_sample, first_whole_day). A window also ends at a UTC month start, so every window has a
single billing_month (the UTC month, as the PPU consumer bills it). For each
window, API-key traffic only (auth_type "api_key", or absent on older series,
as the Prometheus-backed dashboard counted it):

    requests  telemetry_obsv_requests_total on inference paths,
              by tenant_id, application_id, service_id, path, status_code
    llm       telemetry_obsv_llm_tokens_processed_sum, prompt and completion,
              by tenant_id, application_id, service_id, token_type
    units     each other task type's native-unit _sum metric (characters,
              audio minutes, images), by tenant_id, application_id, service_id

Each value is the dashboard's own estimate of a counter's growth over a
window: increase(), plus the raw counter for series born inside it.

Loading daily_usage
-------------------
One daily_usage row per IST day and dimension key, written with source =
'backfill':

    tenant, application   the series' labels; names and the tenant's
                          allocated budget from the auth DB
    tier                  the tenant's current tier (Prometheus has none)
    API key               the application's key when it has exactly one,
                          else NULL (Prometheus has none)
    service, model        mm_services / mm_models
    inference type        the service's task type, else the request path's
    requests, failed      rounded; failed = status 400 or above
    LLM                   input = prompt tokens, output = completion tokens,
                          no cached input (not recorded before 2026-10-09)
    other task types      units in input
    cost                  at each service's current price, priced exactly as
                          the PPU consumer bills (_price_llm / _price below)

Units without a price are left out, as the consumer bills nothing for them
and writes no usage row. A row's labels that no longer match a service, tier
or tenant are dropped to NULL (or the row skipped, without a tenant).

In one transaction: the past-month partitions the rows need are created, the
backfill rows of the days read are deleted and the new ones inserted, so a
re-run converges, and days Prometheus no longer has keep their rows. Refuses
to load when usage_events has rows before the cut-over, which would count
those days twice.

Backfilled days are not flagged in the dashboard: no platform-core or
simple-ui change ships here, so these rows display alongside recorded ones,
unmarked. To take it all back out, run ``python -m backfill undo``: it
deletes the source = 'backfill' rows and nothing else. Running it again
afterwards reads Prometheus again, which may no longer hold the oldest days.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional
from zoneinfo import ZoneInfo

import httpx
from ai4i_core.logging import get_logger
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from backfill.config import get_settings
from bootstrap.database import auth_session, platform_core_session
from jobs.monthly_partition_rollover import _create_months, _partitions

logger = get_logger(__name__)

IST = ZoneInfo("Asia/Kolkata")
SOURCE = "backfill"

# Same as platform-core's metering_promql_builder: the requests the
# Prometheus-backed dashboard counted.
_REQUESTS_METRIC = "telemetry_obsv_requests_total"
_INFERENCE_PATHS = r"(.*/inference|/api/v1/chat(/completions)?)"
_CHAT_PATHS = {"/api/v1/chat", "/api/v1/chat/completions"}
_LLM_METRIC = "telemetry_obsv_llm_tokens_processed_sum"
# Native-unit metrics of the other task types (SERVICE_BREAKDOWN_CONFIG), by
# inference_types catalogue name.
_UNIT_METRICS = {
    "nmt": "telemetry_obsv_nmt_characters_translated_sum",
    "asr": "telemetry_obsv_asr_audio_minutes_processed_sum",
    "tts": "telemetry_obsv_tts_characters_synthesized_sum",
    "ocr": "telemetry_obsv_ocr_images_processed_sum",
    "transliteration": "telemetry_obsv_transliteration_characters_processed_sum",
    "ner": "telemetry_obsv_ner_tokens_processed_sum",
    "language-detection": "telemetry_obsv_language_detection_characters_processed_sum",
    "speaker-diarization": "telemetry_obsv_speaker_diarization_minutes_processed_sum",
    "language-diarization": "telemetry_obsv_language_diarization_minutes_processed_sum",
    "audio-lang-detection": "telemetry_obsv_audio_lang_detection_minutes_processed_sum",
}
# Billed in fractional minutes; every other unit is a whole count.
_MINUTE_TASKS = {"asr", "speaker-diarization", "language-diarization", "audio-lang-detection"}
_COMMON_SELECTORS = 'tenant!="unknown",auth_type=~"api_key|"'

_WHOLE = Decimal(1)
_MINUTE_STEP = Decimal("0.0001")


class BackfillError(RuntimeError):
    pass


# ── Windows ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Window:
    usage_date: date
    start: datetime
    end: datetime

    @property
    def seconds(self) -> int:
        return int((self.end - self.start).total_seconds())

    @property
    def billing_month(self) -> str:
        return f"{self.start.astimezone(timezone.utc):%Y-%m}"


def _ist_midnight(day: date) -> datetime:
    return datetime.combine(day, time(), tzinfo=IST)


def windows(first_day: date, until: datetime) -> list[Window]:
    """[IST midnight, next IST midnight) per day from ``first_day``, the last
    one cut at ``until``, each split at a UTC month start inside it."""
    result = []
    day = first_day
    while _ist_midnight(day) < until:
        start, end = _ist_midnight(day), min(_ist_midnight(day + timedelta(days=1)), until)
        utc_end = end.astimezone(timezone.utc)
        month_start = datetime(utc_end.year, utc_end.month, 1, tzinfo=timezone.utc)
        if start < month_start < end:
            result.append(Window(day, start, month_start))
            result.append(Window(day, month_start, end))
        else:
            result.append(Window(day, start, end))
        day += timedelta(days=1)
    return result


# ── Prometheus ─────────────────────────────────────────────────────────────


# Look the oldest sample up this far back, at most.
_OLDEST_SAMPLE_MAX_HOURS = 400 * 24
# A day's first window needs every established series' sample just before
# its start (the instant lookback is 5 minutes): start this long after the
# hour the oldest sample falls in.
_OLDEST_SAMPLE_MARGIN = timedelta(minutes=10)


async def oldest_sample(prometheus: "Prometheus", now: datetime) -> Optional[datetime]:
    """Prometheus' oldest request-counter sample (within
    _OLDEST_SAMPLE_MAX_HOURS), None when it has none. A single range query over
    the span, taking the first point it returns. Not an hour-by-hour probe: an
    environment on a standard schedule (powered off nights and weekends) has
    empty hours, so a probe landing in a gap would be read as "before the
    oldest" and silently skip earlier days Prometheus still holds."""
    start = now - timedelta(hours=_OLDEST_SAMPLE_MAX_HOURS)
    firsts = [
        float(series["values"][0][0])
        for series in await prometheus.query_range(f"count({_REQUESTS_METRIC})", start, now, "1h")
        if series.get("values")
    ]
    return datetime.fromtimestamp(min(firsts), tz=timezone.utc) if firsts else None


def first_whole_day(oldest: datetime) -> date:
    """The first IST day whose start has samples before it: the day after
    the one oldest (plus the lookback margin) falls on."""
    return (oldest + _OLDEST_SAMPLE_MARGIN).astimezone(IST).date() + timedelta(days=1)


def _hybrid(selector: str, seconds: int) -> str:
    """A counter's growth over the ``seconds`` before the evaluation time,
    as platform-core's sum_over_window: the raw value for series born in the
    window (increase() would extrapolate them), increase() for the rest."""
    return f"({selector} unless {selector} offset {seconds}s) or (increase({selector}[{seconds}s]) > 0)"


def queries(path_label: str, seconds: int) -> list[tuple[str, Optional[str], str]]:
    """(kind, task, PromQL) for one window of ``seconds``, evaluated at its end."""
    requests = f'{_REQUESTS_METRIC}{{{_COMMON_SELECTORS},{path_label}=~"{_INFERENCE_PATHS}"}}'
    llm = f'{_LLM_METRIC}{{{_COMMON_SELECTORS},token_type=~"prompt|completion"}}'
    result = [
        ("requests", None,
         f"sum by (tenant_id, application_id, service_id, {path_label}, status_code) ({_hybrid(requests, seconds)})"),
        ("llm", "llm",
         f"sum by (tenant_id, application_id, service_id, token_type) ({_hybrid(llm, seconds)})"),
    ]
    for task, metric in _UNIT_METRICS.items():
        selector = f"{metric}{{{_COMMON_SELECTORS}}}"
        result.append(
            ("units", task, f"sum by (tenant_id, application_id, service_id) ({_hybrid(selector, seconds)})")
        )
    return result


class Prometheus:
    def __init__(self, client: httpx.AsyncClient, base_url: str) -> None:
        self._client = client
        self._base = base_url.rstrip("/")

    async def _get(self, path: str, params: Optional[dict] = None) -> Any:
        response = await self._client.get(f"{self._base}{path}", params=params)
        response.raise_for_status()
        body = response.json()
        if body.get("status") != "success":
            raise BackfillError(f"Prometheus {path} failed: {body.get('error') or body}")
        return body["data"]

    async def query(self, promql: str, at: datetime) -> list[dict]:
        data = await self._get("/api/v1/query", {"query": promql, "time": at.timestamp()})
        return data.get("result", [])

    async def query_range(self, promql: str, start: datetime, end: datetime, step: str) -> list[dict]:
        data = await self._get(
            "/api/v1/query_range",
            {"query": promql, "start": start.timestamp(), "end": end.timestamp(), "step": step},
        )
        return data.get("result", [])


async def _first_usage_event() -> Optional[datetime]:
    async with platform_core_session() as session:
        return (await session.execute(text("SELECT min(occurred_at) FROM usage_events"))).scalar_one()


@dataclass(frozen=True)
class Collected:
    """What Prometheus had for the days to backfill."""
    first_day: date
    until: datetime          # where usage_events takes over
    days: list[date]
    samples: list[dict]      # {usage_date, billing_month, kind, task, labels, value}


async def collect(prometheus: Prometheus, first_day: Optional[date], until: Optional[datetime]) -> Collected:
    """Every window's samples, from first_day (default: the first whole day
    after Prometheus' oldest sample, and never earlier) up to until (default:
    the first usage_events row)."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    if until is None:
        # Default cut-over: the IST midnight of the day the first usage_events
        # row falls on — or today's IST midnight when usage_events is still
        # empty (see the clamp below), so the cut-over day is always left to
        # the rollup.
        first_event = await _first_usage_event()
        until = _ist_midnight(first_event.astimezone(IST).date()) if first_event else now
    until = min(until, now)
    # Every path — the empty-usage_events default (now), a future or mid-day
    # USAGE_BACKFILL_UNTIL — must end on an IST midnight. A partial final day
    # would give that day a backfill window; since source is not in the unique
    # key, the nightly rollup would later overwrite the row with recorded
    # figures while it stayed labelled 'backfill', and a subsequent undo would
    # then wipe real recorded usage. Round down to the IST day start.
    clamped = _ist_midnight(until.astimezone(IST).date())
    if clamped != until:
        logger.warning(
            "Cut-off %s is not an IST midnight; rounding down to %s so the cut-over day is left to the rollup",
            until.isoformat(), clamped.isoformat(),
        )
    until = clamped
    oldest = await oldest_sample(prometheus, now)
    if oldest is None:
        logger.warning("Prometheus has no %s samples: nothing to backfill", _REQUESTS_METRIC)
        return Collected(first_day or until.astimezone(IST).date(), until, [], [])
    earliest = first_whole_day(oldest)
    logger.info("Prometheus' oldest sample | hour_ending=%s first_whole_day=%s", oldest.isoformat(), earliest)
    if first_day is None:
        first_day = earliest
    elif first_day < earliest:
        raise BackfillError(
            f"USAGE_BACKFILL_FROM={first_day} is before {earliest}, the first whole day after Prometheus'"
            f" oldest sample ({oldest.isoformat()}): that day's start isn't in Prometheus any more, so"
            " every series would count its lifetime total as that day's usage. Leave it unset, or set it"
            f" to {earliest} or later."
        )

    path_label = settings.PROMETHEUS_API_PATH_LABEL
    samples = []
    spans = windows(first_day, until)
    for window in spans:
        count = 0
        for kind, task, promql in queries(path_label, window.seconds):
            for series in await prometheus.query(promql, window.end):
                value = float(series["value"][1])
                if not math.isfinite(value) or value <= 0:
                    continue
                labels = dict(series.get("metric", {}))
                if kind == "requests":
                    labels["path"] = labels.pop(path_label, "")
                samples.append({
                    "usage_date": window.usage_date.isoformat(),
                    "billing_month": window.billing_month,
                    "kind": kind,
                    "task": task,
                    "labels": labels,
                    "value": value,
                })
                count += 1
        logger.info(
            "Read window | usage_date=%s start=%s end=%s series=%d",
            window.usage_date, window.start.isoformat(), window.end.isoformat(), count,
        )
    return Collected(first_day, until, sorted({w.usage_date for w in spans}), samples)


# ── Pricing: the PPU consumer's (payperuse_consumer/_billing.py) ──────────


@dataclass(frozen=True)
class Pricing:
    task_type: str
    unit_rate: Optional[Decimal]
    cost_per_unit: Optional[Decimal]
    unit_size: Optional[int]
    cached_input_cost_per_unit: Optional[Decimal] = None
    output_cost_per_unit: Optional[Decimal] = None


def _per_unit_rate(price: Optional[Decimal], pricing: Pricing) -> Optional[Decimal]:
    if price is None or not pricing.unit_size:
        return None
    return price / pricing.unit_size


def _price_llm(input_tokens: Decimal, output_tokens: Decimal, pricing: Pricing) -> tuple[Decimal, Decimal]:
    """(input cost, output cost): calculate_llm_cost with no cached input."""
    input_rate = pricing.unit_rate or _per_unit_rate(pricing.cost_per_unit, pricing) or Decimal(0)
    output_rate = _per_unit_rate(pricing.output_cost_per_unit, pricing)
    return input_tokens * input_rate, output_tokens * (input_rate if output_rate is None else output_rate)


def _price(units: Decimal, pricing: Pricing) -> Decimal:
    """calculate_cost."""
    if pricing.unit_rate:
        return units * pricing.unit_rate
    if pricing.cost_per_unit and pricing.unit_size:
        return (units / pricing.unit_size) * pricing.cost_per_unit
    return Decimal(0)


# ── Rows ───────────────────────────────────────────────────────────────────


@dataclass
class Service:
    name: Optional[str]
    model_name: Optional[str]
    pricing: Pricing


@dataclass
class Lookups:
    tenants: dict[int, tuple[Optional[str], Any, Optional[str]]]   # id → (name, allocated_budget, tier_id)
    applications: dict[int, Optional[str]]                         # id → name
    single_keys: dict[int, int]                                    # application id → its only API key
    services: dict[str, Service]
    inference_types: dict[str, tuple[int, Optional[str]]]          # type_key(name) → (id, unit)
    tiers: dict[str, Optional[str]]                                # id → name


def _int_label(value: Optional[str]) -> Optional[int]:
    return int(value) if value and value.isdigit() and int(value) > 0 else None


def type_key(name: Optional[str]) -> Optional[str]:
    """A task type name as the inference_types catalogue spells it
    (lowercase, hyphenated), so "speaker_diarization" finds "speaker-diarization"."""
    return name.lower().replace("_", "-") if name else None


def path_task(path: str) -> Optional[str]:
    """The task type of an inference path: /api/v1/<task>/inference, or llm for chat."""
    if path in _CHAT_PATHS:
        return "llm"
    match = re.fullmatch(r"/api/v1/(.+)/inference", path or "")
    return type_key(match.group(1)) if match else None


@dataclass
class _Acc:
    requests: float = 0.0
    failed: float = 0.0
    total_units: Decimal = field(default_factory=Decimal)
    output_units: Decimal = field(default_factory=Decimal)
    input_units_cost: Decimal = field(default_factory=Decimal)
    output_units_cost: Decimal = field(default_factory=Decimal)
    task_type: Optional[str] = None


def build_rows(samples: list[dict], lookups: Lookups) -> tuple[list[dict], dict[str, int]]:
    """daily_usage rows (source 'backfill') from Prometheus samples (see collect), and counts
    of what was left out, by reason."""
    skipped: dict[str, int] = defaultdict(int)
    acc: dict[tuple, _Acc] = defaultdict(_Acc)
    # LLM tokens per row key, priced once summed; the key's service sets the price.
    llm: dict[tuple, dict[str, Decimal]] = defaultdict(lambda: {"prompt": Decimal(0), "completion": Decimal(0)})

    def key_for(sample: dict, task: Optional[str]) -> Optional[tuple[tuple, Optional[Service], Optional[str]]]:
        labels = sample["labels"]
        tenant_id = _int_label(labels.get("tenant_id"))
        if tenant_id is None or tenant_id not in lookups.tenants:
            skipped[f"{sample['kind']}: unknown tenant"] += 1
            return None
        application_id = _int_label(labels.get("application_id"))
        if application_id is not None and application_id not in lookups.applications:
            application_id = None
        service_id = labels.get("service_id") or None
        service = lookups.services.get(service_id) if service_id else None
        if service is None:
            service_id = None
        task_type = type_key(service.pricing.task_type if service else None) or type_key(task)
        inference_type = lookups.inference_types.get(task_type) if task_type else None
        tier_id = lookups.tenants[tenant_id][2]
        if tier_id not in lookups.tiers:
            tier_id = None
        key = (
            date.fromisoformat(sample["usage_date"]), tenant_id, application_id,
            lookups.single_keys.get(application_id) if application_id is not None else None,
            tier_id, service_id, inference_type[0] if inference_type else None, sample["billing_month"],
        )
        return key, service, task_type

    for sample in samples:
        kind, value = sample["kind"], float(sample["value"])
        if kind == "requests":
            found = key_for(sample, path_task(sample["labels"].get("path", "")))
            if found is None:
                continue
            key, _, task_type = found
            row = acc[key]
            row.task_type = row.task_type or task_type
            row.requests += value
            status = sample["labels"].get("status_code", "")
            if status.isdigit() and int(status) >= 400:
                row.failed += value
        elif kind == "llm":
            found = key_for(sample, "llm")
            if found is None:
                continue
            key, _, task_type = found
            token_type = sample["labels"].get("token_type")
            if token_type in ("prompt", "completion"):
                llm[key][token_type] += Decimal(str(value))
                acc[key].task_type = acc[key].task_type or task_type
        elif kind == "units":
            found = key_for(sample, sample["task"])
            if found is None:
                continue
            key, service, task_type = found
            step = _MINUTE_STEP if sample["task"] in _MINUTE_TASKS else _WHOLE
            units = Decimal(str(value)).quantize(step, ROUND_HALF_UP)
            cost = _price(units, service.pricing) if service else Decimal(0)
            if units <= 0 or cost <= 0:
                skipped["units: no price" if units > 0 else "units: rounds to 0"] += 1
                continue
            row = acc[key]
            row.task_type = row.task_type or task_type
            row.total_units += units
            row.input_units_cost += cost

    for key, tokens in llm.items():
        service = lookups.services.get(key[5]) if key[5] else None
        prompt = tokens["prompt"].quantize(_WHOLE, ROUND_HALF_UP)
        completion = tokens["completion"].quantize(_WHOLE, ROUND_HALF_UP)
        input_cost, output_cost = (
            _price_llm(prompt, completion, service.pricing) if service else (Decimal(0), Decimal(0))
        )
        if prompt + completion <= 0 or input_cost + output_cost <= 0:
            skipped["llm: no price" if prompt + completion > 0 else "llm: rounds to 0"] += 1
            continue
        row = acc[key]
        row.total_units += prompt + completion
        row.output_units += completion
        row.input_units_cost += input_cost
        row.output_units_cost += output_cost

    units_by_type = {type_id: unit for type_id, unit in lookups.inference_types.values()}
    rows = []
    for key, row in acc.items():
        usage_date, tenant_id, application_id, api_key_id, tier_id, service_id, type_id, billing_month = key
        requests = int(Decimal(str(row.requests)).quantize(_WHOLE, ROUND_HALF_UP))
        failed = min(int(Decimal(str(row.failed)).quantize(_WHOLE, ROUND_HALF_UP)), requests)
        if requests == 0 and row.total_units == 0:
            continue
        tenant_name, allocated_budget, _ = lookups.tenants[tenant_id]
        service = lookups.services.get(service_id) if service_id else None
        rows.append({
            "usage_date": usage_date,
            "tenant_id": tenant_id,
            "application_id": application_id,
            "api_key_id": api_key_id,
            "tier_id": tier_id,
            "service_id": service_id,
            "inference_type_id": type_id,
            "billing_month": billing_month,
            "tenant_name": tenant_name,
            "allocated_budget": allocated_budget,
            "application_name": lookups.applications.get(application_id) if application_id else None,
            "tier_name": lookups.tiers.get(tier_id) if tier_id else None,
            "service_name": service.name if service else None,
            "model_name": service.model_name if service else None,
            "task_type": row.task_type,
            "unit": units_by_type.get(type_id),
            "request_count": requests,
            "success_count": requests - failed,
            "failed_count": failed,
            "total_units": row.total_units,
            "cached_input_units": Decimal(0),
            "output_units": row.output_units,
            "input_units_cost": row.input_units_cost,
            "cached_input_units_cost": Decimal(0),
            "output_units_cost": row.output_units_cost,
        })
    rows.sort(key=lambda r: (r["usage_date"], r["tenant_id"], str(r["service_id"])))
    return rows, dict(skipped)


# ── Load ───────────────────────────────────────────────────────────────────


def _ids(samples: list[dict], label: str) -> set[int]:
    return {i for s in samples if (i := _int_label(s["labels"].get(label))) is not None}


def _in(sql: str, name: str = "ids"):
    return text(sql).bindparams(bindparam(name, expanding=True))


async def _lookups(core: AsyncSession, samples: list[dict]) -> Lookups:
    tenant_ids, application_ids = _ids(samples, "tenant_id"), _ids(samples, "application_id")
    service_ids = {s["labels"]["service_id"] for s in samples if s["labels"].get("service_id")}

    tenants: dict = {}
    applications: dict = {}
    single_keys: dict = {}
    async with auth_session() as auth:
        if tenant_ids:
            rows = await auth.execute(
                _in("SELECT id, name, allocated_budget, tier_id FROM tenants WHERE id IN :ids"),
                {"ids": list(tenant_ids)},
            )
            tenants = {r.id: (r.name, r.allocated_budget, str(r.tier_id) if r.tier_id else None) for r in rows}
        if application_ids:
            rows = await auth.execute(
                _in("SELECT id, name FROM applications WHERE id IN :ids"), {"ids": list(application_ids)}
            )
            applications = {r.id: r.name for r in rows}
            # Every key the application ever had, revoked ones too: with more
            # than one, Prometheus can't tell which made a call.
            rows = await auth.execute(
                _in(
                    "SELECT application_id, min(id) AS id, count(*) AS n FROM api_key"
                    " WHERE application_id IN :ids GROUP BY application_id"
                ),
                {"ids": list(application_ids)},
            )
            single_keys = {r.application_id: r.id for r in rows if r.n == 1}

    services: dict = {}
    if service_ids:
        # Soft-deleted services too: their last price is their current one.
        rows = await core.execute(
            _in(
                "SELECT s.service_id, s.name, m.name AS model_name, s.task_type, s.unit_rate,"
                " s.cost_per_unit, s.unit_size, s.cached_input_cost_per_unit, s.output_cost_per_unit"
                " FROM mm_services s LEFT JOIN mm_models m ON m.model_id = s.model_id"
                " WHERE s.service_id IN :ids"
            ),
            {"ids": list(service_ids)},
        )

        def dec(value) -> Optional[Decimal]:
            return None if value is None or value == "" else Decimal(str(value))

        services = {
            r.service_id: Service(
                r.name, r.model_name,
                Pricing(
                    task_type=r.task_type or "", unit_rate=dec(r.unit_rate), cost_per_unit=dec(r.cost_per_unit),
                    unit_size=int(r.unit_size) if r.unit_size else None,
                    cached_input_cost_per_unit=dec(r.cached_input_cost_per_unit),
                    output_cost_per_unit=dec(r.output_cost_per_unit),
                ),
            )
            for r in rows
        }
    inference_types = {
        type_key(r.name): (r.id, r.unit)
        for r in await core.execute(text("SELECT id, name, unit FROM inference_types"))
    }
    tiers = {str(r.id): r.name for r in await core.execute(text("SELECT id, name FROM tiers"))}
    return Lookups(tenants, applications, single_keys, services, inference_types, tiers)


_COLUMNS = (
    "usage_date", "tenant_id", "application_id", "api_key_id", "tier_id", "service_id",
    "inference_type_id", "billing_month", "tenant_name", "allocated_budget", "application_name",
    "tier_name", "service_name", "model_name", "task_type", "unit",
    "request_count", "success_count", "failed_count",
    "total_units", "cached_input_units", "output_units",
    "input_units_cost", "cached_input_units_cost", "output_units_cost",
)
_INSERT = text(
    f"INSERT INTO daily_usage ({', '.join(_COLUMNS)}, source)"
    f" VALUES ({', '.join(':' + c for c in _COLUMNS)}, '{SOURCE}')"
)


async def load(collected: Collected) -> None:
    days, until = collected.days, collected.until
    if not days:
        logger.info("Nothing to load: no days before usage_events begins in Prometheus' retention")
        return

    async with platform_core_session() as session:
        async with session.begin():
            locked = (
                await session.execute(
                    text("SELECT pg_try_advisory_xact_lock(hashtext('pyjob:usage_backfill'))")
                )
            ).scalar_one()
            if not locked:
                raise BackfillError("another usage_backfill load is running")

            first_event = (
                await session.execute(text("SELECT min(occurred_at) FROM usage_events"))
            ).scalar_one()
            if first_event is not None and first_event < until:
                raise BackfillError(
                    f"usage_events has rows from {first_event.isoformat()}, before the cut-off"
                    f" {until.isoformat()}: those would be counted twice. Run again without"
                    " USAGE_BACKFILL_UNTIL, or with it at or before the first usage_events row."
                )

            lookups = await _lookups(session, collected.samples)
            rows, skipped = build_rows(collected.samples, lookups)

            # Past months need their partitions (the migration and the
            # rollover job only create current and future ones).
            await session.execute(text("SET LOCAL lock_timeout = '30s'"))
            await session.execute(text("LOCK TABLE daily_usage IN ACCESS EXCLUSIVE MODE"))
            existing, default = await _partitions(session)
            months = sorted({d.replace(day=1) for d in days} - set(existing))
            moved = await _create_months(session, default, months)

            # source is a native enum; compare to the literal (SOURCE is a
            # fixed constant, not user input) so there's no text-vs-enum bind.
            deleted = (
                await session.execute(
                    _in(f"DELETE FROM daily_usage WHERE source = '{SOURCE}' AND usage_date IN :days", "days"),
                    {"days": days},
                )
            ).rowcount or 0
            if rows:
                await session.execute(_INSERT, rows)

    by_day: dict[date, list[dict]] = defaultdict(list)
    for row in rows:
        by_day[row["usage_date"]].append(row)
    for day in days:
        day_rows = by_day.get(day, [])
        logger.info(
            "Backfilled | usage_date=%s rows=%d requests=%d units=%s cost=%s",
            day, len(day_rows), sum(r["request_count"] for r in day_rows),
            sum((r["total_units"] for r in day_rows), Decimal(0)),
            sum((r["input_units_cost"] + r["output_units_cost"] for r in day_rows), Decimal(0)),
        )
    logger.info(
        "Backfill loaded | days=%s..%s rows=%d replaced=%d partitions_created=%s default_rows_moved=%d skipped=%s",
        days[0], days[-1], len(rows), deleted, [f"{m:%Y-%m}" for m in months], moved, skipped or "none",
    )


# ── Entry point ────────────────────────────────────────────────────────────


async def run() -> None:
    settings = get_settings()
    if not settings.PROMETHEUS_URL:
        raise BackfillError("PROMETHEUS_URL must be set")
    until = settings.USAGE_BACKFILL_UNTIL
    if until is not None and until.tzinfo is None:
        until = until.replace(tzinfo=IST)
    logger.info("Starting usage backfill | prometheus=%s", settings.PROMETHEUS_URL)
    async with httpx.AsyncClient(timeout=settings.PROMETHEUS_TIMEOUT_SECONDS) as client:
        collected = await collect(Prometheus(client, settings.PROMETHEUS_URL), settings.USAGE_BACKFILL_FROM, until)
    await load(collected)
