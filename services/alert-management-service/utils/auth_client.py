"""
Auth client for alert-management-service (standalone auth when not behind API gateway).
Validates JWT via auth-service and returns user payload for permission checks.
"""
import os
from typing import Optional, Dict, Any
import httpx

AUTH_SERVICE_URL = os.getenv("AUTH_SERVICE_URL", "http://auth-service:8081")
_http_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=10.0)
    return _http_client


async def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify JWT with auth-service (same contract as API gateway auth_middleware).
    Returns payload with username, user_id (sub), permissions, roles; or None if invalid.
    """
    try:
        client = _get_client()
        response = await client.post(
            f"{AUTH_SERVICE_URL.rstrip('/')}/api/v1/auth/validate",
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code != 200:
            return None
        data = response.json()
        user_id = str(data.get("user_id", data.get("sub", "")))
        return {
            "sub": user_id,
            "user_id": user_id,
            "username": data.get("username"),
            "permissions": data.get("permissions", []),
            "roles": data.get("roles", []),
        }
    except (httpx.RequestError, Exception):
        return None


async def close_auth_client():
    """Close the HTTP client (call on app shutdown)."""
    global _http_client
    if _http_client is not None:
        await _http_client.aclose()
        _http_client = None
