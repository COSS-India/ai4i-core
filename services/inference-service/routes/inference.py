"""
Main inference router with unified /inference endpoint.
Handles all inference requests regardless of task type.
Integrates orchestration, factory, and telemetry.
"""

import logging
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, Body, HTTPException, Depends, Request
from fastapi.responses import JSONResponse

from orchestrator import Orchestrator
from models.common import GenericInferenceResponse
from services.llm_service import OpenAIProxyService
from utils.http_client import ServiceCallError, ServiceNotFoundError
from inference.inference_server_resolver import (
    ServiceNotFoundError as ResolverServiceNotFoundError,
)


logger = logging.getLogger(__name__)
router = APIRouter(tags=["inference"])


_CHAT_EXAMPLE = {
    "model": "google/gemma-4-E4B-it",
    "messages": [{"role": "user", "content": "Hello!"}],
    "stream": False,
}


# Module-level singleton: a fresh Orchestrator per request would rebuild the
# InferenceServerResolver each time, so its in-memory service cache never got
# a hit and every request blocked on a live MMS lookup.
_orchestrator = Orchestrator()


async def get_orchestrator() -> Orchestrator:
    """
    Dependency for Orchestrator instance.
    Can be overridden in tests.
    """
    return _orchestrator


def _http_error_for(exc: Exception, task_type: str) -> HTTPException:
    """
    Map an orchestration failure to a client-safe HTTPException.

    Walks the exception __cause__ chain (orchestrator wraps with `from exc`)
    so the original error classifies the response:
      ValueError          → 400 (validation messages are user-facing by design)
      NotImplementedError               → 501 (unimplemented task, e.g. PII)
      ServiceNotFoundError              → 404 (unknown serviceId)
      RuntimeError                      → 502 (Triton / MMS dependency failed)
      anything else                     → 500

    Only validation messages are echoed to the client. Resolver and backend
    errors previously leaked internal endpoints via str(exc) — those now get
    a generic detail; the full chain is logged server-side by the caller.
    """
    chain = []
    cause: Optional[BaseException] = exc
    while cause is not None and len(chain) < 16:
        chain.append(cause)
        cause = cause.__cause__

    for e in chain:
        if isinstance(e, ValueError):
            return HTTPException(status_code=400, detail=str(e))
        if isinstance(e, NotImplementedError):
            return HTTPException(status_code=501, detail=str(e))
        if isinstance(e, (ServiceNotFoundError, ResolverServiceNotFoundError)):
            return HTTPException(
                status_code=404, detail=f"{task_type}: requested service not found"
            )
    for e in chain:
        if isinstance(e, (RuntimeError, ServiceCallError)):
            return HTTPException(
                status_code=502, detail=f"{task_type}: upstream inference dependency failed"
            )
    return HTTPException(status_code=500, detail=f"{task_type}: internal error")


async def _run_inference(
    request: Request,
    payload: Dict[str, Any],
    orchestrator: Orchestrator,
    default_task_type: Optional[str] = None,
    strip: Tuple[str, ...] = (),
) -> Dict[str, Any]:
    """
    Shared handler body for every inference route:
    default the task_type, route via the Orchestrator, strip response keys
    the endpoint contract excludes, and map failures to client-safe HTTP
    errors (full details logged server-side only).
    """
    # No manual timing here: the logging middleware records duration_ms for
    # every request, and the request span carries total_time_ms.
    if default_task_type and not payload.get("task_type"):
        payload = {**payload, "task_type": default_task_type}
    task_type = str(payload.get("task_type", "")).upper()
    logger.info(f"Inference request: task_type={task_type}")

    try:
        result = await orchestrator.route_inference(payload=payload, request=request)
    except Exception as exc:
        logger.error(f"Inference failed: task_type={task_type}", exc_info=True)
        raise _http_error_for(exc, task_type) from exc

    for key in strip:
        result.pop(key, None)
    return result


@router.post(
    "/inference",
    response_model=GenericInferenceResponse,
    summary="Unified Inference Endpoint",
    description="Route inference requests to appropriate TaskService based on task_type",
    openapi_extra={"requestBody": {"content": {"application/json": {"example": {
        "serviceId": "your-service-id",
        "task_type": "NMT",
        "input": [{"source": "hello world"}],
        "config": {"language": {"sourceLanguage": "en", "targetLanguage": "hi"}},
    }}}}},
)
async def run_inference(
    request: Request,
    payload: Dict[str, Any],
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> Dict[str, Any]:
    """
    Unified inference endpoint accepting requests for all task types.
    Routes to appropriate TaskService via Orchestrator.

    Request payload structure:
    {
        "task_type": "NMT|ASR|OCR|NER|...",
        "input"|"audio"|"image": [...],  # Polymorphic input array
        "config": {...},                  # Task-specific config
        "control_config": {...}          # Optional control parameters
    }
    """
    return await _run_inference(request, payload, orchestrator)


@router.post(
    "/nmt/inference",
    response_model=GenericInferenceResponse,
    response_model_exclude={"config"},
    summary="NMT Inference Endpoint",
    description="Route inference requests to NMT TaskService",
    openapi_extra={"requestBody": {"content": {"application/json": {"example": {
        "serviceId": "your-service-id",
        "input": [{"source": "hello world"}],
        "config": {"language": {"sourceLanguage": "en", "targetLanguage": "hi"}},
    }}}}},
)
async def run_nmt_inference(
    request: Request,
    payload: Dict[str, Any],
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> Dict[str, Any]:
    """Dedicated endpoint for NMT inference requests."""
    return await _run_inference(request, payload, orchestrator, default_task_type="NMT")


@router.post(
    "/ner/inference",
    response_model=None,
    summary="NER Inference Endpoint",
    description="Route inference requests to NER TaskService",
    openapi_extra={"requestBody": {"content": {"application/json": {"example": {
        "serviceId": "your-service-id",
        "input": [{"source": "John lives in New York"}],
        "config": {"language": {"sourceLanguage": "en"}},
    }}}}},
)
async def run_ner_inference(
    request: Request,
    payload: Dict[str, Any],
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> Dict[str, Any]:
    """Dedicated endpoint for NER inference requests."""
    return await _run_inference(
        request, payload, orchestrator,
        default_task_type="NER", strip=("smr_response", "elapsed_time_ms"),
    )


@router.post(
    "/transliteration/inference",
    response_model=GenericInferenceResponse,
    response_model_exclude={"config", "smr_response"},
    summary="TRANSLITERATION Inference Endpoint",
    description="Route inference requests to TRANSLITERATION TaskService",
    openapi_extra={"requestBody": {"content": {"application/json": {"example": {
        "serviceId": "your-service-id",
        "input": [{"source": "namaste"}],
        "config": {"language": {"sourceLanguage": "hi", "targetLanguage": "en"}},
    }}}}},
)
async def run_transliteration_inference(
    request: Request,
    payload: Dict[str, Any],
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> Dict[str, Any]:
    """Dedicated endpoint for Transliteration inference requests."""
    return await _run_inference(
        request, payload, orchestrator, default_task_type="TRANSLITERATION"
    )


@router.post(
    "/language-detection/inference",
    response_model=GenericInferenceResponse,
    response_model_exclude={"smr_response"},
    summary="LANGUAGE_DETECTION Inference Endpoint",
    description="Route inference requests to LANGUAGE_DETECTION TaskService",
    openapi_extra={"requestBody": {"content": {"application/json": {"example": {
        "serviceId": "your-service-id",
        "input": [{"source": "hello world"}],
        "config": {"language": {"sourceLanguage": "hi"}},
    }}}}},
)
async def run_language_detection_inference(
    request: Request,
    payload: Dict[str, Any],
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> Dict[str, Any]:
    """Dedicated endpoint for Language Detection inference requests."""
    return await _run_inference(
        request, payload, orchestrator, default_task_type="LANGUAGE_DETECTION"
    )


@router.post(
    "/asr/inference",
    response_model=GenericInferenceResponse,
    summary="ASR Inference Endpoint",
    description="Route inference requests to ASR TaskService",
    openapi_extra={"requestBody": {"content": {"application/json": {"example": {
        "serviceId": "your-service-id",
        "audio": [{"audioContent": "<base64-encoded-audio>", "audioFormat": "wav"}],
        "config": {"language": {"sourceLanguage": "en"}},
    }}}}},
)
async def run_asr_inference(
    request: Request,
    payload: Dict[str, Any],
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> Dict[str, Any]:
    """Dedicated endpoint for ASR inference requests."""
    return await _run_inference(request, payload, orchestrator, default_task_type="ASR")


@router.post(
    "/tts/inference",
    response_model=None,
    summary="TTS Inference Endpoint",
    description="Route inference requests to TTS TaskService",
    openapi_extra={"requestBody": {"content": {"application/json": {"example": {
        "serviceId": "your-service-id",
        "input": [{"source": "यह एक परीक्षण है"}],
        "config": {
            "language": {"sourceLanguage": "hi"},
            "gender": "female",
            "samplingRate": 22050,
            "audioFormat": "mp3",
        },
    }}}}},
)
async def run_tts_inference(
    request: Request,
    payload: Dict[str, Any],
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> Dict[str, Any]:
    """Dedicated endpoint for TTS inference requests."""
    return await _run_inference(request, payload, orchestrator, default_task_type="TTS")


@router.post(
    "/audio-lang-detection/inference",
    response_model=None,
    summary="Audio Language Detection Inference Endpoint",
    description="Route inference requests to Audio Language Detection TaskService",
    openapi_extra={"requestBody": {"content": {"application/json": {"example": {
        "serviceId": "your-service-id",
        "audio": [{"audioContent": "<base64-encoded-audio>", "audioFormat": "wav"}],
        "config": {},
    }}}}},
)
async def run_audio_lang_detection_inference(
    request: Request,
    payload: Dict[str, Any],
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> Dict[str, Any]:
    """Dedicated endpoint for Audio Language Detection inference requests."""
    return await _run_inference(
        request, payload, orchestrator,
        default_task_type="AUDIO_LANGUAGE_DETECTION",
        strip=("smr_response", "elapsed_time_ms"),
    )


@router.post(
    "/speaker-diarization/inference",
    response_model=None,
    summary="Speaker Diarization Inference Endpoint",
    description="Route inference requests to Speaker Diarization TaskService",
    openapi_extra={"requestBody": {"content": {"application/json": {"example": {
        "serviceId": "your-service-id",
        "audio": [{"audioContent": "<base64-encoded-audio>", "audioFormat": "wav"}],
        "config": {"numSpeakers": "2"},
    }}}}},
)
async def run_speaker_diarization_inference(
    request: Request,
    payload: Dict[str, Any],
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> Dict[str, Any]:
    """Dedicated endpoint for Speaker Diarization inference requests."""
    return await _run_inference(
        request, payload, orchestrator,
        default_task_type="SPEAKER_DIARIZATION",
        strip=("smr_response", "elapsed_time_ms"),
    )


@router.post(
    "/language-diarization/inference",
    response_model=None,
    summary="Language Diarization Inference Endpoint",
    description="Route inference requests to Language Diarization TaskService",
    openapi_extra={"requestBody": {"content": {"application/json": {"example": {
        "serviceId": "your-service-id",
        "audio": [{"audioContent": "<base64-encoded-audio>", "audioFormat": "wav"}],
        "config": {},
    }}}}},
)
async def run_language_diarization_inference(
    request: Request,
    payload: Dict[str, Any],
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> Dict[str, Any]:
    """Dedicated endpoint for Language Diarization inference requests."""
    return await _run_inference(
        request, payload, orchestrator,
        default_task_type="LANGUAGE_DIARIZATION",
        strip=("smr_response", "elapsed_time_ms"),
    )


@router.post(
    "/ocr/inference",
    response_model=GenericInferenceResponse,
    summary="OCR Inference Endpoint",
    description="Route inference requests to OCR TaskService",
    openapi_extra={"requestBody": {"content": {"application/json": {"example": {
        "serviceId": "your-service-id",
        "image": [{"imageContent": "<base64-encoded-image>", "imageFormat": "png"}],
        "config": {"language": {"sourceLanguage": "en"}},
    }}}}},
)
async def run_ocr_inference(
    request: Request,
    payload: Dict[str, Any],
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> Dict[str, Any]:
    """Dedicated endpoint for OCR inference requests."""
    return await _run_inference(request, payload, orchestrator, default_task_type="OCR")


@router.post(
    "/chat/completions",
    summary="OpenAI-compatible Chat Completions",
    description="Forwards the request to the upstream LLM at /v1/chat/completions",
)
async def chat_completions(
    payload: Dict[str, Any] = Body(..., example=_CHAT_EXAMPLE),
) -> JSONResponse:
    status_code, body = await OpenAIProxyService().proxy(path="/v1/chat/completions", payload=payload)
    return JSONResponse(status_code=status_code, content=body)


@router.post(
    "/chat",
    summary="LLM Chat",
    description="Forwards the request to the upstream LLM at /v1/chat",
)
async def chat(
    payload: Dict[str, Any] = Body(..., example=_CHAT_EXAMPLE),
) -> JSONResponse:
    status_code, body = await OpenAIProxyService().proxy(path="/v1/chat", payload=payload)
    return JSONResponse(status_code=status_code, content=body)


@router.get(
    "/inference/health",
    summary="Health Check",
    description="Check if inference service is healthy",
)
async def health_check() -> Dict[str, str]:
    """Health check endpoint for inference service."""
    return {"status": "healthy", "message": "Inference service is operational"}


@router.get(
    "/inference/tasks",
    summary="List Available Tasks",
    description="Get list of supported inference task types",
)
async def list_available_tasks() -> Dict[str, list]:
    """List all available inference task types."""
    return {"tasks": ["NMT", "ASR", "OCR", "NER", "TTS", "PII", "LANGUAGE_DETECTION", "SPEAKER_DIARIZATION", "LANGUAGE_DIARIZATION", "TRANSLITERATION", "AUDIO_LANGUAGE_DETECTION", "SMR"]}
