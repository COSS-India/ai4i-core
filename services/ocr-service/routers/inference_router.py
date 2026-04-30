"""
Inference router for OCR service.

Exposes a ULCA-style OCR inference endpoint:
- POST /api/v1/ocr/inference
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from ai4icore_logging import get_correlation_id

from models.ocr_request import OCRInferenceRequest
from models.ocr_response import OCRInferenceResponse
from services.ocr_service import OCRService
from repositories.ocr_repository import OCRRepository, get_db_session
from utils.triton_client import TritonClient, TritonInferenceError
from middleware.auth_provider import AuthProvider
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)
# Use service name to get the same tracer instance as main.py
tracer = trace.get_tracer("ocr-service")

inference_router = APIRouter(
    prefix="/api/v1/ocr",
    tags=["OCR Inference"],
    dependencies=[Depends(AuthProvider)]  # Enforce auth and permission checks on all routes
)


async def get_ocr_service(
    request: Request,
    db: AsyncSession = Depends(get_db_session)
) -> OCRService:
    """
    Dependency to construct OCRService with configured Triton client and repository.

    REQUIRES Model Management database resolution - no environment variable fallback.
    Request must include config.serviceId for Model Management to resolve endpoint and model.
    """
    repository = OCRRepository(db)
    
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
                "OCR service requires Model Management database resolution."
            ),
        )
    
    # Get resolved model name from middleware (MUST be resolved by Model Management)
    model_name = getattr(request.state, "triton_model_name", None)
    
    if not model_name or model_name == "unknown":
        service_id = getattr(request.state, "service_id", None)
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
                "OCR service requires Model Management database resolution."
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
    
    # Create OCR-specific TritonClient (has OCR-specific methods like run_ocr_batch)
    ocr_triton_client = TritonClient(triton_endpoint, triton_api_key or None, model_name=model_name)
    return OCRService(repository=repository, triton_client=ocr_triton_client, model_name=model_name)


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
    
    The Model Resolution Middleware automatically resolves serviceId from
    request_body.config.serviceId to triton_endpoint and model_name,
    which are available in http_request.state.
    """
    """
    Run OCR inference for a batch of images.
    
    The Model Resolution Middleware automatically resolves serviceId from
    request_body.config.serviceId to triton_endpoint and model_name,
    which are available in http_request.state.
    """
    """
    Run OCR inference for a batch of images.
    """
    # Create a span for the entire inference operation
    # This will be a child of the FastAPI auto-instrumented span
    if not tracer:
        # Fallback if tracing not available
        return await _run_inference_impl(request_body, http_request, ocr_service)
    
    with tracer.start_as_current_span("ocr.inference") as span:
        try:
            # Extract auth context from request.state (if middleware is configured)
            user_id = getattr(http_request.state, "user_id", None)
            api_key_id = getattr(http_request.state, "api_key_id", None)
            session_id = getattr(http_request.state, "session_id", None)
            
            # Get correlation ID for log/trace correlation
            correlation_id = get_correlation_id(http_request) or getattr(http_request.state, "correlation_id", None)
            if correlation_id:
                span.set_attribute("correlation.id", correlation_id)

            # Add request metadata to span
            span.set_attribute("ocr.image_count", len(request_body.image))
            span.set_attribute("ocr.service_id", request_body.config.serviceId if request_body.config else "unknown")
            span.set_attribute("ocr.source_language", request_body.config.language.sourceLanguage if request_body.config and request_body.config.language else "unknown")
            
            # Track request size (approximate)
            try:
                import json
                request_size = len(json.dumps(request_body.dict()).encode('utf-8'))
                span.set_attribute("http.request.size_bytes", request_size)
            except Exception:
                pass
            
            if user_id:
                span.set_attribute("user.id", str(user_id))
            if api_key_id:
                span.set_attribute("api_key.id", str(api_key_id))
            if session_id:
                span.set_attribute("session.id", str(session_id))
            
            # Add span event for request start
            span.add_event("ocr.inference.started", {
                "image_count": len(request_body.image),
                "service_id": request_body.config.serviceId if request_body.config else "unknown"
            })

            logger.info(
                "Processing OCR inference request with %d image(s), user_id=%s api_key_id=%s session_id=%s",
                len(request_body.image),
                user_id,
                api_key_id,
                session_id,
            )

            # Run inference (Triton + Surya OCR)
            response = await ocr_service.run_inference(
                request_body,
                user_id=user_id,
                api_key_id=api_key_id,
                session_id=session_id
            )
            
            # Add response metadata
            span.set_attribute("ocr.output_count", len(response.output))
            span.set_attribute("http.status_code", 200)
            
            # Track response size (approximate)
            try:
                import json
                response_size = len(json.dumps(response.dict()).encode('utf-8'))
                span.set_attribute("http.response.size_bytes", response_size)
            except Exception:
                pass
            
            # Add span event for successful completion
            span.add_event("ocr.inference.completed", {
                "output_count": len(response.output),
                "status": "success"
            })
            span.set_status(Status(StatusCode.OK))
            logger.info("OCR inference completed successfully")
            return response

        except ValueError as exc:
            span.set_attribute("error", True)
            span.set_attribute("error.type", "ValueError")
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", 400)
            span.add_event("ocr.inference.failed", {
                "error_type": "ValueError",
                "error_message": str(exc)
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            logger.warning("Validation error in OCR inference: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        except TritonInferenceError as exc:
            span.set_attribute("error", True)
            span.set_attribute("error.type", "TritonInferenceError")
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", 503)
            span.add_event("ocr.inference.failed", {
                "error_type": "TritonInferenceError",
                "error_message": str(exc)
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            service_id = getattr(http_request.state, "service_id", None)
            triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
            model_name = getattr(http_request.state, "triton_model_name", None)
            
            error_detail = (
                f"OCR inference failed for serviceId '{service_id}' "
                f"at endpoint '{triton_endpoint}' with model '{model_name}': {str(exc)}. "
                "Please verify the model is registered in Model Management and the Triton server is accessible."
            )
            
            logger.error(
                "OCR Triton inference failed: %s (serviceId=%s, endpoint=%s, model=%s)",
                exc, service_id, triton_endpoint, model_name
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=error_detail,
            ) from exc
        except Exception as exc:  # pragma: no cover - generic error path
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", 500)
            span.add_event("ocr.inference.failed", {
                "error_type": type(exc).__name__,
                "error_message": str(exc)
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            service_id = getattr(http_request.state, "service_id", None)
            triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
            error_detail = str(exc)
            
            # Include model management context in error message
            if service_id and triton_endpoint:
                error_detail = (
                    f"OCR inference failed for serviceId '{service_id}' at endpoint '{triton_endpoint}': {error_detail}. "
                    "Please verify the model is registered in Model Management and the Triton server is accessible."
                )
            elif service_id:
                error_detail = (
                    f"OCR inference failed for serviceId '{service_id}': {error_detail}. "
                    "Model Management resolved the serviceId but Triton endpoint may be misconfigured."
                )
            else:
                error_detail = (
                    f"OCR inference failed: {error_detail}. "
                    "Please ensure config.serviceId is provided and the service is registered in Model Management."
                )
            
            logger.error(
                "OCR inference failed: %s (serviceId=%s, endpoint=%s)",
                exc, service_id, triton_endpoint, exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_detail,
            ) from exc


async def _run_inference_impl(
    request_body: OCRInferenceRequest,
    http_request: Request,
    ocr_service: OCRService,
) -> OCRInferenceResponse:
    """Fallback implementation when tracing is not available."""
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

    response = await ocr_service.run_inference(
        request_body,
        user_id=user_id,
        api_key_id=api_key_id,
        session_id=session_id
    )
    logger.info("OCR inference completed successfully")
    return response


