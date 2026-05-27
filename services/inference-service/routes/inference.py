"""
Main inference router with unified /inference endpoint.
Handles all inference requests regardless of task type.
Integrates orchestration, factory, and telemetry.
"""

import logging
import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Request, HTTPException, Depends

from orchestrator import Orchestrator, OrchestratorError
from models.common import GenericInferenceRequest, GenericInferenceResponse
from models.task_types import task_registry


logger = logging.getLogger(__name__)
router = APIRouter(tags=["inference"])


class InferenceRouterError(Exception):
    """Base exception for routing errors."""

    pass


async def get_orchestrator() -> Orchestrator:
    """
    Dependency for Orchestrator instance.
    Can be overridden in tests.
    """
    return Orchestrator()


async def handle_orchestrated_inference(
    payload: Dict[str, Any],
    orchestrator: Orchestrator,
    *,
    default_task_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Shared handler for inference routes that delegate to the orchestrator.

    Handles timing, logging, optional default task_type injection, orchestrator
    routing, and HTTP error mapping. Reuse from unified and task-specific
    endpoints (e.g. /inference vs /nmt/inference).

    Args:
        payload: Raw request payload dictionary
        orchestrator: Orchestrator instance (dependency-injected)
        default_task_type: Applied when task_type is missing from payload

    Returns:
        GenericInferenceResponse-compatible dict with task-specific output

    Raises:
        HTTPException: If request validation or execution fails
    """
    start_time = time.time()

    try:
        task_type = payload.get("task_type", "").upper()
        if not task_type and default_task_type:
            task_type = default_task_type.upper()
            request_payload = payload.copy()
            request_payload["task_type"] = task_type
        else:
            request_payload = payload

        logger.info(f"Inference request: task_type={task_type}")

        result = await orchestrator.route_inference(payload=request_payload)

        duration_ms = (time.time() - start_time) * 1000
        logger.info(
            f"✓ Inference completed: task_type={task_type}, duration_ms={duration_ms:.2f}ms"
        )
        return result

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(
            f"✗ Inference failed: {str(e)}, duration_ms={duration_ms:.2f}ms"
        )
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/inference",
    response_model=GenericInferenceResponse,
    summary="Unified Inference Endpoint",
    description="Route inference requests to appropriate TaskService based on task_type",
)
async def run_inference(
    payload: Dict[str, Any],
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> Dict[str, Any]:
    """
    Unified inference endpoint accepting requests for all task types.
    Routes to appropriate TaskService via Orchestrator.

    Request payload structure:
    {
        "task_type": "NMT|ASR|OCR|NER|LLM|...",
        "input"|"audio"|"image": [...],  # Polymorphic input array
        "config": {...},                  # Task-specific config
        "control_config": {...}          # Optional control parameters
    }

    Response payload structure:
    {
        "output": [...],                  # Task-specific output
        "config": {...},                  # Optional response metadata
        "smr_response": {...}            # Optional SMR routing metadata
    }

    Args:
        payload: Raw request payload dictionary
        orchestrator: Orchestrator instance (dependency-injected)

    Returns:
        GenericInferenceResponse with task-specific output

    Raises:
        HTTPException: If request validation or execution fails
    """
    return await handle_orchestrated_inference(payload, orchestrator)


@router.post(
    "/nmt/inference",
    response_model=GenericInferenceResponse,
    summary="NMT Inference Endpoint",
    description="Route inference requests to NMT TaskService",
)
async def run_nmt_inference(
    payload: Dict[str, Any],
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> Dict[str, Any]:
    """
    Dedicated endpoint for NMT inference requests.
    Routes to NMT TaskService via Orchestrator.

    Args:
        payload: Raw request payload dictionary
        orchestrator: Orchestrator instance (dependency-injected)   
    Returns:
        GenericInferenceResponse with NMT output    
    Raises:
        HTTPException: If request validation or execution fails
    """
    return await handle_orchestrated_inference(
        payload, orchestrator, default_task_type="NMT"
    )


@router.get(
    "/inference/health",
    summary="Health Check",
    description="Check if inference service is healthy",
)
async def health_check() -> Dict[str, str]:
    """
    Health check endpoint for inference service.
    Verifies service availability and dependencies.

    Returns:
        Dict with status and message
    """
    return {"status": "healthy", "message": "Inference service is operational"}


@router.get(
    "/inference/tasks",
    summary="List Available Tasks",
    description="Get list of supported inference task types",
)
async def list_available_tasks(
) -> Dict[str, list]:
    """
    List all available inference task types.
    Useful for clients to discover supported services.

    Args:

    Returns:
        Dict with list of available task types
    """
    return {"tasks": ["NMT", "ASR", "OCR", "NER", "LLM", "TTS", "PII", "LANGUAGE_DETECTION", "SPEAKER_DIARIZATION", "LANGUAGE_DIARIZATION", "TRANSLITERATION", "AUDIO_LANGUAGE_DETECTION", "SMR"]}

async def get_task_info(
    task_type: str,
) -> Dict[str, Any]:
    """
    Get detailed information about a specific task type.
    Returns request/response schema information.

    Args:
        task_type: Task type to get information for

    Returns:
        Dict with task schema information

    Raises:
        HTTPException: If task type not found
    """
    return {
        "task_type": task_type,
        "status": "supported",
        "description": f"Inference service for {task_type} task"
    }


async def _log_request_start(
    task_type: str,
    user_context: Dict[str, Any],
    session_id: Optional[str],
) -> None:
    """
    Log start of inference request.

    Args:
        task_type: Task type being processed
        user_context: User context from request
        session_id: Optional session ID
    """
    logger.info(f"Starting {task_type} inference request (session: {session_id})")


async def _log_request_complete(
    task_type: str,
    session_id: Optional[str],
    duration_ms: float,
    success: bool,
    error_msg: Optional[str] = None,
) -> None:
    """
    Log completion of inference request.

    Args:
        task_type: Task type that was processed
        session_id: Optional session ID
        duration_ms: Request duration in milliseconds
        success: Whether request succeeded
        error_msg: Optional error message if failed
    """
    status = "✓ SUCCESS" if success else "✗ FAILED"
    logger.info(f"{status} {task_type} inference (session: {session_id}, duration: {duration_ms:.2f}ms)")
    if error_msg:
        logger.error(f"  Error: {error_msg}")


async def _create_telemetry_context(
    task_type: str,
    user_context: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Create telemetry context for request tracing.
    Sets up parent span for orchestration and child spans for tasks.

    Args:
        task_type: Task type being processed
        user_context: User context from request

    Returns:
        Dict with telemetry context
    """
    return {
        "task_type": task_type,
        "user_id": user_context.get("user_id"),
        "session_id": user_context.get("session_id")
    }


async def _get_user_id_from_context(user_context: Dict[str, Any]) -> Optional[int]:
    """Extract user_id from user context."""
    user_id = user_context.get("user_id")
    return int(user_id) if user_id else None


async def _get_api_key_id_from_context(user_context: Dict[str, Any]) -> Optional[int]:
    """Extract api_key_id from user context."""
    api_key_id = user_context.get("api_key_id")
    return int(api_key_id) if api_key_id else None


async def _get_session_id_from_context(user_context: Dict[str, Any]) -> Optional[str]:
    """Extract session_id from user context."""
    return user_context.get("session_id")


async def _handle_http_error(
    error: Exception,
    task_type: str,
    session_id: Optional[str],
) -> HTTPException:
    """
    Convert internal exceptions to HTTP exceptions.

    Args:
        error: Internal exception
        task_type: Task type being processed
        session_id: Optional session ID

    Returns:
        HTTPException for HTTP response
    """
    error_msg = str(error)
    logger.error(f"Error in {task_type} inference (session: {session_id}): {error_msg}")
    return HTTPException(status_code=400, detail=error_msg)
