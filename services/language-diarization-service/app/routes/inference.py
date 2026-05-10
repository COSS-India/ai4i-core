"""Language Diarization inference endpoint."""

import logging

from fastapi import APIRouter, Depends, Request


from app.dependencies.services import get_language_diarization_service
from app.schemas.inference import (
    LanguageDiarizationInferenceRequest,
    LanguageDiarizationInferenceResponse,
)
from app.services.language_diarization_service import LanguageDiarizationService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/language-diarization",
    tags=["Language Diarization Inference"],
    
)


async def enforce_language_diarization_checks(request: Request):
    """Enforce tenant and service availability checks."""
router.dependencies.append(Depends(enforce_language_diarization_checks))


@router.post(
    "/inference",
    response_model=LanguageDiarizationInferenceResponse,
    summary="Perform language diarization inference",
    description="Run language diarization on one or more audio files using Triton.",
)
async def run_inference(
    request_body: LanguageDiarizationInferenceRequest,
    http_request: Request,
    language_diarization_service: LanguageDiarizationService = Depends(
        get_language_diarization_service
    ),
) -> LanguageDiarizationInferenceResponse:
    """Run language diarization inference for a batch of audio files."""
    user_id = getattr(http_request.state, "user_id", None)
    api_key_id = getattr(http_request.state, "api_key_id", None)
    session_id = getattr(http_request.state, "session_id", None)

    return await language_diarization_service.run_inference(
        request_body,
        user_id=user_id,
        api_key_id=api_key_id,
        session_id=session_id,
    )
