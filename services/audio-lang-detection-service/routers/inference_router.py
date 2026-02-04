"""
Inference router for Audio Language Detection service.

Exposes a ULCA-style audio language detection inference endpoint:
- POST /api/v1/audio-lang-detection/inference
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from ai4icore_logging import get_correlation_id
from sqlalchemy.ext.asyncio import AsyncSession

from models.audio_lang_detection_request import AudioLangDetectionInferenceRequest
from models.audio_lang_detection_response import AudioLangDetectionInferenceResponse
from repositories.audio_lang_detection_repository import AudioLangDetectionRepository
from services.audio_lang_detection_service import AudioLangDetectionService
from utils.triton_client import TritonClient, TritonInferenceError
from middleware.auth_provider import AuthProvider
from middleware.tenant_db_dependency import get_tenant_db_session

logger = logging.getLogger(__name__)
# Use service name to get the same tracer instance as main.py
tracer = trace.get_tracer("audio-lang-detection-service")

inference_router = APIRouter(
    prefix="/api/v1/audio-lang-detection",
    tags=["Audio Language Detection Inference"],
    dependencies=[Depends(AuthProvider)]  # Enforce auth and permission checks on all routes
)


async def get_audio_lang_detection_service(
    request: Request,
    db: AsyncSession = Depends(get_tenant_db_session)
) -> AudioLangDetectionService:
    """
    Dependency to construct AudioLangDetectionService with configured Triton client and repository.

    REQUIRES Model Management database resolution - no environment variable fallback.
    Request must include config.serviceId for Model Management to resolve endpoint and model.
    
    The db session is tenant-aware:
    - For tenant users: routes to tenant-specific schema in multi_tenant_db
    - For normal users: uses shared auth_db tables
    """
    # Log tenant context if available (set by tenant middleware/JWT)
    tenant_id = getattr(request.state, "tenant_id", None)
    tenant_schema = getattr(request.state, "tenant_schema", None)
    if tenant_id:
        logger.info(f"Audio Lang Detection request with tenant context: tenant_id={tenant_id}, schema={tenant_schema}")
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
                "Audio Language Detection service requires Model Management database resolution."
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
        "Using Triton endpoint=%s model_name=%s for serviceId=%s from Model Management",
        triton_endpoint,
        model_name,
        getattr(request.state, "service_id", "unknown"),
    )

    triton_client = TritonClient(triton_endpoint, triton_api_key or None, triton_timeout, model_name=model_name)
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
    # Create a span for the entire inference operation
    # This will be a child of the FastAPI auto-instrumented span
    if not tracer:
        # Fallback if tracing not available
        return await _run_inference_impl(request_body, http_request, audio_lang_detection_service)
    
    with tracer.start_as_current_span("audio-lang-detection.inference") as span:
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
            span.set_attribute("audio-lang-detection.audio_count", len(request_body.audio))
            span.set_attribute("audio-lang-detection.service_id", request_body.config.serviceId if request_body.config else "unknown")
            
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
            span.add_event("audio-lang-detection.inference.started", {
                "audio_count": len(request_body.audio),
                "service_id": request_body.config.serviceId if request_body.config else "unknown"
            })

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
            
            # Add response metadata
            span.set_attribute("audio-lang-detection.output_count", len(response.output))
            span.set_attribute("http.status_code", 200)
            
            # Track response size (approximate)
            try:
                import json
                response_size = len(json.dumps(response.dict()).encode('utf-8'))
                span.set_attribute("http.response.size_bytes", response_size)
            except Exception:
                pass
            
            # Add span event for successful completion
            span.add_event("audio-lang-detection.inference.completed", {
                "output_count": len(response.output),
                "status": "success"
            })
            span.set_status(Status(StatusCode.OK))
            logger.info("Audio Language Detection inference completed successfully")
            return response

        except ValueError as exc:
            span.set_attribute("error", True)
            span.set_attribute("error.type", "ValueError")
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", 400)
            span.add_event("audio-lang-detection.inference.failed", {
                "error_type": "ValueError",
                "error_message": str(exc)
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            logger.warning("Validation error in Audio Language Detection inference: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        except TritonInferenceError as exc:
            span.set_attribute("error", True)
            span.set_attribute("error.type", "TritonInferenceError")
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", 503)
            span.add_event("audio-lang-detection.inference.failed", {
                "error_type": "TritonInferenceError",
                "error_message": str(exc)
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            service_id = getattr(http_request.state, "service_id", None)
            triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
            model_name = getattr(http_request.state, "triton_model_name", None)
            
            error_detail = (
                f"Audio Language Detection inference failed for serviceId '{service_id}' "
                f"at endpoint '{triton_endpoint}' with model '{model_name}': {str(exc)}. "
                "Please verify the model is registered in Model Management and the Triton server is accessible."
            )
            
            logger.error(
                "Audio Language Detection Triton inference failed: %s (serviceId=%s, endpoint=%s, model=%s)",
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
            span.add_event("audio-lang-detection.inference.failed", {
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
                    f"Audio Language Detection inference failed for serviceId '{service_id}' at endpoint '{triton_endpoint}': {error_detail}. "
                    "Please verify the model is registered in Model Management and the Triton server is accessible."
                )
            elif service_id:
                error_detail = (
                    f"Audio Language Detection inference failed for serviceId '{service_id}': {error_detail}. "
                    "Model Management resolved the serviceId but Triton endpoint may be misconfigured."
            )
            else:
                error_detail = (
                    f"Audio Language Detection inference failed: {error_detail}. "
                    "Please ensure config.serviceId is provided and the service is registered in Model Management."
                )
            
            logger.error(
                "Audio Language Detection inference failed: %s (serviceId=%s, endpoint=%s)",
                exc, service_id, triton_endpoint, exc_info=True
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_detail,
            ) from exc


async def _run_inference_impl(
    request_body: AudioLangDetectionInferenceRequest,
    http_request: Request,
    audio_lang_detection_service: AudioLangDetectionService,
) -> AudioLangDetectionInferenceResponse:
    """Fallback implementation when tracing is not available."""
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

    response = await audio_lang_detection_service.run_inference(
        request_body,
        user_id=user_id,
        api_key_id=api_key_id,
        session_id=session_id
    )
    logger.info("Audio Language Detection inference completed successfully")
    return response

