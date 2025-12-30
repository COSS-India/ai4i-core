"""
Inference router for NER service.

Exposes a ULCA-style NER inference endpoint:
- POST /api/v1/ner/inference
"""

import logging
from typing import Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status

from models.ner_request import NerInferenceRequest
from models.ner_response import NerInferenceResponse
from services.ner_service import NerService, TritonInferenceError, ModelManagementError
from ai4icore_model_management import ModelManagementClient
from middleware.auth_provider import AuthProvider

logger = logging.getLogger(__name__)

inference_router = APIRouter(
    prefix="/api/v1/ner",
    tags=["NER Inference"],
    dependencies=[Depends(AuthProvider)]  # Enforce auth and permission checks on all routes
)


def get_ner_service(request: Request) -> NerService:
    """
    Dependency to construct NerService with Model Management Client.

    Model configuration is fetched from Model Management Service at runtime.
    """
    model_management_client: Optional[ModelManagementClient] = getattr(
        request.app.state, "model_management_client", None
    )

    if not model_management_client:
        logger.error("Model Management Client is not initialized in app.state")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Model Management Client is not configured. "
                "Please ensure MODEL_MANAGEMENT_SERVICE_URL is set and the service is running."
            ),
        )

    redis_client = getattr(request.app.state, "redis_client", None)
    
    return NerService(
        model_management_client=model_management_client,
        redis_client=redis_client
    )


def get_auth_headers(request: Request) -> Dict[str, str]:
    """
    Extract authentication headers from request to forward to model management service.
    
    Returns:
        Dictionary of auth headers (Authorization, X-API-Key, X-Auth-Source)
    """
    auth_headers: Dict[str, str] = {}
    
    # Extract Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header:
        auth_headers["Authorization"] = auth_header
    
    # Extract X-API-Key header
    api_key = request.headers.get("X-API-Key")
    if api_key:
        auth_headers["X-API-Key"] = api_key
    
    # Extract X-Auth-Source header
    auth_source = request.headers.get("X-Auth-Source")
    if auth_source:
        auth_headers["X-Auth-Source"] = auth_source
    
    return auth_headers


@inference_router.post(
    "/inference",
    response_model=NerInferenceResponse,
    summary="Perform batch NER inference",
    description="Run NER on one or more text inputs using models configured in Model Management Service.",
)
async def run_inference(
    request_body: NerInferenceRequest,
    http_request: Request,
    ner_service: NerService = Depends(get_ner_service),
) -> NerInferenceResponse:
    """
    Run NER inference for a batch of text inputs.
    
    The serviceId in request.config must correspond to a service registered in
    Model Management Service. Model configuration (endpoint, model name) is
    fetched dynamically from Model Management Service.
    """
    try:
        # Extract auth context from request.state (if middleware is configured)
        user_id = getattr(http_request.state, "user_id", None)
        api_key_id = getattr(http_request.state, "api_key_id", None)
        session_id = getattr(http_request.state, "session_id", None)
        
        service_id = request_body.config.serviceId if request_body.config else None

        logger.info(
            "Processing NER inference request with %d text input(s), "
            "serviceId=%s, user_id=%s api_key_id=%s session_id=%s",
            len(request_body.input),
            service_id,
            user_id,
            api_key_id,
            session_id,
        )

        # Extract auth headers to forward to model management service
        auth_headers = get_auth_headers(http_request)

        response = await ner_service.run_inference(
            request=request_body,
            auth_headers=auth_headers if auth_headers else None
        )
        logger.info("NER inference completed successfully for serviceId=%s", service_id)
        return response

    except ValueError as exc:
        error_msg = str(exc)
        logger.warning("Validation error in NER inference: %s", error_msg)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid request: {error_msg}",
        ) from exc
    except ModelManagementError as exc:
        error_msg = str(exc)
        logger.error("Model Management error in NER inference: %s", error_msg)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                f"Failed to fetch model configuration from Model Management Service: {error_msg}. "
                f"Please verify the serviceId is correct and the service is registered."
            ),
        ) from exc
    except TritonInferenceError as exc:
        error_msg = str(exc)
        logger.error("NER Triton inference failed: %s", error_msg)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"NER inference service temporarily unavailable: {error_msg}. "
                f"Please check if the Triton server is running and accessible."
            ),
        ) from exc
    except Exception as exc:  # pragma: no cover - generic error path
        error_msg = str(exc)
        logger.error("NER inference failed with unexpected error: %s", error_msg, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error during NER inference: {error_msg}",
        ) from exc



