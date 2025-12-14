"""
Inference router for Audio Language Detection service.

Exposes a ULCA-style audio language detection inference endpoint:
- POST /api/v1/audio-lang-detection/inference
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from models.audio_lang_detection_request import AudioLangDetectionInferenceRequest
from models.audio_lang_detection_response import AudioLangDetectionInferenceResponse
from repositories.audio_lang_detection_repository import AudioLangDetectionRepository, get_db_session
from services.audio_lang_detection_service import AudioLangDetectionService
from utils.triton_client import TritonClient, TritonInferenceError
from middleware.auth_provider import AuthProvider

logger = logging.getLogger(__name__)

inference_router = APIRouter(
    prefix="/api/v1/audio-lang-detection",
    tags=["Audio Language Detection Inference"],
    dependencies=[Depends(AuthProvider)]  # Enforce auth and permission checks on all routes
)


async def get_audio_lang_detection_service(
    request: Request,
    db: AsyncSession = Depends(get_db_session)
) -> AudioLangDetectionService:
    """
    Dependency to construct AudioLangDetectionService with configured Triton client and repository.

    Uses TRITON_ENDPOINT, TRITON_API_KEY, and TRITON_TIMEOUT from app.state (set in main.py).
    """
    triton_endpoint: str = getattr(request.app.state, "triton_endpoint", "")
    triton_api_key: str = getattr(request.app.state, "triton_api_key", "")
    triton_timeout: float = getattr(request.app.state, "triton_timeout", 300.0)

    if not triton_endpoint:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="TRITON_ENDPOINT is not configured for Audio Language Detection service",
        )

    triton_client = TritonClient(triton_endpoint, triton_api_key or None, triton_timeout)
    repository = AudioLangDetectionRepository(db)
    return AudioLangDetectionService(triton_client=triton_client, repository=repository)


@inference_router.post(
    "/inference",
    response_model=AudioLangDetectionInferenceResponse,
    summary="Perform audio language detection inference",
    description="Detect the language of one or more audio files using Triton.",
)
async def run_inference(
    request_body: AudioLangDetectionInferenceRequest,
    http_request: Request,
    audio_lang_detection_service: AudioLangDetectionService = Depends(
        get_audio_lang_detection_service
    ),
) -> AudioLangDetectionInferenceResponse:
    """
    Run audio language detection inference for a batch of audio files.
    """
    try:
        # Extract auth context from request.state (if middleware is configured)
        user_id = getattr(http_request.state, "user_id", None)
        api_key_id = getattr(http_request.state, "api_key_id", None)
        session_id = getattr(http_request.state, "session_id", None)

        logger.info(
            "Processing Audio Language Detection inference request with %d audio file(s), user_id=%s api_key_id=%s session_id=%s",
            len(request_body.audio),
            user_id,
            api_key_id,
            session_id,
        )

        # Run inference (Triton + Audio Language Detection)
        response = await audio_lang_detection_service.run_inference(
            request_body,
            user_id=user_id,
            api_key_id=api_key_id,
            session_id=session_id
        )
        logger.info("Audio Language Detection inference completed successfully")
        return response

    except ValueError as exc:
        logger.warning("Validation error in Audio Language Detection inference: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except TritonInferenceError as exc:
        logger.error("Audio Language Detection Triton inference failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Audio Language Detection service temporarily unavailable",
        ) from exc
    except Exception as exc:  # pragma: no cover - generic error path
        logger.error("Audio Language Detection inference failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from exc

