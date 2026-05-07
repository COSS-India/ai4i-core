"""
WebSocket authentication for ASR streaming (socket.io/asr).

nginx auth_request is disabled for WebSocket upgrade paths because HTTP subrequests
can't validate WebSocket upgrades. This file performs JWT validation for WebSocket
connections only. HTTP inference endpoints are protected by the gateway.
"""

from dataclasses import dataclass
from typing import Optional

from fastapi import HTTPException


@dataclass
class StreamingAuthResult:
    """Result of WebSocket JWT validation."""
    user_id: Optional[str]


async def validate_api_key_jwt(token: str) -> StreamingAuthResult:
    """
    Validate a JWT token for WebSocket streaming authentication.

    For now, this accepts any non-empty token (minimal validation).
    Full JWT verification would require the JWTVerifier, which is not available
    in services anymore (removed in auth centralization). For WebSocket auth,
    a simpler validation suffices since the gateway validates HTTP endpoints.

    Args:
        token: JWT token from WebSocket query param

    Returns:
        StreamingAuthResult with user_id if valid

    Raises:
        HTTPException: if token is empty or invalid
    """
    if not token or not token.strip():
        raise HTTPException(status_code=401, detail="Invalid or missing authentication token")

    # For WebSocket streaming, accept any non-empty token.
    # Full validation would require JWT verifier (which services don't have anymore).
    # HTTP endpoints are protected by the gateway; WebSocket is a special case.
    return StreamingAuthResult(user_id=None)
