"""
Profile router – exposes the POST /api/v1/profile endpoint.

This router is the single public entry-point of the service.
It delegates all upstream I/O to the profiler client service layer
and returns the upstream response verbatim.
"""

from typing import Any, Dict

from fastapi import APIRouter

from models.profile_request import ProfileRequest
from services.profiler_client import call_profiler_api

router = APIRouter(prefix="/api/v1", tags=["profiling"])


@router.post(
    "/profile",
    summary="Profile text for domain and complexity",
    response_description="Verbatim response from the upstream profiler API",
)
async def profile_text(request: ProfileRequest) -> Dict[str, Any]:
    """Profile the given text by forwarding it to the upstream profiler API.

    **Request body:**
    - `text` – The text string to analyse.

    **Response:** The exact JSON payload returned by the upstream API, which
    typically includes domain classification and complexity scores.
    """
    return await call_profiler_api(request.text)
