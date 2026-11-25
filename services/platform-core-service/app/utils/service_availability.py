"""Service List "Availability" column — live up/down via Prometheus's `up` metric.

Matches by exact instance (IP:port): a service's stored endpoint port is the
same port Prometheus's `instance` label carries for that scrape target, so
each service is checked against its own instance rather than every instance
behind its IP. A service whose endpoint has no explicit port, or whose
instance PROMETHEUS_VLLM_JOB_NAME never scrapes at all (Triton ASR/NMT/TTS,
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


def extract_instance(endpoint: Optional[str]) -> Optional[str]:
    """``host:port`` from a service endpoint URL, or None if it can't be
    parsed or carries no explicit port (nothing to match a scrape instance
    against)."""
    if not endpoint:
        return None
    parsed = urlparse(endpoint)
    if not parsed.hostname or parsed.port is None:
        return None
    return f"{parsed.hostname}:{parsed.port}"


async def get_instance_availability(
    client: PrometheusClient, job_name: Optional[str], instances: Iterable[str]
) -> Dict[str, Optional[bool]]:
    """instance (host:port) -> online (True) / offline (False) / not scraped
    by this job (None), via one bulk `up{job=...}` query.

    False means Prometheus scraped it and `up` was 0 — a real down signal, not
    "we don't know." An instance this job never targets at all (so no series
    comes back for it) stays None rather than being guessed as offline.

    Returns {} (unknown for every instance) when job_name is unset, there are
    no instances to check, or the Prometheus query itself fails.
    """
    unique_instances = sorted({instance for instance in instances if instance})
    if not job_name or not unique_instances:
        return {}
    # No re.escape: Python escapes `-` (invalid as `\-` in Prometheus's RE2
    # regex outside a character class) and a literal `\.` would need
    # double-escaping to survive PromQL's own Go-style string-literal
    # grammar first. An unescaped `.` just matches any one character here,
    # which is harmless for IPs/hostnames and avoids both problems. Prometheus
    # anchors `=~` matches to the whole label value, so the plain instance
    # strings alone (no `.*` suffix) already require an exact match.
    pattern = "|".join(unique_instances)
    promql = f'up{{job="{job_name}", instance=~"{pattern}"}}'
    try:
        result = await client.query(promql)
    except Exception as exc:
        logger.warning("Service availability query failed: %s", type(exc).__name__)
        return {}
    status: Dict[str, Optional[bool]] = dict.fromkeys(unique_instances, None)
    for series in result:
        instance = series.get("metric", {}).get("instance", "")
        if instance not in status:
            continue
        value = series.get("value", [None, "0"])[1]
        if value == "1":
            status[instance] = True
        elif status[instance] is None:
            # Duplicate/stale series for the same instance must not clobber
            # an earlier "up" one.
            status[instance] = False
    return status
