"""Shared helpers for router modules."""

from typing import Optional

from fastapi import HTTPException, Request, status

from ai4icore_env import app_env
from validators import validate_endpoint, ValidationStatus


def get_user_id(request: Request) -> Optional[str]:
    """Extract user_id from request state as string."""
    user_id = getattr(request.state, "user_id", None)
    return str(user_id) if user_id is not None else None


async def validate_endpoint_or_raise(
    endpoint: str,
    task_type: Optional[str],
    request_schema: Optional[dict] = None,
    api_key: Optional[str] = None,
    triton_schema: Optional[dict] = None,
    error_message: str = "Endpoint validation failed.",
) -> None:
    """Run endpoint validation; raise HTTP 400 on failure."""
    validation = await validate_endpoint(
        endpoint=endpoint,
        task_type=task_type,
        request_schema=request_schema or None,
        api_key=api_key or None,
        run_inference_test=app_env.run_inference_test,
        timeout=app_env.endpoint_validation_timeout_seconds,
        validation_mode=app_env.endpoint_validation_mode,
        triton_schema=triton_schema or None,
    )
    if not validation.is_valid:
        failed = [d for d in validation.details if d.status == ValidationStatus.FAILED]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "kind": "EndpointValidationError",
                "message": error_message,
                "errors": [d.message for d in failed],
            },
        )
