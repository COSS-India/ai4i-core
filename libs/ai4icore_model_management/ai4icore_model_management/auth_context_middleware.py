"""
Auth context middleware: sets request.state.user_id from JWT (sub) before Model Resolution runs.

Enables A/B experiment variant selection to use a consistent user_id for inference calls. 
User ID is read from the JWT payload (sub or user_id claim); AuthProvider at route level performs full validation.
"""

import base64
import json
import logging
from typing import List

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


def _decode_jwt_payload_unverified(token: str) -> dict | None:
    """Decode JWT payload without verifying signature. Returns None on any error."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        # payload is the second part (base64url)
        payload_b64 = parts[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        return json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        return None


def _extract_user_id_from_jwt(request: Request) -> None:
    """
    If Authorization: Bearer <token> is present, read payload (no signature verify) and set
    request.state.user_id from payload['sub'] or payload['user_id']. AuthProvider validates
    the token later; spoofed tokens only affect A/B bucket for a request that gets rejected.
    """
    auth = request.headers.get("Authorization") or request.headers.get("authorization")
    if not auth or not auth.startswith("Bearer "):
        return
    token = auth.split(" ", 1)[1].strip()
    if not token:
        return
    payload = _decode_jwt_payload_unverified(token)
    if not payload:
        return
    user_id = payload.get("sub") or payload.get("user_id")
    if user_id is None:
        return
    token_type = payload.get("type", "")
    if token_type != "access":
        return
    request.state.user_id = int(user_id) if isinstance(user_id, (str, int)) else user_id


class AuthContextMiddleware(BaseHTTPMiddleware):
    """
    Sets request.state.user_id from JWT (sub) on configured paths so Model Resolution
    middleware can use it for A/B variant hashing (same user -> same variant).
    Runs only on path_prefixes; does not reject requests (route auth does that).
    """

    def __init__(self, app, path_prefixes: List[str]):
        super().__init__(app)
        self.path_prefixes = [p.rstrip("/") for p in path_prefixes]

    async def dispatch(self, request: Request, call_next):
        path = request.url.path.rstrip("/") or "/"
        if any(path == p or path.startswith(p + "/") for p in self.path_prefixes):
            _extract_user_id_from_jwt(request)
        return await call_next(request)
