"""
SSRF guard for user-supplied download URIs (OWASP API7).

Audio/image items may carry an audioUri/imageUri that the service fetches
server-side. Without validation a caller can make the service request
internal endpoints (cloud metadata, localhost admin ports, RFC-1918 hosts).

validate_external_url() enforces:
  - http/https scheme only
  - hostname resolves to public addresses only (loopback, private,
    link-local, metadata ranges rejected)

ALLOW_PRIVATE_DOWNLOAD_HOSTS=true disables the address check for local
development, where test fixtures are typically served from localhost.
"""

import ipaddress
import socket
from urllib.parse import urlparse

from config import settings


def validate_external_url(url: str) -> None:
    """
    Validate a user-supplied URL before the service fetches it.

    Raises:
        ValueError: If the scheme is not http(s), the host is missing,
            cannot be resolved, or resolves to a non-public address.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL scheme '{parsed.scheme}' is not allowed; use http(s)")
    if not parsed.hostname:
        raise ValueError("URL has no hostname")

    if settings.ALLOW_PRIVATE_DOWNLOAD_HOSTS:
        return

    try:
        addr_infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"Cannot resolve host '{parsed.hostname}'") from exc

    for info in addr_infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError(
                f"Host '{parsed.hostname}' resolves to a non-public address; "
                "downloads from internal networks are not allowed"
            )
