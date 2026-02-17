"""
Inference router for Language Diarization service.

Exposes a ULCA-style language diarization inference endpoint:
- POST /api/v1/language-diarization/inference
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

# OpenTelemetry imports
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    from ai4icore_logging import get_correlation_id
    tracer = trace.get_tracer("language-diarization-service")
    TRACING_AVAILABLE = True
except ImportError:
    tracer = None
    TRACING_AVAILABLE = False
    def get_correlation_id(request):
        return None

from models.language_diarization_request import LanguageDiarizationInferenceRequest
from models.language_diarization_response import LanguageDiarizationInferenceResponse
from repositories.language_diarization_repository import LanguageDiarizationRepository
from services.language_diarization_service import LanguageDiarizationService
from utils.triton_client import TritonClient, TritonInferenceError
from middleware.auth_provider import AuthProvider
from middleware.tenant_db_dependency import get_tenant_db_session

logger = logging.getLogger(__name__)

inference_router = APIRouter(
    prefix="/api/v1/language-diarization",
    tags=["Language Diarization Inference"],
    dependencies=[Depends(AuthProvider)]  # Enforce auth and permission checks on all routes
)


async def get_language_diarization_service(
    request: Request,
    db: AsyncSession = Depends(get_tenant_db_session)
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
    
    Creates detailed trace spans for the entire inference operation.
    """
    # Create a span for the entire inference operation
    if not tracer:
        # Fallback if tracing not available
        return await _run_inference_impl(request_body, http_request, language_diarization_service)
    
    with tracer.start_as_current_span("language_diarization.inference") as span:
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
            span.set_attribute("language_diarization.audio_count", len(request_body.audio))
            if request_body.config and request_body.config.serviceId:
                span.set_attribute("language_diarization.service_id", request_body.config.serviceId)
            
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
            span.add_event("language_diarization.inference.started", {
                "audio_count": len(request_body.audio),
                "service_id": request_body.config.serviceId if request_body.config else "unknown"
            })

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
            
            # Calculate response metrics (always, not just for span)
            response_size = 0
            total_segments = 0
            try:
                import json
                response_dict = response.dict()
                response_json = json.dumps(response_dict)
                response_size = len(response_json.encode('utf-8'))
                total_segments = sum(out.total_segments for out in response.output)
            except Exception as e:
                logger.warning(f"Failed to calculate response metrics: {e}")
                total_segments = sum(out.total_segments for out in response.output)
            
            # Enhanced success logging (ALWAYS log this)
            logger.info(
                "✅ Language Diarization inference completed successfully - "
                "audio_count=%d output_count=%d total_segments=%d response_size=%d bytes user_id=%s api_key_id=%s",
                len(request_body.audio),
                len(response.output),
                total_segments,
                response_size,
                user_id,
                api_key_id
            )
            
            # Add response metadata to span
            span.set_attribute("language_diarization.output_count", len(response.output))
            span.set_attribute("http.status_code", 200)
            span.set_attribute("http.response.size_bytes", response_size)
            span.set_attribute("language_diarization.total_segments", total_segments)
            
            # Add response preview to span
            try:
                response_preview = response_json[:500] if response_size > 0 else ""
                span.set_attribute("http.response.preview", response_preview)
            except Exception:
                pass
            
            # Add span event for successful completion with detailed info
            completion_event_data = {
                "output_count": len(response.output),
                "status": "success",
                "http_status_code": 200,
                "total_segments": total_segments
            }
            
            # Add segment counts for each output
            for idx, out in enumerate(response.output):
                completion_event_data[f"output_{idx}_segments"] = out.total_segments
            
            span.add_event("language_diarization.inference.completed", completion_event_data)
            span.set_status(Status(StatusCode.OK))
            
            return response

        except ValueError as exc:
            import traceback
            tb_str = traceback.format_exc()
            
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", 400)
            span.set_attribute("error.stack_trace", tb_str[:1000])
            
            span.add_event("language_diarization.inference.failed", {
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "stack_trace_preview": tb_str[:500]
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            
            logger.warning(
                "⚠️ Validation error in Language Diarization inference - "
                "error=%s audio_count=%d user_id=%s\n"
                "Stack trace:\n%s",
                str(exc),
                len(request_body.audio),
                user_id,
                tb_str
            )
            
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        except TritonInferenceError as exc:
            import traceback
            tb_str = traceback.format_exc()
            
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", 503)
            span.set_attribute("error.stack_trace", tb_str[:1000])
            
            service_id = getattr(http_request.state, "service_id", None)
            triton_endpoint = getattr(http_request.state, "triton_endpoint", None)
            
            # Add detailed context to span event
            span.add_event("language_diarization.inference.failed", {
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "service_id": service_id or "unknown",
                "triton_endpoint": triton_endpoint or "unknown",
                "stack_trace_preview": tb_str[:500]
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            
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
            
            # Enhanced error logging with full context
            logger.error(
                "❌ Language Diarization Triton inference failed - "
                "error=%s service_id=%s endpoint=%s audio_count=%d user_id=%s api_key_id=%s\n"
                "Stack trace:\n%s", 
                str(exc),
                service_id,
                triton_endpoint,
                len(request_body.audio),
                user_id,
                api_key_id,
                tb_str
            )
            
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=error_detail,
            ) from exc
        except Exception as exc:  # pragma: no cover - generic error path
            import traceback
            tb_str = traceback.format_exc()
            
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", 500)
            span.set_attribute("error.stack_trace", tb_str[:1000])  # Truncate for span
            
            # Add detailed error event
            span.add_event("language_diarization.inference.failed", {
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "stack_trace_preview": tb_str[:500],
                "audio_count": len(request_body.audio),
                "service_id": request_body.config.serviceId if request_body.config else "unknown"
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            
            # Enhanced error logging
            logger.error(
                "❌ Language Diarization inference failed with unexpected error - "
                "error_type=%s error_message=%s audio_count=%d user_id=%s api_key_id=%s\n"
                "Stack trace:\n%s",
                type(exc).__name__,
                str(exc),
                len(request_body.audio),
                user_id,
                api_key_id,
                tb_str
            )
            
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error",
            ) from exc


async def _run_inference_impl(
    request_body: LanguageDiarizationInferenceRequest,
    http_request: Request,
    language_diarization_service: LanguageDiarizationService,
) -> LanguageDiarizationInferenceResponse:
    """Implementation of run_inference without tracing (fallback)"""
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
    
    # Calculate response metrics
    response_size = 0
    total_segments = 0
    try:
        import json
        response_dict = response.dict()
        response_json = json.dumps(response_dict)
        response_size = len(response_json.encode('utf-8'))
        total_segments = sum(out.total_segments for out in response.output)
    except Exception:
        total_segments = sum(out.total_segments for out in response.output)
    
    # Enhanced success logging
    logger.info(
        "✅ Language Diarization inference completed successfully - "
        "audio_count=%d output_count=%d total_segments=%d response_size=%d bytes user_id=%s api_key_id=%s",
        len(request_body.audio),
        len(response.output),
        total_segments,
        response_size,
        user_id,
        api_key_id
    )
    
    return response

