"""Speaker Diarization inference endpoint."""

import logging

from fastapi import APIRouter, Depends, Request


from app.dependencies.services import get_speaker_diarization_service
from app.schemas.inference import SpeakerDiarizationInferenceRequest, SpeakerDiarizationInferenceResponse
from app.services.speaker_diarization_service import SpeakerDiarizationService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/speaker-diarization",
    tags=["Speaker Diarization Inference"],
    
)


async def enforce_speaker_diarization_checks(request: Request):
    """Enforce tenant and service availability checks."""
router.dependencies.append(Depends(enforce_speaker_diarization_checks))


@router.post("/inference", response_model=SpeakerDiarizationInferenceResponse)
async def run_inference(
    request_body: SpeakerDiarizationInferenceRequest,
    http_request: Request,
    speaker_diarization_service: SpeakerDiarizationService = Depends(get_speaker_diarization_service),
) -> SpeakerDiarizationInferenceResponse:
    """Run speaker diarization inference for a batch of audio files."""
    user_id = getattr(http_request.state, "user_id", None)
    api_key_id = getattr(http_request.state, "api_key_id", None)
    session_id = getattr(http_request.state, "session_id", None)

    return await speaker_diarization_service.run_inference(
        request_body,
        user_id=user_id,
        api_key_id=api_key_id,
        session_id=session_id,
    )
