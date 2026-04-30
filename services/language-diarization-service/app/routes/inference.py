"""Language Diarization inference endpoint."""

import logging

from fastapi import APIRouter, Depends, Request

from ai4icore_multi_tenant import enforce_tenant_and_service_checks

from app.dependencies.auth import AuthProvider
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
    dependencies=[Depends(AuthProvider)],
)


async def enforce_language_diarization_checks(request: Request):
    """Enforce tenant and service availability checks."""
    await enforce_tenant_and_service_checks(
        request,
        service_name="language_diarization",
        service_unavailable_code="SERVICE_UNAVAILABLE",
        service_inactive_message="Language Diarization service is not active at the moment. Please contact your administrator",
        cannot_detect_message="Cannot detect Language Diarization service availability. Please contact your administrator",
        timeout_message="Language Diarization service is temporarily unavailable. Please try again in a few minutes.",
        generic_unavailable_message="Language Diarization service is temporarily unavailable. Please try again in a few minutes.",
    )


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
