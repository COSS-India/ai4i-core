"""
Standardized API response envelope for ALL microservices.

Every service uses this — consistent response shape across the platform.

Inference / legacy format:
  Success: {"success": true, "data": ..., "meta": ...}
  Error:   {"success": false, "error": {"code": ..., "message": ..., "details": ...}}

Platform management format (user/tenant/model/service routes):
  Success: {"requestId": "req_...", "status": "OK", "statusCode": 200, "message": "", "data": ...}
  Error:   {"requestId": "req_...", "status": "ERROR", "statusCode": N, "message": "...",
             "error": {"code": N, "message": "MACHINE_CODE", "params": {"MACHINE_CODE": "..."}}}
"""

import uuid
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Inference / legacy format (unchanged — all inference services use these)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Platform management format (auth-service user/tenant + platform-core routes)
# ---------------------------------------------------------------------------

def generate_request_id() -> str:
    """Generate a unique request ID with a 'req_' prefix."""
    return f"req_{uuid.uuid4()}"


def platform_success_response(
    data: Any = None,
    request_id: Optional[str] = None,
    message: str = "",
    status_code: int = 200,
) -> dict:
    """
    Build a platform management success response.

    Shape:
      {
        "requestId": "req_<uuid>",
        "status": "OK",
        "statusCode": 200,
        "message": "",
        "data": <payload>
      }
    """
    return {
        "requestId": request_id or generate_request_id(),
        "status": "OK",
        "statusCode": status_code,
        "message": message,
        "data": data,
    }


def platform_error_response(
    http_status: int,
    message: str,
    error_code: str,
    params: Optional[dict[str, Any]] = None,
    request_id: Optional[str] = None,
) -> dict:
    """
    Build a platform management error response.

    Shape:
      {
        "requestId": "req_<uuid>",
        "status": "ERROR",
        "statusCode": <http_status>,
        "message": "<human message>",
        "error": {
          "code": <http_status>,
          "message": "<MACHINE_CODE>",
          "params": {"<MACHINE_CODE>": "<human message>"}
        }
      }
    """
    return {
        "requestId": request_id or generate_request_id(),
        "status": "ERROR",
        "statusCode": http_status,
        "message": message,
        "error": {
            "code": http_status,
            "message": error_code,
            "params": params if params is not None else {error_code: message},
        },
    }
