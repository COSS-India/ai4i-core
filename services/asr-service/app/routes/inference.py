"""ASR inference endpoint -- thin route handler."""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request

from ai4icore_multi_tenant import enforce_tenant_and_service_checks
from ai4icore_constants.error_messages import SERVICE_UNAVAILABLE, SERVICE_UNAVAILABLE_MESSAGE

from app.dependencies.auth import AuthProvider
from app.dependencies.services import get_asr_service
from app.schemas.inference import (
    ASRInferenceRequest,
    ASRInferenceResponse,
)
from app.services.asr_service import ASRService
from app.services.smr_service import SMRService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/asr",
    tags=["ASR Inference"],
    dependencies=[Depends(AuthProvider)],
)

smr_service = SMRService()


async def enforce_asr_checks(request: Request):
    """Enforce tenant and service availability checks."""
    await enforce_tenant_and_service_checks(
        request,
        service_name="asr",
        service_unavailable_code=SERVICE_UNAVAILABLE,
        service_inactive_message="ASR service is not active at the moment. Please contact your administrator",
        cannot_detect_message="Cannot detect ASR service availability. Please contact your administrator",
        timeout_message=SERVICE_UNAVAILABLE_MESSAGE,
        generic_unavailable_message=SERVICE_UNAVAILABLE_MESSAGE,
    )


router.dependencies.append(Depends(enforce_asr_checks))


async def resolve_service_id_if_needed(
    request: ASRInferenceRequest,
    http_request: Request,
) -> Optional[Dict[str, Any]]:
    """Dependency: resolve serviceId via SMR when not provided."""
    return await smr_service.resolve_service_id(request, http_request)


@router.post(
    "/inference",
    response_model=ASRInferenceResponse,
    response_model_exclude_none=False,
    summary="Perform batch ASR inference",
    description="Convert speech to text for one or more audio inputs",
)
async def run_inference(
    request: ASRInferenceRequest,
    http_request: Request,
    smr_response: Optional[Dict[str, Any]] = Depends(resolve_service_id_if_needed),
    asr_service: ASRService = Depends(get_asr_service),
) -> ASRInferenceResponse:
    """Run ASR inference on audio inputs."""
    # Extract auth context
    user_id = getattr(http_request.state, "user_id", None)
    api_key_id = getattr(http_request.state, "api_key_id", None)
    session_id = getattr(http_request.state, "session_id", None)

    # Run inference (fallback retry handled inside asr_service)
    response = await asr_service.run_inference(
        request=request,
        user_id=user_id,
        api_key_id=api_key_id,
        session_id=session_id,
        http_request=http_request,
    )

    # Attach SMR metadata
    smr_response_data = smr_response or getattr(http_request.state, "smr_response_data", None)
    try:
        response_dict = response.model_dump(exclude_none=False)
    except AttributeError:
        response_dict = response.dict(exclude_none=False)
    response_dict["smr_response"] = smr_response_data
    return ASRInferenceResponse(**response_dict)


@router.get(
    "/models",
    response_model=Dict[str, Any],
    summary="List available ASR models",
    description="Get list of supported ASR models and languages",
)
async def list_models() -> Dict[str, Any]:
    """List available ASR models."""
    return {
        "models": [
            {
                "model_id": "vakyansh-asr-en",
                "languages": ["en"],
                "description": "English ASR model",
            },
            {
                "model_id": "conformer-asr-multilingual",
                "languages": ["hi", "ta", "te", "kn", "ml"],
                "description": "Multilingual ASR model for Indic languages",
            },
            {
                "model_id": "whisper-large-v3",
                "languages": ["en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa"],
                "description": "Whisper large v3 multilingual model",
            },
        ],
        "supported_languages": [
            "en", "hi", "ta", "te", "kn", "ml", "bn", "gu", "mr", "pa",
            "or", "as", "ur", "sa", "ks", "ne", "sd", "kok", "doi", "mai",
            "brx", "mni",
        ],
        "supported_formats": ["wav", "mp3", "flac", "ogg", "pcm"],
        "transcription_formats": ["transcript", "srt", "webvtt"],
    }
