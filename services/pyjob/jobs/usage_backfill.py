"""One-off backfill of the Usage Dashboard's history from Prometheus.

usage_events only has data from the day its writer shipped; before that the
dashboard read Prometheus, which keeps a limited number of days (15 by
default) and drops the oldest every day. This job keeps what Prometheus still
has, as estimated daily_usage rows (source = 'backfill'), for the days before
usage_events begins. Run it once per environment:

    USAGE_BACKFILL_MODE=export   Prometheus → USAGE_BACKFILL_FILE. Run this
                                 first: what it saves no longer depends on
                                 Prometheus' retention. Keep the file.
    USAGE_BACKFILL_MODE=load     USAGE_BACKFILL_FILE → daily_usage. Needs
                                 migration f6c8e0a2b4d7 (daily_usage.source).
    USAGE_BACKFILL_MODE=all      both, in one run (the default)

Export
------
From USAGE_BACKFILL_FROM (default: the first whole IST day Prometheus
retains) up to USAGE_BACKFILL_UNTIL (default: the first usage_events row), one
window per IST day; the last one ends at the cut-off, so nothing is counted
by both. A window also ends at a UTC month start, so every window has a
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

Load
----
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
backfill rows of the exported days are deleted and the new ones inserted, so
a re-run with the same file converges, and days a later export no longer
covers keep their rows. usage_backfill records the span covered (its first
day, kept from earlier loads, up to the file's cut-off), which tells the Usage
Dashboard which figures are estimates. Refuses to load when usage_events has rows before the
file's cut-off, which would count those days twice.
"""
from __future__ import annotations

import json
import math
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import httpx
from ai4i_core.logging import get_logger
from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

from bootstrap.config import get_settings
from bootstrap.database import auth_session, platform_core_session
from jobs.monthly_partition_rollover import _create_months, _partitions

logger = get_logger(__name__)

IST = ZoneInfo("Asia/Kolkata")
FILE_VERSION = 1
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


_DURATION_PART = re.compile(r"(\d+)(ms|s|m|h|d|w|y)")
_DURATION_SECONDS = {"ms": 0.001, "s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800, "y": 31536000}


def retention_seconds(storage_retention: Optional[str]) -> Optional[float]:
    """Seconds of a runtimeinfo storageRetention ("15d", "1w2d", "15d or
    10GiB"); None when it has no time part (size-only, or unset)."""
    for part in (storage_retention or "").split(" or "):
        part = part.replace(" ", "")
        matches = _DURATION_PART.findall(part)
        if matches and "".join(n + u for n, u in matches) == part:
            return sum(int(n) * _DURATION_SECONDS[u] for n, u in matches)
    return None


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

    async def storage_retention(self) -> Optional[str]:
        try:
            return (await self._get("/api/v1/status/runtimeinfo")).get("storageRetention")
        except (httpx.HTTPError, BackfillError, KeyError) as exc:
            logger.warning("Prometheus retention unavailable: %s", exc)
            return None


async def _first_usage_event() -> Optional[datetime]:
    async with platform_core_session() as session:
        return (await session.execute(text("SELECT min(occurred_at) FROM usage_events"))).scalar_one()


async def export(prometheus: Prometheus, first_day: Optional[date], until: Optional[datetime]) -> dict:
    """The export document: every window's samples, as JSON-ready values."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    if until is None:
        until = await _first_usage_event() or now
    until = min(until, now)
    if first_day is None:
        retained = retention_seconds(await prometheus.storage_retention())
        if retained is None:
            raise BackfillError(
                "Prometheus reports no time retention; set USAGE_BACKFILL_FROM to its first whole day"
            )
        # The day the retention edge falls on is partly gone: start the day after.
        first_day = (now - timedelta(seconds=retained)).astimezone(IST).date() + timedelta(days=1)

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
            "Exported window | usage_date=%s start=%s end=%s series=%d",
            window.usage_date, window.start.isoformat(), window.end.isoformat(), count,
        )
    return {
        "version": FILE_VERSION,
        "exported_at": now.isoformat(),
        "prometheus_url": settings.PROMETHEUS_URL,
        "path_label": path_label,
        "first_day": first_day.isoformat(),
        "until": until.isoformat(),
        "days": sorted({w.usage_date.isoformat() for w in spans}),
        "samples": samples,
    }


def write_export(document: dict, path: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".partial")
    partial.write_text(json.dumps(document, indent=1), encoding="utf-8")
    os.replace(partial, target)
    logger.info(
        "Export written | file=%s days=%d samples=%d until=%s",
        target, len(document["days"]), len(document["samples"]), document["until"],
    )


def read_export(path: str) -> dict:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if document.get("version") != FILE_VERSION:
        raise BackfillError(f"{path}: unsupported export version {document.get('version')!r}")
    return document


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
    """daily_usage rows (source 'backfill') from export samples, and counts
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


# Days an earlier load covered keep their rows, so the span starts at the
# earliest of them.
_COVERAGE = text(
    "INSERT INTO usage_backfill (id, first_day, until, loaded_at) VALUES (1, :first_day, :until, now())"
    " ON CONFLICT (id) DO UPDATE SET first_day = LEAST(usage_backfill.first_day, EXCLUDED.first_day),"
    " until = EXCLUDED.until, loaded_at = now()"
)


async def load(document: dict) -> None:
    days = [date.fromisoformat(d) for d in document["days"]]
    until = datetime.fromisoformat(document["until"])
    if not days:
        logger.info("Nothing to load: the export covers no days")
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
                    f"usage_events has rows from {first_event.isoformat()}, before the export's cut-off"
                    f" {until.isoformat()}: those would be counted twice. Export again without"
                    " USAGE_BACKFILL_UNTIL, or with it at or before the first usage_events row."
                )

            lookups = await _lookups(session, document["samples"])
            rows, skipped = build_rows(document["samples"], lookups)

            # Past months need their partitions (the migration and the
            # rollover job only create current and future ones).
            await session.execute(text("SET LOCAL lock_timeout = '30s'"))
            await session.execute(text("LOCK TABLE daily_usage IN ACCESS EXCLUSIVE MODE"))
            existing, default = await _partitions(session)
            months = sorted({d.replace(day=1) for d in days} - set(existing))
            moved = await _create_months(session, default, months)

            deleted = (
                await session.execute(
                    _in("DELETE FROM daily_usage WHERE source = :source AND usage_date IN :days", "days"),
                    {"source": SOURCE, "days": days},
                )
            ).rowcount or 0
            if rows:
                await session.execute(_INSERT, rows)
            await session.execute(_COVERAGE, {"first_day": days[0], "until": until})

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
    mode = settings.USAGE_BACKFILL_MODE
    logger.info("Starting usage backfill | mode=%s file=%s", mode, settings.USAGE_BACKFILL_FILE)

    if mode in ("export", "all"):
        if not settings.PROMETHEUS_URL:
            raise BackfillError("PROMETHEUS_URL must be set to export")
        until = settings.USAGE_BACKFILL_UNTIL
        if until is not None and until.tzinfo is None:
            until = until.replace(tzinfo=IST)
        async with httpx.AsyncClient(timeout=settings.PROMETHEUS_TIMEOUT_SECONDS) as client:
            document = await export(Prometheus(client, settings.PROMETHEUS_URL), settings.USAGE_BACKFILL_FROM, until)
        write_export(document, settings.USAGE_BACKFILL_FILE)
    else:
        document = read_export(settings.USAGE_BACKFILL_FILE)

    if mode in ("load", "all"):
        await load(document)
