"""
User identity helpers for route handlers.

Authentication is handled exclusively at the gateway layer.
The gateway forwards the authenticated user's ID via the X-User-Id header.
"""

from typing import Optional

from fastapi import Request


def get_user_id(request: Request) -> Optional[str]:
    """Return the calling user's ID forwarded by the gateway via X-User-Id header.

    Returns None when the header is absent (unauthenticated / internal requests).
    """
    return request.headers.get("X-User-Id") or None
