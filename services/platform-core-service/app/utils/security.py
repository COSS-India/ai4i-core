"""
Endpoint security helpers — SSRF protection and log sanitization.

These helpers are used during inference-endpoint validation (probing) to
ensure user-supplied endpoint URLs cannot be used to attack internal
infrastructure.

Behavior:
- Resolve the hostname; reject if it maps to private/loopback/link-local/
  reserved/multicast/unspecified IPs.
- Reject Kubernetes/cluster-internal hostnames outright (`*.svc`,
  `*.cluster.local`, `localhost`, etc.).
- Sanitize URLs for logging (strip user:pass) and redact sensitive keys
  in request/response bodies.

ENDPOINT_VALIDATION_ALLOW_PRIVATE_HOSTS=true relaxes only the private/
reserved rule, for deployments whose model fleet lives entirely on private
infrastructure. The hard blocks below (cloud metadata, loopback,
link-local, unspecified, multicast, cluster-internal hostnames) are not
configurable and hold either way.
"""

import asyncio
import ipaddress
import json
import logging
import socket
from typing import Any, Dict
from urllib.parse import urlparse, urlunparse

from app.core.config import settings

logger = logging.getLogger(__name__)


_REDACT_KEYS = frozenset(
    {
        "authorization",
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "token",
        "password",
        "secret",
        "credential",
        "credentials",
        "x-api-key",
    }
)


def looks_like_cluster_internal_hostname(hostname: str) -> bool:
    h = hostname.strip(".").lower()
    if h in {"localhost", "kubernetes.default.svc"}:
        return True
    return (
        h.endswith(".svc")
        or h.endswith(".svc.cluster.local")
        or h.endswith(".cluster.local")
    )


def is_disallowed_ip(ip: ipaddress._BaseAddress) -> bool:
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


# Never probeable, whatever ENDPOINT_VALIDATION_ALLOW_PRIVATE_HOSTS says.
# `is_link_local` already covers IPv4 169.254.0.0/16, and with it the cloud
# metadata service at 169.254.169.254. The IPv6 metadata address is a
# unique-local address, so it reads as merely "private" and would be let
# through by the setting: it is listed explicitly instead.
_ALWAYS_BLOCKED_NETWORKS = (
    ipaddress.ip_network("fd00:ec2::254/128"),
)


def is_always_blocked_ip(ip: ipaddress._BaseAddress) -> bool:
    """Addresses that must never be probed, regardless of configuration.

    Cloud metadata hands out credentials to anything that asks, and loopback
    reaches this service's own pod and any sidecar admin ports. Neither is a
    legitimate model endpoint on any deployment, so neither is negotiable.
    """
    if ip.is_loopback or ip.is_unspecified or ip.is_multicast or ip.is_link_local:
        return True
    # A version mismatch makes `in` return False rather than raise, so a v4
    # address tested against a v6 network is simply not a match.
    return any(ip in network for network in _ALWAYS_BLOCKED_NETWORKS)


def _is_ip_allowed(ip: ipaddress._BaseAddress, hostname: str) -> bool:
    """Apply the endpoint-host policy to a single resolved address."""
    if is_always_blocked_ip(ip):
        return False
    if not is_disallowed_ip(ip):
        return True
    if settings.endpoint_validation_allow_private_hosts:
        # Audit trail: every host that only got through because the trusted-
        # network setting is on is recorded, with what it resolved to.
        logger.info(
            "Endpoint host '%s' (%s) allowed by "
            "ENDPOINT_VALIDATION_ALLOW_PRIVATE_HOSTS.",
            hostname,
            ip,
        )
        return True
    return False


async def is_safe_host(hostname: str, *, resolve_timeout_s: float = 2.0) -> bool:
    """
    Resolve *hostname* and ensure all resulting IPs are allowed as endpoint
    hosts. Returns False (fail-closed) on resolution failure or unsafe IP.
    """
    if not hostname:
        return False
    if looks_like_cluster_internal_hostname(hostname):
        return False

    # Direct IP literal? Validate without DNS.
    try:
        ip = ipaddress.ip_address(hostname)
        return _is_ip_allowed(ip, hostname)
    except ValueError:
        pass

    try:
        loop = asyncio.get_running_loop()
        infos = await asyncio.wait_for(
            loop.getaddrinfo(hostname, None, type=socket.SOCK_STREAM),
            timeout=resolve_timeout_s,
        )
    except Exception:
        return False

    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except Exception:
            return False
        if not _is_ip_allowed(ip, hostname):
            return False
    return True


def sanitize_url_for_log(url: str) -> str:
    """Strip embedded user:pass credentials from a URL before logging."""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        if not hostname:
            return url
        port = f":{parsed.port}" if parsed.port else ""
        netloc = f"{hostname}{port}"
        return urlunparse(
            (
                parsed.scheme,
                netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )
    except Exception:
        return url


def redact_json(value: Any) -> Any:
    """Recursively redact any sensitive keys in a JSON-shaped value."""
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            if isinstance(k, str) and k.strip().lower() in _REDACT_KEYS:
                out[k] = "[REDACTED]"
            else:
                out[k] = redact_json(v)
        return out
    if isinstance(value, list):
        return [redact_json(v) for v in value]
    return value


def truncate_for_log(text: str, *, max_len: int = 500) -> str:
    if text is None:
        return "(null)"
    if len(text) <= max_len:
        return text
    return text[:max_len] + "…(truncated)"


def json_body_for_log(body_obj: Any) -> str:
    return json.dumps(redact_json(body_obj), ensure_ascii=False)
