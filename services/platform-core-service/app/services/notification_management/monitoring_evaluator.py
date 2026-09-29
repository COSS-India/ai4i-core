"""Monitoring alerts evaluator: ERROR_RATE_4XX, ERROR_RATE_5XX, LATENCY_P50,
LATENCY_P95, LATENCY_P99.

A timer tick runs on every platform-core pod; only the pod that wins the
evaluator lock (SET NX PX, never released — it expires before the next tick)
evaluates. The leader keeps the alerts that have active bands and a selected
recipient role, runs their PromQL queries concurrently against Prometheus, and
hands every (alert, service) value to the shared BAND pipeline in one batch
(ai4i_core.kafka.emit_band_batch): one ledger read, claims only for FIRE and
RESET, one Redis pipeline for all changes.

A service missing from a result (no traffic, or under the minimum request
count) causes no change: missing data never counts as recovery.
"""

import asyncio
import logging
import math
import time
import uuid
from decimal import Decimal
from typing import Dict, List
from zoneinfo import ZoneInfo

import httpx
from prometheus_client import Gauge, Histogram

from ai4i_core.kafka import (
    BandItem,
    FailureCode,
    FailureStage,
    FireContext,
    Measurement,
    NotificationName,
    Operation,
    Producer,
    ThresholdUnit,
    emit_band_batch,
    get_notification_runtime,
    monitoring_subject,
    notifications_configured,
    producer_scope,
)
from ai4i_core.kafka import constants as ntf

from app.core.config import settings

logger = logging.getLogger(__name__)

#: K5 — held by the pod that runs the current tick.
MONITOR_EVAL_LOCK_KEY = f"{ntf.REDIS_KEY_PREFIX}lock:monitor-eval"
#: The lock expires this long before the next tick, so the next tick is free
#: (55 s for the default 60 s interval).
MONITOR_EVAL_LOCK_MARGIN_MS = 5000
MONITOR_EVAL_LOCK_MIN_TTL_MS = 1000


def lock_ttl_ms(interval_s: int) -> int:
    return max(interval_s * 1000 - MONITOR_EVAL_LOCK_MARGIN_MS, MONITOR_EVAL_LOCK_MIN_TTL_MS)
#: At most this long for the whole tick; each Prometheus call gets QUERY_TIMEOUT_S.
TICK_BUDGET_S = 45
QUERY_TIMEOUT_S = 10
#: SOURCE failures are throttled to one row per alert per this window.
SOURCE_FAILURE_THROTTLE_S = 300
PROMETHEUS_QUERY_PATH = "/api/v1/query"
SERVICE_LABEL = "service_id"
IST = ZoneInfo("Asia/Kolkata")

MONITOR_TICK_SECONDS = Histogram(
    "ntf_monitor_tick_seconds", "Duration of one monitoring evaluator tick on the leader."
)
MONITOR_LEADER = Gauge(
    "ntf_monitor_leader", "1 while this process holds the monitoring evaluator lock for the current tick."
)

_REQUESTS = "telemetry_obsv_requests_total"
_DURATION_BUCKETS = "telemetry_obsv_request_duration_seconds_bucket"


def _min_requests_filter(window: str, min_requests: int) -> str:
    return (
        f'sum by ({SERVICE_LABEL}) (increase({_REQUESTS}{{{SERVICE_LABEL}!=""}}[{window}])) >= {min_requests}'
    )


def _error_rate_query(status_regex: str, window: str, min_requests: int) -> str:
    return (
        f"(\n  100 * sum by ({SERVICE_LABEL}) (rate({_REQUESTS}{{{SERVICE_LABEL}!=\"\", status_code=~\"{status_regex}\"}}[{window}]))\n"
        f"      / sum by ({SERVICE_LABEL}) (rate({_REQUESTS}{{{SERVICE_LABEL}!=\"\"}}[{window}]))\n)\n"
        f"and on ({SERVICE_LABEL})\n({_min_requests_filter(window, min_requests)})"
    )


def _latency_query(quantile: str, window: str, min_requests: int) -> str:
    return (
        f"histogram_quantile({quantile},\n"
        f"  sum by (le, {SERVICE_LABEL}) (rate({_DURATION_BUCKETS}{{{SERVICE_LABEL}!=\"\"}}[{window}]))\n)\n"
        f"and on ({SERVICE_LABEL})\n({_min_requests_filter(window, min_requests)})"
    )


def build_queries(window: str, min_requests: int) -> Dict[NotificationName, tuple]:
    """PromQL and unit per monitoring alert."""
    return {
        NotificationName.ERROR_RATE_4XX: (_error_rate_query("4..", window, min_requests), ThresholdUnit.PERCENT),
        NotificationName.ERROR_RATE_5XX: (_error_rate_query("5..", window, min_requests), ThresholdUnit.PERCENT),
        NotificationName.LATENCY_P50: (_latency_query("0.50", window, min_requests), ThresholdUnit.SECONDS),
        NotificationName.LATENCY_P95: (_latency_query("0.95", window, min_requests), ThresholdUnit.SECONDS),
        NotificationName.LATENCY_P99: (_latency_query("0.99", window, min_requests), ThresholdUnit.SECONDS),
    }


#: The LLD's name of each alert's PromQL, stored on SOURCE failure rows.
PROMQL_NAMES = {
    NotificationName.ERROR_RATE_4XX: "E-4XX",
    NotificationName.ERROR_RATE_5XX: "E-5XX",
    NotificationName.LATENCY_P50: "L-0.50",
    NotificationName.LATENCY_P95: "L-0.95",
    NotificationName.LATENCY_P99: "L-0.99",
}


def _bare(value) -> str:
    """A display number without unit: the template appends % or s."""
    text = f"{float(value):.2f}".rstrip("0").rstrip(".")
    return text or "0"


def _details(context: FireContext) -> List[str]:
    """The consumer's monitoring template contract, same shape as the usage
    alerts: [threshold, alert_datetime_ist, current_value]. The service id
    and severity travel in the envelope's subject and severity."""
    return [
        _bare(context.band.value),
        context.occurred_at.astimezone(IST).strftime("%d %b %Y, %I:%M %p IST"),
        _bare(context.observed.value),
    ]


class _SourceError(Exception):
    def __init__(self, code: FailureCode, message: str):
        super().__init__(message)
        self.code = code


async def _query(client: httpx.AsyncClient, promql: str) -> Dict[str, float]:
    """{service_id: value} of one instant query."""
    try:
        response = await client.get(
            settings.prometheus_url.rstrip("/") + PROMETHEUS_QUERY_PATH,
            params={"query": promql},
            timeout=QUERY_TIMEOUT_S,
        )
    except httpx.TimeoutException as exc:
        raise _SourceError(FailureCode.PROMETHEUS_TIMEOUT, str(exc) or "timeout") from exc
    except httpx.HTTPError as exc:
        raise _SourceError(FailureCode.PROMETHEUS_UNREACHABLE, str(exc)) from exc
    try:
        response.raise_for_status()
        body = response.json()
        if body.get("status") != "success":
            raise ValueError(f"status {body.get('status')!r}")
        values: Dict[str, float] = {}
        for sample in body["data"]["result"]:
            service_id = sample["metric"].get(SERVICE_LABEL)
            value = float(sample["value"][1])
            if service_id and math.isfinite(value):
                values[service_id] = value
        return values
    except Exception as exc:
        raise _SourceError(FailureCode.PROMETHEUS_BAD_RESPONSE, str(exc)) from exc


async def _try_lock(redis) -> bool:
    token = f"{get_notification_runtime().origin}:{uuid.uuid4()}"
    return bool(
        await redis.set(MONITOR_EVAL_LOCK_KEY, token, nx=True, px=lock_ttl_ms(settings.monitoring_eval_interval_s))
    )


async def run_tick(client: httpx.AsyncClient) -> List[uuid.UUID]:
    """One leader tick. Returns the event ids handed to Kafka."""
    rt = get_notification_runtime()
    read = await rt.cache.read(context_name=NotificationName.ERROR_RATE_5XX)
    if read.settings is None:
        await rt.failures.record(
            FailureStage.SETTINGS, FailureCode.SETTINGS_UNAVAILABLE, notification_name=NotificationName.ERROR_RATE_5XX,
            operation=Operation.SETTINGS_FILL, error=read.settings_error,
        )
        return []
    queries = build_queries(settings.monitoring_window, settings.monitoring_min_requests)
    wanted = []
    for name, (promql, unit) in queries.items():
        row = read.settings.get(name)
        if row is not None and row.bands and row.any_role_enabled():
            wanted.append((name, promql, unit))
    if not wanted:
        return []

    results = await asyncio.gather(*(_query(client, promql) for _, promql, _ in wanted), return_exceptions=True)
    items: List[BandItem] = []
    for (name, _, unit), result in zip(wanted, results):
        if isinstance(result, BaseException):
            code = result.code if isinstance(result, _SourceError) else FailureCode.PROMETHEUS_BAD_RESPONSE
            await rt.failures.record(
                FailureStage.SOURCE, code, notification_name=name, operation=Operation.PROMETHEUS_QUERY,
                error=result, message=f"{PROMQL_NAMES[name]}: {result}", throttle_s=SOURCE_FAILURE_THROTTLE_S,
            )
            continue
        for service_id, value in result.items():
            items.append(
                BandItem(
                    name=name,
                    tenant_id=ntf.PLATFORM_TENANT_ID,
                    subject=monitoring_subject(service_id),
                    observed=Measurement(value=_decimal(value), unit=unit),
                    details=_details,
                )
            )
    if not items:
        return []
    # Shielded: once claims start, the tick budget must not cancel the batch
    # between a won claim and its publish.
    return await asyncio.shield(emit_band_batch(items))


def _decimal(value: float) -> Decimal:
    return Decimal(str(round(value, 4)))


async def run_forever() -> None:
    """Background loop started in the app lifespan."""
    if not settings.prometheus_url:
        logger.info("Monitoring evaluator disabled: PROMETHEUS_URL is not set.")
        return
    interval = settings.monitoring_eval_interval_s
    async with httpx.AsyncClient() as client:
        while True:
            started = time.monotonic()
            try:
                if notifications_configured():
                    rt = get_notification_runtime()
                    if await _try_lock(rt.redis):
                        MONITOR_LEADER.set(1)
                        with MONITOR_TICK_SECONDS.time(), producer_scope(Producer.MONITORING_EVALUATOR):
                            await asyncio.wait_for(run_tick(client), timeout=TICK_BUDGET_S)
                    else:
                        MONITOR_LEADER.set(0)
            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError:
                logger.warning("Monitoring evaluator tick exceeded %ss", TICK_BUDGET_S)
            except Exception:
                logger.exception("Monitoring evaluator tick failed")
            await asyncio.sleep(max(0.0, interval - (time.monotonic() - started)))
