"""Audio Language Detection inference endpoint."""

import logging

from fastapi import APIRouter, Depends, Request


from app.dependencies.services import get_audio_lang_detection_service
from app.schemas.inference import AudioLangDetectionInferenceRequest, AudioLangDetectionInferenceResponse
from app.services.audio_lang_detection_service import AudioLangDetectionService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/audio-lang-detection",
    tags=["Audio Language Detection Inference"],
    
)


async def enforce_audio_lang_detection_checks(request: Request):
    """Enforce tenant and service availability checks."""
router.dependencies.append(Depends(enforce_audio_lang_detection_checks))


@router.post("/inference", response_model=AudioLangDetectionInferenceResponse)
async def run_inference(
    request_body: AudioLangDetectionInferenceRequest,
    http_request: Request,
    audio_lang_detection_service: AudioLangDetectionService = Depends(get_audio_lang_detection_service),
) -> AudioLangDetectionInferenceResponse:
    """Run audio language detection inference for a batch of audio files."""
    user_id = getattr(http_request.state, "user_id", None)
    api_key_id = getattr(http_request.state, "api_key_id", None)
    session_id = getattr(http_request.state, "session_id", None)

    return await audio_lang_detection_service.run_inference(
        request_body,
        user_id=user_id,
        api_key_id=api_key_id,
        session_id=session_id,
    )
