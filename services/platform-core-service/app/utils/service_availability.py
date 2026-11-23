"""Service List "Availability" column — live up/down via Prometheus's `up` metric.

Matches by IP only (not IP:port): a service's stored endpoint carries no
reliable port/job mapping back to the scrape target, so every instance behind
an IP is queried and the IP counts online if any of its instances reports up.
Never raises — Prometheus being unreachable/unconfigured degrades the column
to unknown (null) rather than failing the whole services list.
"""
import logging
from typing import Dict, Iterable, Optional
from urllib.parse import urlparse

from app.utils.prometheus_client import PrometheusClient

logger = logging.getLogger(__name__)


def extract_ip(endpoint: Optional[str]) -> Optional[str]:
    """Bare host/IP from a service endpoint URL, or None if it can't be parsed."""
    if not endpoint:
        return None
    return urlparse(endpoint).hostname


async def get_ip_availability(
    client: PrometheusClient, job_name: Optional[str], ips: Iterable[str]
) -> Dict[str, bool]:
    """IP -> online (True) / offline (False), via one bulk `up{job=...}` query.

    Returns {} (unknown for every IP) when job_name is unset, there are no IPs
    to check, or the Prometheus query itself fails.
    """
    unique_ips = sorted({ip for ip in ips if ip})
    if not job_name or not unique_ips:
        return {}
    # No re.escape: Python escapes `-` (invalid as `\-` in Prometheus's RE2
    # regex outside a character class) and a literal `\.` would need
    # double-escaping to survive PromQL's own Go-style string-literal
    # grammar first. An unescaped `.` just matches any one character here,
    # which is harmless for IPs/hostnames and avoids both problems.
    pattern = "|".join(f"{ip}:.*" for ip in unique_ips)
    promql = f'up{{job="{job_name}", instance=~"{pattern}"}}'
    try:
        result = await client.query(promql)
    except Exception as exc:
        logger.warning("Service availability query failed: %s", type(exc).__name__)
        return {}
    status = dict.fromkeys(unique_ips, False)
    for series in result:
        instance = series.get("metric", {}).get("instance", "")
        ip = instance.split(":", 1)[0]
        value = series.get("value", [None, "0"])[1]
        if ip in status and value == "1":
            status[ip] = True
    return status
