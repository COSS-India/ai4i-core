"""
Main inference router with unified /inference endpoint.
Handles all inference requests regardless of task type.
Integrates orchestration, factory, and telemetry.
"""

from typing import Any, Dict, Optional
from fastapi import (
    APIRouter, Body, Depends, File, Form, HTTPException, Request, Response, UploadFile,
)
from fastapi.responses import JSONResponse, PlainTextResponse
import logging

from orchestrator import Orchestrator, OrchestratorError
from models.common import GenericInferenceRequest, GenericInferenceResponse
from models.task_types import task_registry
from services.llm_service import OpenAIProxyService


logger = logging.getLogger(__name__)
router = APIRouter(tags=["inference"])


_CHAT_EXAMPLE = {
    "model": "google/gemma-4-E4B-it",
    "messages": [{"role": "user", "content": "Hello!"}],
    "stream": False,
}


class InferenceRouterError(Exception):
    """Base exception for routing errors."""

    pass


async def get_orchestrator() -> Orchestrator:
    """
    Dependency for Orchestrator instance.
    Can be overridden in tests.
    """
    return Orchestrator()


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
    import time
    start_time = time.time()

    try:
        task_type = payload.get("task_type", "").upper()

        logger.info(f"Inference request: task_type={task_type}")

        # Route through orchestrator
        result = await orchestrator.route_inference(
            payload=payload,
            request=request,
        )

        duration_ms = (time.time() - start_time) * 1000
        logger.info(f"✓ Inference completed: task_type={task_type}, duration_ms={duration_ms:.2f}ms")

        return result

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"✗ Inference failed: {str(e)}, duration_ms={duration_ms:.2f}ms")
        raise HTTPException(status_code=400, detail=str(e))

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
    """
    Dedicated endpoint for NMT inference requests.
    Sets task_type to NMT if not provided in payload, then routes via Orchestrator.
    """
    import time
    start_time = time.time()

    try:
        if not payload.get("task_type"):
            request_payload = {**payload, "task_type": "NMT"}
        else:
            request_payload = payload

        task_type = request_payload["task_type"].upper()
        logger.info(f"Inference request: task_type={task_type}")

        result = await orchestrator.route_inference(payload=request_payload, request=request)

        duration_ms = (time.time() - start_time) * 1000
        # logger.info(f"✓ Inference completed: task_type={task_type}, duration_ms={duration_ms:.2f}ms")

        return result

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"✗ Inference failed: {str(e)}, duration_ms={duration_ms:.2f}ms")
        raise HTTPException(status_code=400, detail=str(e))


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
    """
    Dedicated endpoint for NER inference requests.
    Sets task_type to NER if not provided in payload, then routes via Orchestrator.
    """
    import time
    start_time = time.time()

    try:
        if not payload.get("task_type"):
            request_payload = {**payload, "task_type": "NER"}
        else:
            request_payload = payload

        task_type = request_payload["task_type"].upper()
        # logger.info(f"Inference request: task_type={task_type}")

        result = await orchestrator.route_inference(payload=request_payload, request=request)
        result.pop("smr_response", None)
        result.pop("elapsed_time_ms", None)

        duration_ms = (time.time() - start_time) * 1000
        # logger.info(f"✓ Inference completed: task_type={task_type}, duration_ms={duration_ms:.2f}ms")

        return result

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"✗ Inference failed: {str(e)}, duration_ms={duration_ms:.2f}ms")
        raise HTTPException(status_code=400, detail=str(e))



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
    """
    Dedicated endpoint for Transliteration inference requests.
    Sets task_type to TRANSLITERATION if not provided in payload, then routes via Orchestrator.
    """
    import time
    start_time = time.time()

    try:
        if not payload.get("task_type"):
            request_payload = {**payload, "task_type": "TRANSLITERATION"}
        else:
            request_payload = payload

        task_type = request_payload["task_type"].upper()
        logger.info(f"Inference request: task_type={task_type}")

        result = await orchestrator.route_inference(payload=request_payload, request=request)

        duration_ms = (time.time() - start_time) * 1000
        logger.info(f"✓ Inference completed: task_type={task_type}, duration_ms={duration_ms:.2f}ms")

        return result

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"✗ Inference failed: {str(e)}, duration_ms={duration_ms:.2f}ms")
        raise HTTPException(status_code=400, detail=str(e))

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
    """
    Dedicated endpoint for Language Detection inference requests.
    Sets task_type to LANGUAGE_DETECTION if not provided in payload, then routes via Orchestrator.
    """
    import time
    start_time = time.time()

    try:
        if not payload.get("task_type"):
            request_payload = {**payload, "task_type": "LANGUAGE_DETECTION"}
        else:
            request_payload = payload

        task_type = request_payload["task_type"].upper()
        logger.info(f"Inference request: task_type={task_type}")

        result = await orchestrator.route_inference(payload=request_payload, request=request)

        duration_ms = (time.time() - start_time) * 1000
        logger.info(f"✓ Inference completed: task_type={task_type}, duration_ms={duration_ms:.2f}ms")

        return result

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"✗ Inference failed: {str(e)}, duration_ms={duration_ms:.2f}ms")
        raise HTTPException(status_code=400, detail=str(e))


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
    """
    Dedicated endpoint for ASR inference requests.
    Sets task_type to ASR if not provided in payload, then routes via Orchestrator.
    """
    import time
    start_time = time.time()

    try:
        if not payload.get("task_type"):
            request_payload = {**payload, "task_type": "ASR"}
        else:
            request_payload = payload

        task_type = request_payload["task_type"].upper()
        logger.info(f"Inference request: task_type={task_type}")

        result = await orchestrator.route_inference(payload=request_payload, request=request)

        duration_ms = (time.time() - start_time) * 1000
        logger.info(f"✓ Inference completed: task_type={task_type}, duration_ms={duration_ms:.2f}ms")

        return result

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"✗ Inference failed: {str(e)}, duration_ms={duration_ms:.2f}ms")
        raise HTTPException(status_code=400, detail=str(e))


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
    """
    Dedicated endpoint for TTS inference requests.
    Sets task_type to TTS if not provided in payload, then routes via Orchestrator.
    """
    import time
    start_time = time.time()

    try:
        if not payload.get("task_type"):
            request_payload = {**payload, "task_type": "TTS"}
        else:
            request_payload = payload

        task_type = request_payload["task_type"].upper()
        logger.info(f"Inference request: task_type={task_type}")

        result = await orchestrator.route_inference(payload=request_payload, request=request)

        duration_ms = (time.time() - start_time) * 1000
        logger.info(f"✓ Inference completed: task_type={task_type}, duration_ms={duration_ms:.2f}ms")

        return result

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"✗ Inference failed: {str(e)}, duration_ms={duration_ms:.2f}ms")
        raise HTTPException(status_code=400, detail=str(e))


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
    """
    Dedicated endpoint for Audio Language Detection inference requests.
    Sets task_type to AUDIO_LANGUAGE_DETECTION if not provided in payload, then routes via Orchestrator.
    """
    import time
    start_time = time.time()

    try:
        if not payload.get("task_type"):
            request_payload = {**payload, "task_type": "AUDIO_LANGUAGE_DETECTION"}
        else:
            request_payload = payload

        task_type = request_payload["task_type"].upper()
        logger.info(f"Inference request: task_type={task_type}")

        result = await orchestrator.route_inference(payload=request_payload, request=request)
        result.pop("smr_response", None)
        result.pop("elapsed_time_ms", None)

        duration_ms = (time.time() - start_time) * 1000
        logger.info(f"✓ Inference completed: task_type={task_type}, duration_ms={duration_ms:.2f}ms")

        return result

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"✗ Inference failed: {str(e)}, duration_ms={duration_ms:.2f}ms")
        raise HTTPException(status_code=400, detail=str(e))


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
    """
    Dedicated endpoint for Speaker Diarization inference requests.
    Sets task_type to SPEAKER_DIARIZATION if not provided in payload, then routes via Orchestrator.
    """
    import time
    start_time = time.time()

    try:
        if not payload.get("task_type"):
            request_payload = {**payload, "task_type": "SPEAKER_DIARIZATION"}
        else:
            request_payload = payload

        task_type = request_payload["task_type"].upper()
        logger.info(f"Inference request: task_type={task_type}")

        result = await orchestrator.route_inference(payload=request_payload, request=request)
        result.pop("smr_response", None)
        result.pop("elapsed_time_ms", None)

        duration_ms = (time.time() - start_time) * 1000
        logger.info(f"✓ Inference completed: task_type={task_type}, duration_ms={duration_ms:.2f}ms")

        return result

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"✗ Inference failed: {str(e)}, duration_ms={duration_ms:.2f}ms")
        raise HTTPException(status_code=400, detail=str(e))


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
    """
    Dedicated endpoint for Language Diarization inference requests.
    Sets task_type to LANGUAGE_DIARIZATION if not provided in payload, then routes via Orchestrator.
    """
    import time
    start_time = time.time()

    try:
        if not payload.get("task_type"):
            request_payload = {**payload, "task_type": "LANGUAGE_DIARIZATION"}
        else:
            request_payload = payload

        task_type = request_payload["task_type"].upper()
        logger.info(f"Inference request: task_type={task_type}")

        result = await orchestrator.route_inference(payload=request_payload, request=request)
        result.pop("smr_response", None)
        result.pop("elapsed_time_ms", None)

        duration_ms = (time.time() - start_time) * 1000
        logger.info(f"✓ Inference completed: task_type={task_type}, duration_ms={duration_ms:.2f}ms")

        return result

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"✗ Inference failed: {str(e)}, duration_ms={duration_ms:.2f}ms")
        raise HTTPException(status_code=400, detail=str(e))


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
    """
    Dedicated endpoint for OCR inference requests.
    Sets task_type to OCR if not provided in payload, then routes via Orchestrator.
    """
    import time
    start_time = time.time()

    try:
        if not payload.get("task_type"):
            request_payload = {**payload, "task_type": "OCR"}
        else:
            request_payload = payload

        task_type = request_payload["task_type"].upper()
        logger.info(f"Inference request: task_type={task_type}")

        result = await orchestrator.route_inference(payload=request_payload, request=request)

        duration_ms = (time.time() - start_time) * 1000
        logger.info(f"✓ Inference completed: task_type={task_type}, duration_ms={duration_ms:.2f}ms")

        return result

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        logger.error(f"✗ Inference failed: {str(e)}, duration_ms={duration_ms:.2f}ms")
        raise HTTPException(status_code=400, detail=str(e))


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


# ─────────────────────────────────────────────────────────────────────────────
# OpenAI-compatible audio endpoints — pure multipart passthrough.
#
# Upstream (vLLM/gemma server) is expected to implement /v1/audio/transcriptions
# and /v1/audio/translations conforming to OpenAI's OpenAPI spec. See
# DESIGN_audio_llm_endpoints.md §2 for the upstream contract this passthrough
# assumes.
# ─────────────────────────────────────────────────────────────────────────────

_AUDIO_MAX_BYTES = 25 * 1024 * 1024  # OpenAI's documented cap for /audio/*


def _audio_error(
    status: int,
    *,
    message: str,
    type_: str = "invalid_request_error",
    param: Optional[str] = None,
    code: Optional[str] = None,
) -> JSONResponse:
    """OpenAI-shape error envelope: {"error": {message, type, param?, code?}}."""
    payload: Dict[str, Any] = {"message": message, "type": type_}
    if param is not None:
        payload["param"] = param
    if code is not None:
        payload["code"] = code
    return JSONResponse(status_code=status, content={"error": payload})


# Response shapes for OpenAPI docs. The actual body comes from upstream
# verbatim; this annotation just describes what callers should expect.
_AUDIO_RESPONSES: Dict[int | str, Dict[str, Any]] = {
    200: {
        "description": "Successful transcription/translation.",
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "required": ["text"],
                    "properties": {"text": {"type": "string"}},
                },
                "example": {"text": "Hello, how are you?"},
            },
            "text/plain": {
                "schema": {"type": "string"},
                "example": "Hello, how are you?",
            },
        },
    },
    413: {"description": "Uploaded file exceeds the 25 MB cap."},
    502: {"description": "Upstream LLM unreachable."},
    503: {"description": "No upstream LLM endpoint configured."},
}


async def _proxy_audio_upload(
    file: UploadFile,
    data: Dict[str, Any],
    upstream_path: str,
) -> Response:
    """Edge cap + multipart forwarding + response shaping. Each route owns
    its own form-field set and supplies the ``data`` dict; this helper only
    handles the mechanics shared between transcriptions and translations.

    httpx emits each list value in ``data`` as a repeated form field, which
    is how OpenAI's array form fields (`timestamp_granularities[]`,
    `include[]`, etc.) are serialised on the wire."""
    file_bytes = await file.read()
    if len(file_bytes) > _AUDIO_MAX_BYTES:
        return _audio_error(
            413,
            message=(
                f"File exceeds the 25 MB limit "
                f"(received {len(file_bytes)} bytes)."
            ),
            param="file",
            code="file_too_large",
        )

    files = {
        "file": (
            file.filename,
            file_bytes,
            file.content_type or "application/octet-stream",
        )
    }

    status_code, body = await OpenAIProxyService().proxy_multipart(
        path=upstream_path, files=files, data=data,
    )

    # Body shape decides response type: dict → JSON, str → text/plain.
    # Preserves both response_format=json and =text behaviours without
    # peeking at the form field ourselves.
    if isinstance(body, dict):
        return JSONResponse(status_code=status_code, content=body)
    return PlainTextResponse(status_code=status_code, content=body or "")


def _build_form_data(**fields: Any) -> Dict[str, Any]:
    """Drop None / empty-list values; coerce non-list scalars to str.
    Keeps array form fields (e.g. ``timestamp_granularities[]``) as lists
    so httpx repeats them as separate parts on the wire."""
    out: Dict[str, Any] = {}
    for key, value in fields.items():
        if value is None:
            continue
        if isinstance(value, list):
            if value:  # drop empty lists too
                out[key] = value
            continue
        out[key] = str(value)
    return out


@router.post(
    "/audio/transcriptions",
    summary="OpenAI-compatible speech-to-text (same language as audio).",
    description=(
        "Multipart passthrough to the upstream LLM at "
        "/v1/audio/transcriptions. Request and response shapes follow "
        "OpenAI's OpenAPI spec; this service does not transform either."
    ),
    responses=_AUDIO_RESPONSES,
)
async def audio_transcriptions(
    file: UploadFile = File(
        ..., description="Audio file (flac/mp3/mp4/mpeg/mpga/m4a/ogg/wav/webm). Capped at 25 MB.",
    ),
    model: str = Form(
        ...,
        examples=["google/gemma-4-E4B-it"],
        description="Model identifier, e.g. `google/gemma-4-E4B-it`.",
    ),
    language: Optional[str] = Form(
        None, description="ISO-639-1 source language code (optional).",
    ),
    prompt: Optional[str] = Form(
        None, description="Optional text to guide the model's style.",
    ),
    response_format: Optional[str] = Form(
        "json",
        description="One of `json`, `text`, `srt`, `verbose_json`, `vtt`. Default `json`.",
    ),
    temperature: Optional[float] = Form(
        0.0, ge=0.0, le=1.0, description="Sampling temperature, 0.0–1.0.",
    ),
) -> Response:
    data = _build_form_data(
        model=model,
        language=language,
        prompt=prompt,
        response_format=response_format,
        temperature=temperature,
    )
    return await _proxy_audio_upload(file, data, "/audio/transcriptions")


@router.post(
    "/audio/translations",
    summary="OpenAI-compatible audio → English translation.",
    description=(
        "Multipart passthrough to the upstream LLM at "
        "/v1/audio/translations. Request and response shapes follow "
        "OpenAI's OpenAPI spec; this service does not transform either."
    ),
    responses=_AUDIO_RESPONSES,
)
async def audio_translations(
    file: UploadFile = File(
        ..., description="Audio file (flac/mp3/mp4/mpeg/mpga/m4a/ogg/wav/webm). Capped at 25 MB.",
    ),
    model: str = Form(
        ...,
        examples=["google/gemma-4-E4B-it"],
        description="Model identifier, e.g. `google/gemma-4-E4B-it`.",
    ),
    prompt: Optional[str] = Form(
        None,
        description=(
            "Optional text to guide the model's style or continue a previous "
            "audio segment. The prompt should be in English."
        ),
    ),
    response_format: Optional[str] = Form(
        "json",
        description="One of `json`, `text`, `srt`, `verbose_json`, `vtt`. Default `json`.",
    ),
    temperature: Optional[float] = Form(
        0.0, ge=0.0, le=1.0, description="Sampling temperature, 0.0–1.0.",
    ),
) -> Response:
    data = _build_form_data(
        model=model,
        prompt=prompt,
        response_format=response_format,
        temperature=temperature,
    )
    return await _proxy_audio_upload(file, data, "/audio/translations")


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
    return {"tasks": ["NMT", "ASR", "OCR", "NER", "TTS", "PII", "LANGUAGE_DETECTION", "SPEAKER_DIARIZATION", "LANGUAGE_DIARIZATION", "TRANSLITERATION", "AUDIO_LANGUAGE_DETECTION", "SMR"]}

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
