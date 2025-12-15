"""
Inference router for NER service.

Exposes a ULCA-style NER inference endpoint:
- POST /api/v1/ner/inference
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, Request, status

from models.ner_request import NerInferenceRequest
from models.ner_response import NerInferenceResponse
from services.ner_service import NerService, TritonInferenceError
from utils.triton_client import TritonClient
from ai4icore_auth import AuthProvider

logger = logging.getLogger(__name__)

inference_router = APIRouter(
    prefix="/api/v1/ner",
    tags=["NER Inference"],
    dependencies=[Depends(AuthProvider)]  # Enforce auth and permission checks on all routes
)


def get_ner_service(request: Request) -> NerService:
    """
    Dependency to construct NerService with configured Triton client.

    Uses TRITON_ENDPOINT and TRITON_API_KEY from app.state (set in main.py).
    """
    triton_endpoint: str = getattr(request.app.state, "triton_endpoint", "")
    triton_api_key: str = getattr(request.app.state, "triton_api_key", "")

    if not triton_endpoint:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="TRITON_ENDPOINT is not configured for NER service",
        )

    triton_client = TritonClient(triton_endpoint, triton_api_key or None)
    return NerService(triton_client=triton_client)


@inference_router.post(
    "/inference",
    response_model=NerInferenceResponse,
    summary="Perform batch NER inference",
    description="Run NER on one or more text inputs using Dhruva NER via Triton.",
)
async def run_inference(
    request_body: NerInferenceRequest,
    http_request: Request,
    ner_service: NerService = Depends(get_ner_service),
) -> NerInferenceResponse:
    """
    Run NER inference for a batch of text inputs.
    """
    try:
        # Extract auth context from request.state (if middleware is configured)
        user_id = getattr(http_request.state, "user_id", None)
        api_key_id = getattr(http_request.state, "api_key_id", None)
        session_id = getattr(http_request.state, "session_id", None)

        logger.info(
            "Processing NER inference request with %d text input(s), "
            "user_id=%s api_key_id=%s session_id=%s",
            len(request_body.input),
            user_id,
            api_key_id,
            session_id,
        )

        response = ner_service.run_inference(request_body)
        logger.info("NER inference completed successfully")
        return response

    except ValueError as exc:
        logger.warning("Validation error in NER inference: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except TritonInferenceError as exc:
        logger.error("NER Triton inference failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="NER service temporarily unavailable",
        ) from exc
    except Exception as exc:  # pragma: no cover - generic error path
        logger.error("NER inference failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from exc



