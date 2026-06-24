"""
Standardized API response envelope for ALL microservices.

Every service uses this — consistent response shape across the platform.

Success: {"success": true, "data": ..., "meta": ...}
Error:   {"success": false, "error": {"code": ..., "message": ..., "details": ...}}
"""

from typing import Any, Optional


def success_response(data: Any = None, meta: Optional[dict[str, Any]] = None) -> dict:
    """Build a success response dict."""
    resp: dict[str, Any] = {"success": True, "data": data}
    if meta:
        resp["meta"] = meta
    return resp


def error_response(code: str, message: str, details: Optional[dict[str, Any]] = None) -> dict:
    """Build an error response dict."""
    err: dict[str, Any] = {"code": code, "message": message}
    if details:
        err["details"] = details
    return {"success": False, "error": err}
