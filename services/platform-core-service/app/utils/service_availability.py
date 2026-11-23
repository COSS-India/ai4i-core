"""Service List "Availability" column — live up/down via Prometheus's `up` metric.

Matches by IP only (not IP:port): a service's stored endpoint carries no
reliable port/job mapping back to the scrape target, so every instance behind
an IP is queried and the IP counts online if any of its instances reports up.
An IP that PROMETHEUS_VLLM_JOB_NAME never scrapes at all (Triton ASR/NMT/TTS,
external LLM endpoints, anything addressed by hostname) is unknown, not
offline — it reports None, same as a Prometheus/job-name misconfiguration.
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
) -> Dict[str, Optional[bool]]:
    """IP -> online (True) / offline (False) / not scraped by this job (None),
    via one bulk `up{job=...}` query.

    False means Prometheus scraped it and `up` was 0 — a real down signal, not
    "we don't know." An IP this job never targets at all (so no series comes
    back for it) stays None rather than being guessed as offline.

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
    status: Dict[str, Optional[bool]] = dict.fromkeys(unique_ips, None)
    for series in result:
        instance = series.get("metric", {}).get("instance", "")
        ip = instance.split(":", 1)[0]
        if ip not in status:
            continue
        value = series.get("value", [None, "0"])[1]
        if value == "1":
            status[ip] = True
        elif status[ip] is None:
            # Multiple ports behind one IP: a later "down" series must not
            # clobber an earlier "up" one — any instance up counts the IP online.
            status[ip] = False
    return status
