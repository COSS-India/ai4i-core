"""
Inference router for Language Diarization service.

Exposes a ULCA-style language diarization inference endpoint:
- POST /api/v1/language-diarization/inference
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from models.language_diarization_request import LanguageDiarizationInferenceRequest
from models.language_diarization_response import LanguageDiarizationInferenceResponse
from repositories.language_diarization_repository import LanguageDiarizationRepository, get_db_session
from services.language_diarization_service import LanguageDiarizationService
from utils.triton_client import TritonClient, TritonInferenceError
from middleware.auth_provider import AuthProvider

logger = logging.getLogger(__name__)

inference_router = APIRouter(
    prefix="/api/v1/language-diarization",
    tags=["Language Diarization Inference"],
    dependencies=[Depends(AuthProvider)]  # Enforce auth and permission checks on all routes
)


async def get_language_diarization_service(
    request: Request,
    db: AsyncSession = Depends(get_db_session)
) -> LanguageDiarizationService:
    """
    Dependency to construct LanguageDiarizationService with configured Triton client and repository.

    REQUIRES Model Management database resolution - no environment variable fallback.
    Request must include config.serviceId for Model Management to resolve endpoint and model.
    """
    triton_endpoint: str = getattr(request.state, "triton_endpoint", None)
    triton_api_key: str = getattr(request.app.state, "triton_api_key", "")
    triton_timeout: float = getattr(request.app.state, "triton_timeout", 300.0)

    if not triton_endpoint:
        service_id = getattr(request.state, "service_id", None)
        model_mgmt_error = getattr(request.state, "model_management_error", None)
        
        if service_id:
            error_detail = (
                f"Model Management failed to resolve Triton endpoint for serviceId: {service_id}. "
                f"Please ensure the service is registered in Model Management database."
            )
            if model_mgmt_error:
                error_detail += f" Error: {model_mgmt_error}"
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_detail,
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Request must include config.serviceId. "
                "Language Diarization service requires Model Management database resolution."
            ),
        )

    logger.info(
        "Using Triton endpoint=%s for serviceId=%s from Model Management",
        triton_endpoint,
        getattr(request.state, "service_id", "unknown"),
    )

    triton_client = TritonClient(triton_endpoint, triton_api_key or None, triton_timeout)
    repository = LanguageDiarizationRepository(db)
    return LanguageDiarizationService(triton_client=triton_client, repository=repository)


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
        response = await language_diarization_service.run_inference(
            request_body,
            user_id=user_id,
            api_key_id=api_key_id,
            session_id=session_id
        )
        logger.info("Language Diarization inference completed successfully")
        return response

    except ValueError as exc:
        logger.warning("Validation error in Language Diarization inference: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except TritonInferenceError as exc:
        service_id = getattr(http_request.state, "service_id", None)
        triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
        error_detail = str(exc)
        
        # Include model management context in error message
        if service_id and triton_endpoint:
            error_detail = (
                f"Triton inference failed for serviceId '{service_id}' at endpoint '{triton_endpoint}': {error_detail}. "
                "Please verify the model is registered in Model Management and the Triton server is accessible."
            )
        elif service_id:
            error_detail = (
                f"Triton inference failed for serviceId '{service_id}': {error_detail}. "
                "Model Management resolved the serviceId but Triton endpoint may be misconfigured."
            )
        else:
            error_detail = (
                f"Triton inference failed: {error_detail}. "
                "Please ensure config.serviceId is provided and the service is registered in Model Management."
            )
        
        logger.error("Language Diarization Triton inference failed: %s (serviceId=%s, endpoint=%s)", 
                    exc, service_id, triton_endpoint)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error_detail,
        ) from exc
    except Exception as exc:  # pragma: no cover - generic error path
        logger.error("Language Diarization inference failed: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        ) from exc

