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
from middleware.auth_provider import AuthProvider
from middleware.auth_provider import AuthProvider

logger = logging.getLogger(__name__)

inference_router = APIRouter(
    prefix="/api/v1/ner",
    tags=["NER Inference"],
    dependencies=[Depends(AuthProvider)]  # Enforce auth and permission checks on all routes
)


def get_ner_service(request: Request) -> NerService:
    """
    Dependency to construct NerService with configured Triton client.

    REQUIRES Model Management database resolution - no environment variable fallback.
    Request must include config.serviceId for Model Management to resolve endpoint and model.
    """
    # Get middleware-resolved endpoint from Model Management database
    triton_endpoint = getattr(request.state, "triton_endpoint", None)
    triton_api_key = getattr(request.app.state, "triton_api_key", "")
    
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
                "NER service requires Model Management database resolution."
            ),
        )
    
    # Get resolved model name from middleware (MUST be resolved by Model Management)
    model_name = getattr(request.state, "triton_model_name", None)
    
    if not model_name or model_name == "unknown":
        service_id = getattr(request.state, "service_id", None)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                f"Model Management failed to resolve Triton model name for serviceId: {service_id}. "
                f"Please ensure the model is properly configured in Model Management database with inference endpoint schema."
            ),
        )
    
    logger.info(
        f"Using endpoint={triton_endpoint} model_name={model_name} from Model Management "
        f"for serviceId={getattr(request.state, 'service_id', 'unknown')}"
    )
    
    # Create NER-specific TritonClient (has NER-specific methods like get_ner_io_for_triton)
    triton_client = TritonClient(triton_endpoint, triton_api_key or None)
    return NerService(triton_client=triton_client, model_name=model_name)


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
    
    The Model Resolution Middleware automatically resolves serviceId from
    request_body.config.serviceId to triton_endpoint and model_name,
    which are available in http_request.state.
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
        service_id = getattr(http_request.state, "service_id", None)
        triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
        model_name = getattr(http_request.state, "triton_model_name", None)
        
        error_detail = (
            f"NER inference failed for serviceId '{service_id}' "
            f"at endpoint '{triton_endpoint}' with model '{model_name}': {str(exc)}. "
            "Please verify the model is registered in Model Management and the Triton server is accessible."
        )
        
        logger.error(
            "NER Triton inference failed: %s (serviceId=%s, endpoint=%s, model=%s)",
            exc, service_id, triton_endpoint, model_name
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=error_detail,
        ) from exc
    except Exception as exc:  # pragma: no cover - generic error path
        service_id = getattr(http_request.state, "service_id", None)
        triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
        error_detail = str(exc)
        
        # Include model management context in error message
        if service_id and triton_endpoint:
            error_detail = (
                f"NER inference failed for serviceId '{service_id}' at endpoint '{triton_endpoint}': {error_detail}. "
                "Please verify the model is registered in Model Management and the Triton server is accessible."
            )
        elif service_id:
            error_detail = (
                f"NER inference failed for serviceId '{service_id}': {error_detail}. "
                "Model Management resolved the serviceId but Triton endpoint may be misconfigured."
            )
        else:
            error_detail = (
                f"NER inference failed: {error_detail}. "
                "Please ensure config.serviceId is provided and the service is registered in Model Management."
            )
        
        logger.error(
            "NER inference failed: %s (serviceId=%s, endpoint=%s)",
            exc, service_id, triton_endpoint, exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_detail,
        ) from exc



