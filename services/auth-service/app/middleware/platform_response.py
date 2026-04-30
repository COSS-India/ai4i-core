"""
PlatformResponseMiddleware — transforms error responses to the platform
management format for user and tenant management endpoints.

Only activated for paths that contain /auth/me, /auth/users, or /tenants.
All other paths (auth, roles, api-keys, health, inference) are passed through
unchanged.

Error shape produced:
  {
    "requestId": "req_<uuid>",
    "status": "ERROR",
    "statusCode": <http_status>,
    "message": "<human readable message>",
    "error": {
      "code": <http_status>,
      "message": "<MACHINE_CODE>",
      "params": {"<MACHINE_CODE>": "<human readable message>"}
    }
  }

The matching requestId is set on request.state.platform_request_id before the
route handler runs so that success responses from user.py / tenants.py can
embed the same ID.
"""

import json
import logging
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from ai4icore_exceptions import platform_error_response

logger = logging.getLogger(__name__)

# Path segments that activate the platform management response format.
# Checked via substring match so versioned prefixes (/api/v1/...) work.
_MANAGED_SEGMENTS = ("/auth/me", "/auth/users", "/tenants")


def _is_managed(path: str) -> bool:
    return any(seg in path for seg in _MANAGED_SEGMENTS)


class PlatformResponseMiddleware(BaseHTTPMiddleware):
    """Intercepts user/tenant route responses and applies the platform format."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if not _is_managed(request.url.path):
            return await call_next(request)

        # Assign a stable request ID; route handlers read it for success bodies.
        request_id = f"req_{uuid.uuid4()}"
        request.state.platform_request_id = request_id

        response = await call_next(request)

        # Success responses are already in the new format (returned by route handlers).
        if response.status_code < 400:
            return response

        # Buffer the error body for transformation.
        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        try:
            content = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            logger.warning("PlatformResponseMiddleware: non-JSON error body, passing through")
            return Response(
                content=body,
                status_code=response.status_code,
                media_type=response.media_type,
                headers={k: v for k, v in response.headers.items() if k.lower() != "content-length"},
            )

        detail = content.get("detail", {})

        if isinstance(detail, dict):
            machine_code = detail.get("code", "ERROR")
            human_message = detail.get("message", "An error occurred")
        elif isinstance(detail, list) and detail:
            # Pydantic / FastAPI validation error list
            machine_code = "VALIDATION_ERROR"
            first = detail[0]
            human_message = first.get("msg", "Validation failed") if isinstance(first, dict) else "Validation failed"
        elif isinstance(detail, str):
            machine_code = "ERROR"
            human_message = detail
        else:
            machine_code = "ERROR"
            human_message = "An error occurred"

        new_body = platform_error_response(
            http_status=response.status_code,
            message=human_message,
            error_code=str(machine_code),
            request_id=request_id,
        )

        # Preserve upstream headers (trace ID, CORS, etc.) but drop content-length
        # — JSONResponse recalculates it.
        passthrough_headers = {
            k: v
            for k, v in response.headers.items()
            if k.lower() not in ("content-length", "content-type")
        }

        return JSONResponse(
            status_code=response.status_code,
            content=new_body,
            headers=passthrough_headers,
        )
