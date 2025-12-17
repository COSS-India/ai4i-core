"""
Inference router for Speaker Diarization service.

Exposes a ULCA-style speaker diarization inference endpoint:
- POST /api/v1/speaker-diarization/inference
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from models.speaker_diarization_request import SpeakerDiarizationInferenceRequest
from models.speaker_diarization_response import SpeakerDiarizationInferenceResponse
from repositories.speaker_diarization_repository import SpeakerDiarizationRepository, get_db_session
from services.speaker_diarization_service import SpeakerDiarizationService
from utils.triton_client import TritonClient, TritonInferenceError
from middleware.auth_provider import AuthProvider

logger = logging.getLogger(__name__)

inference_router = APIRouter(
    prefix="/api/v1/speaker-diarization",
    tags=["Speaker Diarization Inference"],
    dependencies=[Depends(AuthProvider)]  # Enforce auth and permission checks on all routes
)


async def get_speaker_diarization_service(
    request: Request,
    db: AsyncSession = Depends(get_db_session)
) -> SpeakerDiarizationService:
    """
    Dependency to construct SpeakerDiarizationService with configured Triton client and repository.

    REQUIRES Model Management database resolution - no environment variable fallback.
    Request must include config.serviceId for Model Management to resolve endpoint and model.
    """
    triton_endpoint: str = getattr(request.state, "triton_endpoint", None)
    triton_api_key: str = getattr(request.app.state, "triton_api_key", "")
    triton_timeout: float = getattr(request.app.state, "triton_timeout", 300.0)

    if not triton_endpoint:
        service_id = getattr(request.state, "service_id", None)
        if service_id:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=(
                    f"Model Management failed to resolve Triton endpoint for serviceId: {service_id}. "
                    f"Please ensure the service is registered in Model Management database."
                ),
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Request must include config.serviceId. "
                "Speaker Diarization service requires Model Management database resolution."
            ),
        )

    logger.info(
        "Using Triton endpoint=%s for serviceId=%s from Model Management",
        triton_endpoint,
        getattr(request.state, "service_id", "unknown"),
    )

    triton_client = TritonClient(triton_endpoint, triton_api_key or None, triton_timeout)
    repository = SpeakerDiarizationRepository(db)
    return SpeakerDiarizationService(triton_client=triton_client, repository=repository)


@inference_router.post(
    "/inference",
    response_model=SpeakerDiarizationInferenceResponse,
    summary="Perform speaker diarization inference",
    description="Run speaker diarization on one or more audio files using Triton.",
)
async def run_inference(
    request_body: SpeakerDiarizationInferenceRequest,
    http_request: Request,
    speaker_diarization_service: SpeakerDiarizationService = Depends(
        get_speaker_diarization_service
    ),
) -> SpeakerDiarizationInferenceResponse:
    """
    Run speaker diarization inference for a batch of audio files.
    """
    try:
        # Extract auth context from request.state (if middleware is configured)
        user_id = getattr(http_request.state, "user_id", None)
        api_key_id = getattr(http_request.state, "api_key_id", None)
        session_id = getattr(http_request.state, "session_id", None)

        logger.info(
            "Processing Speaker Diarization inference request with %d audio file(s), user_id=%s api_key_id=%s session_id=%s",
            len(request_body.audio),
            user_id,
            api_key_id,
            session_id,
        )

        # Run inference (Triton + Speaker Diarization)
        response = await speaker_diarization_service.run_inference(
            request_body,
            user_id=user_id,
            api_key_id=api_key_id,
            session_id=session_id
        )
        logger.info("Speaker Diarization inference completed successfully")
        return response

    except ValueError as exc:
        logger.warning("Validation error in Speaker Diarization inference: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except TritonInferenceError as exc:
        logger.error("Speaker Diarization Triton inference failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Speaker Diarization service temporarily unavailable",
        ) from exc
    except Exception as exc:  # pragma: no cover - generic error path
        logger.error("Speaker Diarization inference failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from exc

