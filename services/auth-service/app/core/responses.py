"""
API response envelope — re-exports from shared ai4icore_exceptions.

Inference / legacy format:   success_response, error_response
Platform management format:  platform_success_response, platform_error_response
"""

from ai4icore_exceptions import (  # noqa: F401
    success_response,
    error_response,
    generate_request_id,
    platform_success_response,
    platform_error_response,
)

__all__ = [
    "success_response",
    "error_response",
    "generate_request_id",
    "platform_success_response",
    "platform_error_response",
]
