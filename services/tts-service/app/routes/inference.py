"""TTS inference endpoint."""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request

from ai4icore_multi_tenant import enforce_tenant_and_service_checks
from ai4icore_constants.error_messages import SERVICE_UNAVAILABLE

from app.dependencies.auth import AuthProvider
from app.dependencies.services import get_tts_service
from app.schemas.inference import TTSInferenceRequest, TTSInferenceResponse
from app.services.tts_service import TTSService
from app.services.smr_service import SMRService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/tts",
    tags=["TTS Inference"],
    dependencies=[Depends(AuthProvider)],
)

smr_service = SMRService()


async def enforce_tts_checks(request: Request):
    """Enforce tenant and service availability checks."""
    await enforce_tenant_and_service_checks(
        request,
        service_name="tts",
        service_unavailable_code=SERVICE_UNAVAILABLE,
        service_inactive_message="TTS service is not active at the moment. Please contact your administrator",
        cannot_detect_message="Cannot detect TTS service availability. Please contact your administrator",
        timeout_message="TTS service is temporarily unavailable. Please try again in a few minutes.",
        generic_unavailable_message="TTS service is temporarily unavailable. Please try again in a few minutes.",
    )


router.dependencies.append(Depends(enforce_tts_checks))


async def resolve_service_id_if_needed(
    request: TTSInferenceRequest,
    http_request: Request,
) -> Optional[Dict[str, Any]]:
    """Dependency: resolve serviceId via SMR when not provided."""
    return await smr_service.resolve_service_id(request, http_request)


@router.post("/inference", response_model=TTSInferenceResponse)
async def run_inference(
    request: TTSInferenceRequest,
    http_request: Request,
    smr_response: Optional[Dict[str, Any]] = Depends(resolve_service_id_if_needed),
    tts_service: TTSService = Depends(get_tts_service),
) -> TTSInferenceResponse:
    """Run TTS inference on the given request."""

    # ── Extract auth context ──
    user_id = getattr(http_request.state, "user_id", None)
    api_key_id = getattr(http_request.state, "api_key_id", None)
    session_id = getattr(http_request.state, "session_id", None)

    # ── Run inference (fallback retry handled inside tts_service) ──
    response = await tts_service.run_inference(
        request=request,
        user_id=user_id,
        api_key_id=api_key_id,
        session_id=session_id,
        http_request=http_request,
    )

    # ── Attach SMR metadata ──
    smr_response_data = smr_response or getattr(http_request.state, "smr_response_data", None)
    response_dict = response.dict()
    response_dict["smr_response"] = smr_response_data
    return TTSInferenceResponse(**response_dict)
