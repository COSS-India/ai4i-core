"""
Inference router for OCR service.

Exposes a ULCA-style OCR inference endpoint:
- POST /api/v1/ocr/inference
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status

from models.ocr_request import OCRInferenceRequest
from models.ocr_response import OCRInferenceResponse
from services.ocr_service import OCRService
from utils.triton_client import TritonClient, TritonInferenceError
from middleware.auth_provider import AuthProvider

logger = logging.getLogger(__name__)

inference_router = APIRouter(
    prefix="/api/v1/ocr",
    tags=["OCR Inference"],
    dependencies=[Depends(AuthProvider)],
)


def get_ocr_service(request: Request) -> OCRService:
    """
    Dependency to construct OCRService with configured Triton client.

    Uses TRITON_ENDPOINT and TRITON_API_KEY from app.state (set in main.py).
    """
    triton_endpoint: str = getattr(request.app.state, "triton_endpoint", "")
    triton_api_key: str = getattr(request.app.state, "triton_api_key", "")

    if not triton_endpoint:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="TRITON_ENDPOINT is not configured for OCR service",
        )

    triton_client = TritonClient(triton_endpoint, triton_api_key or None)
    return OCRService(triton_client=triton_client)


@inference_router.post(
    "/inference",
    response_model=OCRInferenceResponse,
    summary="Perform batch OCR inference",
    description="Run OCR on one or more images using Surya OCR via Triton.",
)
async def run_inference(
    request_body: OCRInferenceRequest,
    http_request: Request,
    ocr_service: OCRService = Depends(get_ocr_service),
) -> OCRInferenceResponse:
    """
    Run OCR inference for a batch of images.
    """
    try:
        # Extract auth context from request.state (if middleware is configured)
        user_id = getattr(http_request.state, "user_id", None)
        api_key_id = getattr(http_request.state, "api_key_id", None)
        session_id = getattr(http_request.state, "session_id", None)

        logger.info(
            "Processing OCR inference request with %d image(s), user_id=%s api_key_id=%s session_id=%s",
            len(request_body.image),
            user_id,
            api_key_id,
            session_id,
        )

        # Run inference (Triton + Surya OCR)
        response = ocr_service.run_inference(request_body)
        logger.info("OCR inference completed successfully")
        return response

    except ValueError as exc:
        logger.warning("Validation error in OCR inference: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except TritonInferenceError as exc:
        logger.error("OCR Triton inference failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OCR service temporarily unavailable",
        ) from exc
    except Exception as exc:  # pragma: no cover - generic error path
        logger.error("OCR inference failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from exc


