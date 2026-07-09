"""Process memory helpers for Prometheus metrics and per-request log lines."""

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterable, Optional

import psutil
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector

from config import settings

_mem_before: ContextVar[Optional["ProcessMemorySnapshot"]] = ContextVar(
    "request_memory_before", default=None
)


@dataclass(frozen=True)
class ProcessMemorySnapshot:
    """RSS/VMS snapshot for the inference-service process."""

    rss_bytes: int
    vms_bytes: int

    @property
    def rss_mb(self) -> float:
        return round(self.rss_bytes / (1024 * 1024), 2)

    @property
    def vms_mb(self) -> float:
        return round(self.vms_bytes / (1024 * 1024), 2)


def get_process_memory_snapshot() -> ProcessMemorySnapshot:
    """Read current process RSS/VMS via psutil."""
    mem = psutil.Process().memory_info()
    return ProcessMemorySnapshot(rss_bytes=mem.rss, vms_bytes=mem.vms)


def _enabled() -> bool:
    return settings.MEMORY_LOG_ENABLED


def start_request_memory() -> None:
    """Capture RSS at the start of a root inference request span."""
    if not _enabled():
        return
    _mem_before.set(get_process_memory_snapshot())


def collect_request_memory() -> dict:
    """Return before/after/delta memory fields for the current request."""
    if not _enabled():
        return {}
    before = _mem_before.get()
    after = get_process_memory_snapshot()
    if before is None:
        return {
            "memory_rss_after_mb": after.rss_mb,
            "memory_vms_after_mb": after.vms_mb,
        }
    return {
        "memory_rss_before_mb": before.rss_mb,
        "memory_rss_after_mb": after.rss_mb,
        "memory_rss_delta_mb": round(after.rss_mb - before.rss_mb, 2),
        "memory_vms_before_mb": before.vms_mb,
        "memory_vms_after_mb": after.vms_mb,
        "memory_vms_delta_mb": round(after.vms_mb - before.vms_mb, 2),
    }


def format_memory_summary(attrs: dict) -> str:
    """Build a one-line MEMORY summary for request logs."""
    if "memory_rss_after_mb" not in attrs:
        return ""
    parts = []
    if "memory_rss_before_mb" in attrs:
        parts.append(f"rss_before={attrs['memory_rss_before_mb']}MB")
    parts.append(f"rss_after={attrs['memory_rss_after_mb']}MB")
    if "memory_rss_delta_mb" in attrs:
        parts.append(f"rss_delta={attrs['memory_rss_delta_mb']}MB")
    return "MEMORY " + " ".join(parts)


class ProcessMemoryCollector(Collector):
    """Expose RSS using the standard process_resident_memory_bytes metric name."""

    def collect(self) -> Iterable[GaugeMetricFamily]:
        rss = get_process_memory_snapshot().rss_bytes
        yield GaugeMetricFamily(
            "process_resident_memory_bytes",
            "Resident memory size in bytes.",
            value=rss,
        )
