"""
Inference router for Language Diarization service.

Exposes a ULCA-style language diarization inference endpoint:
- POST /api/v1/language-diarization/inference
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status

from models.language_diarization_request import LanguageDiarizationInferenceRequest
from models.language_diarization_response import LanguageDiarizationInferenceResponse
from services.language_diarization_service import LanguageDiarizationService
from utils.triton_client import TritonClient, TritonInferenceError

logger = logging.getLogger(__name__)

inference_router = APIRouter(
    prefix="/api/v1/language-diarization",
    tags=["Language Diarization Inference"],
)


def get_language_diarization_service(request: Request) -> LanguageDiarizationService:
    """
    Dependency to construct LanguageDiarizationService with configured Triton client.

    Uses TRITON_ENDPOINT, TRITON_API_KEY, and TRITON_TIMEOUT from app.state (set in main.py).
    """
    triton_endpoint: str = getattr(request.app.state, "triton_endpoint", "")
    triton_api_key: str = getattr(request.app.state, "triton_api_key", "")
    triton_timeout: float = getattr(request.app.state, "triton_timeout", 300.0)

    if not triton_endpoint:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="TRITON_ENDPOINT is not configured for Language Diarization service",
        )

    triton_client = TritonClient(triton_endpoint, triton_api_key or None, triton_timeout)
    return LanguageDiarizationService(triton_client=triton_client)


@inference_router.post(
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
    """
    Run language diarization inference for a batch of audio files.
    """
    try:
        # Extract auth context from request.state (if middleware is configured)
        user_id = getattr(http_request.state, "user_id", None)
        api_key_id = getattr(http_request.state, "api_key_id", None)
        session_id = getattr(http_request.state, "session_id", None)

        logger.info(
            "Processing Language Diarization inference request with %d audio file(s), user_id=%s api_key_id=%s session_id=%s",
            len(request_body.audio),
            user_id,
            api_key_id,
            session_id,
        )

        # Run inference (Triton + Language Diarization)
        response = language_diarization_service.run_inference(request_body)
        logger.info("Language Diarization inference completed successfully")
        return response

    except ValueError as exc:
        logger.warning("Validation error in Language Diarization inference: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except TritonInferenceError as exc:
        logger.error("Language Diarization Triton inference failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Language Diarization service temporarily unavailable",
        ) from exc
    except Exception as exc:  # pragma: no cover - generic error path
        logger.error("Language Diarization inference failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from exc

