"""
Pipeline router for Pipeline Service

FastAPI router for pipeline inference endpoints.
Includes distributed tracing for end-to-end observability.
"""

import logging
import time
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Request
from models.pipeline_request import PipelineInferenceRequest
from models.pipeline_response import PipelineInferenceResponse
from services.pipeline_service import PipelineService
from utils.http_client import ServiceClient
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
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False
    logging.warning("OpenTelemetry not available, tracing disabled in router")

logger = logging.getLogger(__name__)

# Create router
pipeline_router = APIRouter(
    prefix="/api/v1/pipeline",
    tags=["Pipeline"]
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
    
    Example: ASR → Translation → TTS for Speech-to-Speech translation
    """
    tracer = trace.get_tracer(__name__) if TRACING_AVAILABLE else None
    
    return await _execute_pipeline_request(request, http_request, tracer, None)


async def _execute_pipeline_request(
    request: PipelineInferenceRequest,
    http_request: Request,
    tracer,
    root_span
) -> PipelineInferenceResponse:
    """Internal pipeline request execution logic."""
    try:
        # Create span for authentication/authorization
        if tracer:
            with tracer.start_as_current_span("Pipeline Authentication") as auth_span:
                # Extract JWT token and API key from request headers
                jwt_token = None
                api_key = None
                
                auth_header = http_request.headers.get('Authorization')
                if auth_header and auth_header.startswith('Bearer '):
                    jwt_token = auth_header.replace('Bearer ', '')
                    auth_span.set_attribute("auth.jwt_present", True)
                else:
                    auth_span.set_attribute("auth.jwt_present", False)
                
                api_key_header = http_request.headers.get('X-API-Key')
                if api_key_header:
                    api_key = api_key_header
                    auth_span.set_attribute("auth.api_key_present", True)
                else:
                    auth_span.set_attribute("auth.api_key_present", False)
                
                # Add pipeline metadata to span
                auth_span.set_attribute("pipeline.task_count", len(request.pipelineTasks))
                auth_span.set_attribute("pipeline.task_types", ",".join([t.taskType.value for t in request.pipelineTasks]))
                
                logger.info(f"🔐 Authentication extracted: JWT={'present' if jwt_token else 'absent'}, API_KEY={'present' if api_key else 'absent'}")
            
            # Get pipeline service
            pipeline_service = get_pipeline_service()
            
            # Execute pipeline (this will create its own spans)
            response = await pipeline_service.run_pipeline_inference(
                request=request,
                jwt_token=jwt_token,
                api_key=api_key
            )
            
            logger.info("✅ Pipeline inference completed successfully")
            return response
        else:
            # No tracing, extract auth normally
            jwt_token = None
            api_key = None
            
            auth_header = http_request.headers.get('Authorization')
            if auth_header and auth_header.startswith('Bearer '):
                jwt_token = auth_header.replace('Bearer ', '')
            
            api_key_header = http_request.headers.get('X-API-Key')
            if api_key_header:
                api_key = api_key_header
            
            # Get pipeline service
            pipeline_service = get_pipeline_service()
            
            # Execute pipeline (this will create its own spans)
            response = await pipeline_service.run_pipeline_inference(
                request=request,
                jwt_token=jwt_token,
                api_key=api_key
            )
            
            logger.info("✅ Pipeline inference completed successfully")
            return response
        
    except (PipelineTaskError, ModelNotFoundError, ServiceUnavailableError) as e:
        # Handle pipeline-specific errors with structured response
        error_detail = ErrorDetail(
            message=e.message,
            code=e.error_code,
            timestamp=time.time()
        )
        
        # Add additional context to error detail
        error_dict = error_detail.dict()
        if e.task_index:
            error_dict["task_index"] = e.task_index
        if e.task_type:
            error_dict["task_type"] = e.task_type
        if e.service_error:
            error_dict["service_error"] = e.service_error
        
        logger.error(f"❌ Pipeline error [{e.error_code}]: {e.message}")
        
        # Record error in span if tracing is available
        if TRACING_AVAILABLE:
            current_span = trace.get_current_span()
            if current_span:
                current_span.set_attribute("error", True)
                current_span.set_attribute("error.code", e.error_code)
                current_span.set_attribute("error.message", e.message)
                current_span.set_attribute("error.type", type(e).__name__)
                if e.task_index:
                    current_span.set_attribute("error.task_index", e.task_index)
                if e.task_type:
                    current_span.set_attribute("error.task_type", e.task_type)
                if e.service_error:
                    for key, value in e.service_error.items():
                        current_span.set_attribute(f"error.service.{key}", str(value))
                current_span.record_exception(e)
        
        raise HTTPException(status_code=e.status_code, detail=error_dict)
    
    except ValueError as e:
        error_msg = f"Validation error: {e}"
        logger.warning(f"⚠️ {error_msg}")
        
        error_detail = ErrorDetail(
            message=error_msg,
            code="VALIDATION_ERROR",
            timestamp=time.time()
        )
        
        # Record error in span if tracing is available
        if TRACING_AVAILABLE:
            current_span = trace.get_current_span()
            if current_span:
                current_span.set_attribute("error", True)
                current_span.set_attribute("error.type", "ValueError")
                current_span.set_attribute("error.code", "VALIDATION_ERROR")
                current_span.set_attribute("error.message", str(e))
                current_span.record_exception(e)
        
        raise HTTPException(status_code=400, detail=error_detail.dict())
    
    except Exception as e:
        error_msg = f"Unexpected pipeline error: {e}"
        logger.error(f"❌ {error_msg}", exc_info=True)
        
        error_detail = ErrorDetail(
            message=error_msg,
            code="INTERNAL_ERROR",
            timestamp=time.time()
        )
        
        # Record error in span if tracing is available
        if TRACING_AVAILABLE:
            current_span = trace.get_current_span()
            if current_span:
                current_span.set_attribute("error", True)
                current_span.set_attribute("error.type", type(e).__name__)
                current_span.set_attribute("error.code", "INTERNAL_ERROR")
                current_span.set_attribute("error.message", str(e))
                current_span.record_exception(e)
        
        raise HTTPException(status_code=500, detail=error_detail.dict())


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
