"""Speaker Diarization inference endpoint."""

import logging

from fastapi import APIRouter, Depends, Request

from ai4icore_multi_tenant import enforce_tenant_and_service_checks

from app.dependencies.auth import AuthProvider
from app.dependencies.services import get_speaker_diarization_service
from app.schemas.inference import SpeakerDiarizationInferenceRequest, SpeakerDiarizationInferenceResponse
from app.services.speaker_diarization_service import SpeakerDiarizationService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/speaker-diarization",
    tags=["Speaker Diarization Inference"],
    dependencies=[Depends(AuthProvider)],
)


async def enforce_speaker_diarization_checks(request: Request):
    """Enforce tenant and service availability checks."""
    await enforce_tenant_and_service_checks(
        request,
        service_name="speaker_diarization",
        service_unavailable_code="SERVICE_UNAVAILABLE",
        service_inactive_message="Speaker Diarization service is not active at the moment. Please contact your administrator",
        cannot_detect_message="Cannot detect Speaker Diarization service availability. Please contact your administrator",
        timeout_message="Speaker Diarization service is temporarily unavailable. Please try again in a few minutes.",
        generic_unavailable_message="Speaker Diarization service is temporarily unavailable. Please try again in a few minutes.",
    )


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
