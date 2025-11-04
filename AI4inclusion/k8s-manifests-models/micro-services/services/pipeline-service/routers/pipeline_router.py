"""
Pipeline injector for Pipeline Service

FastAPI router for pipeline inference endpoints.
"""

import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Request
from models.pipeline_request import PipelineInferenceRequest
from models.pipeline_response import PipelineInferenceResponse
from services.pipeline_service import PipelineService
from utils.http_client import ServiceClient

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
    try:
        # Extract API key from request headers
        api_key = None
        auth_header = http_request.headers.get('Authorization')
        if auth_header:
            api_key = auth_header.replace('Bearer ', '').replace('ApiKey ', '')
        
        # Get pipeline service
        pipeline_service = get_pipeline_service()
        
        # Execute pipeline
        response = await pipeline_service.run_pipeline_inference(
            request=request,
            api_key=api_key
        )
        
        logger.info("Pipeline inference completed successfully")
        return response
        
    except ValueError as e:
        logger.warning(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    
    except Exception as e:
        logger.error(f"Pipeline inference failed: {e}")
        raise HTTPException(status_code=500, detail=f"Pipeline inference failed: {str(e)}")


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
