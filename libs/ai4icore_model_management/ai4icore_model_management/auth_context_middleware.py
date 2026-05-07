"""
Auth context middleware: sets request.state.user_id from gateway-injected header before Model Resolution runs.

Enables A/B experiment variant selection to use a consistent user_id for inference calls.
User ID is read from X-User-ID header (set by gateway after auth validation).
"""

import logging
from typing import List

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class AuthContextMiddleware(BaseHTTPMiddleware):
    """
    Sets request.state.user_id from X-User-ID header on configured paths so Model Resolution
    middleware can use it for A/B variant hashing (same user -> same variant).
    Runs only on path_prefixes; does not reject requests (gateway auth does that).
    """

    def __init__(self, app, path_prefixes: List[str]):
        super().__init__(app)
        self.path_prefixes = [p.rstrip("/") for p in path_prefixes]

    async def dispatch(self, request: Request, call_next):
        path = request.url.path.rstrip("/") or "/"
        if any(path == p or path.startswith(p + "/") for p in self.path_prefixes):
            user_id = request.headers.get("X-User-ID")
            if user_id:
                request.state.user_id = user_id
        return await call_next(request)
