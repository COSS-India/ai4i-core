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
"""

import asyncio
import ipaddress
import json
import socket
from typing import Any, Dict
from urllib.parse import urlparse, urlunparse


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


async def is_safe_host(hostname: str, *, resolve_timeout_s: float = 2.0) -> bool:
    """
    Resolve *hostname* and ensure all resulting IPs are public/routable.
    Returns False (fail-closed) on resolution failure or unsafe IP.
    """
    if not hostname:
        return False
    if looks_like_cluster_internal_hostname(hostname):
        return False

    # Direct IP literal? Validate without DNS.
    try:
        ip = ipaddress.ip_address(hostname)
        return not is_disallowed_ip(ip)
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
        if is_disallowed_ip(ip):
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
