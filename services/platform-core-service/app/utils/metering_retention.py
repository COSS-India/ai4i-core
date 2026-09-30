"""How much history the metering Prometheus actually retains.

One value for every retention-aware metering query: the custom-range clamp
(metering_promql_builder.retention_edge), the vs-previous-period guard, the
first-usage lookback and model_usage_growth_pct's 60-day guard. It comes from
Prometheus itself (``/api/v1/status/runtimeinfo`` → ``storageRetention``),
because PROMETHEUS_RETENTION_DAYS can sit below or above the real retention:
below, ranges with real usage read zero; above, a pruned start sample makes
the windowed PromQL count lifetime counters. The setting is only the
fallback when Prometheus doesn't report a time retention (a Thanos/Mimir
proxy without the endpoint, a size-only retention, or an error).

That's the configured maximum, though, not the data Prometheus actually
holds: after a fresh start, or a redeploy without its volume, the oldest
sample is younger than the retention allows. So the oldest sample
(``prometheus_tsdb_lowest_timestamp_seconds``, self-scraped) is read too, and
data_floor() exposes it; metering_promql_builder.retention_edge() takes the
later of the two. Without that metric, the floor is simply skipped.

Cached per process: refresh_retention() is awaited by the metering routes on
a cache miss, and the query builders read retention_days() / data_floor()
synchronously.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Optional, Protocol

from app.core.config import settings

logger = logging.getLogger(__name__)

# How long a result is trusted before refresh_retention() asks again: a
# success rarely changes; a failure is retried sooner, but not on every
# request to a Prometheus that simply doesn't report it.
_SUCCESS_TTL_SECONDS = 3600
_FAILURE_TTL_SECONDS = 300
# The oldest sample jumps forward on a restart without the volume, and the
# lookup is one cheap instant query, so it's re-read every minute (the
# overview cache TTL) whether the last read worked or not.
_FLOOR_TTL_SECONDS = 60

_UNIT_DAYS: dict[str, float] = {
    "y": 365, "w": 7, "d": 1, "h": 1 / 24, "m": 1 / 1440, "s": 1 / 86_400, "ms": 1 / 86_400_000,
}
_TERM = re.compile(r"(\d+)(ms|y|w|d|h|m|s)")

_discovered_days: Optional[float] = None
_fetched_at: Optional[float] = None
_last_ok = False

_floor_ts: Optional[float] = None
_floor_fetched_at: Optional[float] = None


class _RetentionSource(Protocol):
    async def storage_retention(self) -> Optional[str]: ...

    async def lowest_sample_timestamp(self) -> Optional[float]: ...


def parse_storage_retention(value: Optional[str]) -> Optional[float]:
    """Days of time-based retention in Prometheus's ``storageRetention``
    string, or None when it has none.

    The time part is a Prometheus duration: one or more ``<n><unit>`` terms
    (``90d``, ``1y2w``, ``12h``). When a size limit is also set, Prometheus
    reports ``"30d or 512MiB"``; only the part before " or " is read. A
    size-only value ("512MiB") or anything unparseable gives None.
    """
    if not value:
        return None
    time_part = value.split(" or ")[0].strip()
    if not time_part or _TERM.sub("", time_part):
        return None
    days = sum(int(n) * _UNIT_DAYS[unit] for n, unit in _TERM.findall(time_part))
    return float(days) if days > 0 else None


def retention_days() -> float:
    """The retention every metering query uses: what Prometheus last
    reported, else PROMETHEUS_RETENTION_DAYS."""
    if _discovered_days is not None:
        return _discovered_days
    return float(settings.prometheus_retention_days)


def data_floor() -> Optional[datetime]:
    """The oldest sample Prometheus holds (UTC), or None when it doesn't
    report one, in which case only the configured retention bounds queries."""
    if _floor_ts is None:
        return None
    return datetime.fromtimestamp(_floor_ts, tz=timezone.utc)


async def refresh_retention(client: Optional[_RetentionSource]) -> None:
    """Re-read Prometheus's configured retention and its oldest sample, each
    when its cached value has expired.

    A failed or size-only retention read keeps the last good value; with
    none, the setting applies, and one warning is logged per failed fetch.
    A failed oldest-sample read clears the floor (skipped until the next
    read). Never raises. No lock: two concurrent fetches just write the same
    value.
    """
    if client is None:
        return
    now = time.monotonic()
    await _refresh_floor(client, now)
    await _refresh_storage_retention(client, now)


async def _refresh_floor(client: _RetentionSource, now: float) -> None:
    global _floor_ts, _floor_fetched_at
    if _floor_fetched_at is not None and now - _floor_fetched_at < _FLOOR_TTL_SECONDS:
        return
    try:
        ts = await client.lowest_sample_timestamp()
    except Exception as exc:  # lowest_sample_timestamp() doesn't raise; a stand-in might
        logger.warning("Prometheus oldest-sample lookup failed: %s", type(exc).__name__)
        ts = None
    _floor_ts = ts if isinstance(ts, (int, float)) and not isinstance(ts, bool) else None
    _floor_fetched_at = now


async def _refresh_storage_retention(client: _RetentionSource, now: float) -> None:
    global _discovered_days, _fetched_at, _last_ok
    if _fetched_at is not None:
        ttl = _SUCCESS_TTL_SECONDS if _last_ok else _FAILURE_TTL_SECONDS
        if now - _fetched_at < ttl:
            return

    try:
        raw = await client.storage_retention()
    except Exception as exc:  # storage_retention() doesn't raise; a stand-in might
        logger.warning("Prometheus retention lookup failed: %s", type(exc).__name__)
        raw = None
    days = parse_storage_retention(raw)
    _fetched_at = now
    _last_ok = days is not None
    if days is not None:
        _discovered_days = days
        return
    logger.warning(
        "Prometheus did not report a time retention (storageRetention=%r); using %s",
        raw,
        f"the last reported {_discovered_days}d" if _discovered_days is not None
        else f"PROMETHEUS_RETENTION_DAYS={settings.prometheus_retention_days}",
    )


def reset_retention_cache() -> None:
    """Forget what Prometheus reported. For tests."""
    global _discovered_days, _fetched_at, _last_ok, _floor_ts, _floor_fetched_at
    _discovered_days = None
    _fetched_at = None
    _last_ok = False
    _floor_ts = None
    _floor_fetched_at = None
