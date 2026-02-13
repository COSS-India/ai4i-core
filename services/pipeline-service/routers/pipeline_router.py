"""
Pipeline router for Pipeline Service

FastAPI router for pipeline inference endpoints.
Includes distributed tracing for end-to-end observability.
"""

import logging
import time
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Request, Depends
from models.pipeline_request import PipelineInferenceRequest
from models.pipeline_response import PipelineInferenceResponse
from services.pipeline_service import PipelineService
from utils.http_client import ServiceClient
from middleware.auth_provider import AuthProvider
from middleware.exceptions import (
    PipelineError,
    PipelineTaskError,
    ServiceUnavailableError,
    ModelNotFoundError,
    ErrorDetail
)

# Import OpenTelemetry for tracing
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode
    from ai4icore_logging import get_correlation_id
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False
    logging.warning("OpenTelemetry not available, tracing disabled in router")
    def get_correlation_id(request):
        return None

logger = logging.getLogger(__name__)
# Use service name to get the same tracer instance as main.py
tracer = trace.get_tracer("pipeline-service") if TRACING_AVAILABLE else None

# Create router
pipeline_router = APIRouter(
    prefix="/api/v1/pipeline",
    tags=["Pipeline"],
    dependencies=[Depends(AuthProvider)]  # Enforce auth and permission checks on all routes
)


def get_service_client() -> ServiceClient:
    """Dependency to get service client."""
    return ServiceClient()


def get_pipeline_service() -> PipelineService:
    """Dependency to get pipeline service instance."""
    service_client = get_service_client()
    return PipelineService(service_client)


@pipeline_router.post(
    "/inference",
    response_model=PipelineInferenceResponse,
    summary="Execute pipeline inference",
    description="Execute a multi-task AI pipeline (e.g., Speech-to-Speech translation)"
)
async def run_pipeline_inference(
    request: PipelineInferenceRequest,
    http_request: Request
) -> PipelineInferenceResponse:
    """
    Execute a pipeline of AI tasks.
    
    Creates detailed trace spans for the entire pipeline operation.
    Example: ASR → Translation → TTS for Speech-to-Speech translation
    """
    # Create a span for the entire pipeline operation
    # This will be a child of the FastAPI auto-instrumented span
    if not tracer:
        # Fallback if tracing not available
        return await _execute_pipeline_request(request, http_request, None, None)
    
    with tracer.start_as_current_span("pipeline.inference") as span:
        try:
            # Extract auth context from request.state (if middleware is configured)
            user_id = getattr(http_request.state, "user_id", None)
            api_key_id = getattr(http_request.state, "api_key_id", None)
            
            # Get correlation ID for log/trace correlation
            correlation_id = get_correlation_id(http_request) or getattr(http_request.state, "correlation_id", None)
            if correlation_id:
                span.set_attribute("correlation.id", correlation_id)
            
            # Add request metadata to span
            span.set_attribute("pipeline.task_count", len(request.pipelineTasks))
            task_types = [task.taskType.value for task in request.pipelineTasks]
            span.set_attribute("pipeline.task_types", ",".join(task_types))
            span.set_attribute("pipeline.has_input_data", hasattr(request, 'inputData') and request.inputData is not None)
            
            # Track request size (approximate)
            try:
                import json
                request_size = len(json.dumps(request.dict()).encode('utf-8'))
                span.set_attribute("http.request.size_bytes", request_size)
            except Exception:
                pass
            
            if user_id:
                span.set_attribute("user.id", str(user_id))
            if api_key_id:
                span.set_attribute("api_key.id", str(api_key_id))
            
            # Add span event for request start
            span.add_event("pipeline.inference.started", {
                "task_count": len(request.pipelineTasks),
                "task_types": ",".join(task_types)
            })
            
            logger.info(
                "Processing pipeline inference request with %d tasks, user_id=%s api_key_id=%s",
                len(request.pipelineTasks),
                user_id,
                api_key_id
            )
            
            # Execute pipeline
            response = await _execute_pipeline_request(request, http_request, tracer, span)
            
            # Add response metadata
            span.set_attribute("http.status_code", 200)
            span.set_attribute("pipeline.success", True)
            
            # Track response size (approximate)
            try:
                import json
                response_size = len(json.dumps(response.dict()).encode('utf-8'))
                span.set_attribute("http.response.size_bytes", response_size)
            except Exception:
                pass
            
            # Add span event for successful completion
            span.add_event("pipeline.inference.completed", {
                "status": "success",
                "task_count": len(request.pipelineTasks)
            })
            span.set_status(Status(StatusCode.OK))
            logger.info("Pipeline inference completed successfully")
            return response
            
        except (PipelineTaskError, ModelNotFoundError, ServiceUnavailableError) as exc:
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", 400)
            span.add_event("pipeline.inference.failed", {
                "error_type": type(exc).__name__,
                "error_message": str(exc)
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            logger.warning("Pipeline error: %s", exc)
            raise
            
        except Exception as exc:
            span.set_attribute("error", True)
            span.set_attribute("error.type", type(exc).__name__)
            span.set_attribute("error.message", str(exc))
            span.set_attribute("http.status_code", 500)
            span.add_event("pipeline.inference.exception", {
                "error_type": type(exc).__name__,
                "error_message": str(exc)
            })
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            logger.error("Unexpected error in pipeline inference: %s", exc, exc_info=True)
            raise


async def _execute_pipeline_request(
    request: PipelineInferenceRequest,
    http_request: Request,
    tracer,
    root_span
) -> PipelineInferenceResponse:
    """Internal pipeline request execution logic."""
    # Extract JWT token and API key from request headers
    jwt_token = None
    api_key = None
    
    auth_header = http_request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        jwt_token = auth_header.replace('Bearer ', '')
    
    api_key_header = http_request.headers.get('X-API-Key')
    if api_key_header:
        api_key = api_key_header
    
    # Extract user_id from request state (set by AuthProvider middleware)
    # This is needed for tenant routing in downstream services (ASR, NMT, TTS)
    user_id = getattr(http_request.state, "user_id", None)
    
    logger.info(f"🔐 Authentication extracted: JWT={'present' if jwt_token else 'absent'}, API_KEY={'present' if api_key else 'absent'}, USER_ID={user_id}")
    
    # Get pipeline service
    pipeline_service = get_pipeline_service()
    
    # Execute pipeline (this will create its own spans)
    response = await pipeline_service.run_pipeline_inference(
        request=request,
        jwt_token=jwt_token,
        api_key=api_key,
        user_id=user_id
    )
    
    logger.info("✅ Pipeline inference completed successfully")
    return response


@pipeline_router.get(
    "/info",
    summary="Pipeline service information",
    description="Get pipeline service capabilities and usage information"
)
async def get_pipeline_info() -> Dict[str, Any]:
    """Get pipeline service information."""
    return {
        "service": "pipeline-service",
        "version": "1.0.0",
        "description": "Multi-task AI pipeline orchestration service",
        "supported_task_types": ["asr", "translation", "tts", "transliteration"],
        "example_pipelines": {
            "speech_to_speech": {
                "description": "Full Speech-to-Speech translation pipeline",
                "tasks": [
                    {
                        "taskType": "asr",
                        "description": "Convert audio to text"
                    },
                    {
                        "taskType": "translation",
                        "description": "Translate text"
                    },
                    {
                        "taskType": "tts",
                        "description": "Convert text to speech"
                    }
                ]
            },
            "text_to_speech": {
                "description": "Text translation to speech pipeline",
                "tasks": [
                    {
                        "taskType": "translation",
                        "description": "Translate text"
                    },
                    {
                        "taskType": "tts",
                        "description": "Convert text to speech"
                    }
                ]
            }
        },
        "task_sequence_rules": {
            "asr": ["translation"],
            "translation": ["tts"],
            "transliteration": ["translation", "tts"]
        }
    }
