import asyncio
import ipaddress
import json
import socket
from typing import Any, Dict
from urllib.parse import urlparse, urlunparse


def looks_like_cluster_internal_hostname(hostname: str) -> bool:
    h = hostname.strip(".").lower()
    if h in {"localhost", "kubernetes.default.svc"}:
        return True
    if h.endswith(".svc") or h.endswith(".svc.cluster.local") or h.endswith(".cluster.local"):
        return True
    return False


def is_disallowed_ip(ip: ipaddress._BaseAddress) -> bool:
    # Block internal/unsafe destinations to mitigate SSRF.
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
    Resolve *hostname* and ensure it does not map to private/link-local/loopback/etc.
    If resolution fails or times out, treat it as unsafe (fail closed).
    """
    if not hostname:
        return False

    if looks_like_cluster_internal_hostname(hostname):
        return False

    try:
        # If user supplied an IP literal, validate it directly.
        ip_literal = ipaddress.ip_address(hostname)
        return not is_disallowed_ip(ip_literal)
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
    """
    Remove userinfo (username/password) from a URL before logging.
    Keeps scheme, host, port, path, query, fragment.
    """
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        if not hostname:
            return url
        port = f":{parsed.port}" if parsed.port else ""
        netloc = f"{hostname}{port}"
        return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
    except Exception:
        return url


_REDACT_KEYS = {
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


def redact_json(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: Dict[str, Any] = {}
        for k, v in value.items():
            if isinstance(k, str) and k.strip().lower() in _REDACT_KEYS:
                redacted[k] = "[REDACTED]"
            else:
                redacted[k] = redact_json(v)
        return redacted
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

