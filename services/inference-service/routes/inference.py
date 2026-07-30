"""
Main inference router with unified /inference endpoint.
Handles all inference requests regardless of task type.
Integrates orchestration, factory, and telemetry.
"""

import logging
from typing import Any, Dict, Optional, Tuple

from fastapi import (
    APIRouter, Body, Depends, File, Form, HTTPException, Request, Response, UploadFile,
)
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from ai4i_core.context import (
    get_llm_usage_input_tokens,
    get_llm_usage_model_name,
    get_llm_usage_output_tokens,
)
from orchestrator import Orchestrator
from models.common import GenericInferenceResponse
from services.llm_service import OpenAIProxyService
from trace.request_span import traced_span, get_context_attributes

logger = logging.getLogger(__name__)
router = APIRouter(tags=["inference"])


_CHAT_EXAMPLE = {
    "model": "llm-service-1",
    "messages": [{"role": "user", "content": "Hello!"}],
    "stream": False,
}


# Module-level singleton: a fresh Orchestrator per request would rebuild the
# InferenceServerResolver each time, so its in-memory service cache never got
# a hit and every request blocked on a live MMS lookup.
_orchestrator = Orchestrator()


def get_orchestrator() -> Orchestrator:
    """
    Dependency for Orchestrator instance.
    Can be overridden in tests.
    """
    return _orchestrator


def _http_error_for(exc: Exception, task_type: str) -> HTTPException:
    """
    Map an orchestration failure to a client-safe HTTPException.

    Walks the exception __cause__ chain (raised with `from exc` throughout)
    so the original error classifies the response. Builtin exceptions only:
      ValueError          → 400 (validation messages are user-facing by design)
      NotImplementedError → 501 (unimplemented task, e.g. PII)
      LookupError         → 404 (unknown serviceId)
      ConnectionError     → 502 (MMS / Triton unreachable)
      RuntimeError        → 502 (server-side config / backend mismatch)
      anything else       → 500

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
        if isinstance(e, PermissionError):
            return HTTPException(status_code=403, detail=str(e))
        if isinstance(e, ValueError):
            return HTTPException(status_code=400, detail=str(e))
        if isinstance(e, NotImplementedError):
            return HTTPException(status_code=501, detail=str(e))
        # exact type: KeyError/IndexError are LookupError subclasses but are
        # programming errors, not not-found semantics — they must stay 500
        if type(e) is LookupError:
            return HTTPException(status_code=404, detail=str(e))
    for e in chain:
        if isinstance(e, (RuntimeError, ConnectionError)):
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
    # Unwrap TryItRequest envelope ({ service_name, serviceId?, payload: <inner> })
    # when present. Normal inference payloads carry input/audio/image at the top
    # level and never have a nested 'payload' wrapper, so this detection is safe.
    # Handles the case where APISIX rewrites /nmt/try-it → /nmt/inference while
    # passing the original client body through unchanged.
    inner = payload.get("payload")
    if isinstance(inner, dict) and "service_name" in payload:
        top_service_id = payload.get("serviceId")
        payload = inner
        if top_service_id and not (payload.get("config") or {}).get("serviceId"):
            payload = {**payload, "config": {**(payload.get("config") or {}), "serviceId": top_service_id}}

    # No manual timing here: the logging middleware records duration_ms for
    # every request, and the request span carries total_time_ms.
    if default_task_type and not payload.get("task_type"):
        payload = {**payload, "task_type": default_task_type}
    task_type = str(payload.get("task_type", "")).upper()
    logger.info(f"Inference request: task_type={task_type}")

    try:
        result = await orchestrator.route_inference(payload=payload, request=request)
    except Exception as exc:
        # No exc_info=True — the formatted traceback embeds chained
        # exception messages, which (for httpx-class errors below the
        # orchestrator) contain the resolved Triton URL. That traceback
        # then ships to OpenSearch via fluent-bit and ends up in the
        # Logs Dashboard. The `from exc` on the raise below preserves
        # the full chain for in-process / debug-shell inspection.
        # Log the chain's TYPE names so a developer triaging a 502 can
        # see "RuntimeError → ConnectionError → OSError" without exposing
        # any underlying str(e) (which is the URL-leak vector).
        chain_types: list[str] = []
        c: Optional[BaseException] = exc
        while c is not None and len(chain_types) < 16:
            chain_types.append(type(c).__name__)
            c = c.__cause__
        logger.error(
            "Inference failed: task_type=%s exc_chain=%s",
            task_type, "→".join(chain_types),
        )
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
    "/nmt/try-it",
    response_model=GenericInferenceResponse,
    response_model_exclude={"config"},
    summary="NMT Try-It Endpoint (anonymous)",
    description="Anonymous try-it endpoint. Accepts either a TryItRequest envelope "
                "({ service_name, serviceId?, payload: NMTPayload }) or a plain NMT "
                "payload directly (for when APISIX has already unwrapped the envelope).",
)
async def run_nmt_try_it(
    request: Request,
    body: Dict[str, Any],
    orchestrator: Orchestrator = Depends(get_orchestrator),
) -> Dict[str, Any]:
    # Unwrap TryItRequest envelope if present; fall back to body as-is when
    # APISIX has already extracted the inner payload before forwarding here.
    inner: Dict[str, Any] = body.get("payload") or body
    # Hoist top-level serviceId into config so the orchestrator finds it
    # regardless of which level the client placed it.
    top_service_id = body.get("serviceId")
    if top_service_id and not (inner.get("config") or {}).get("serviceId"):
        inner = {**inner, "config": {**(inner.get("config") or {}), "serviceId": top_service_id}}
    return await _run_inference(request, inner, orchestrator, default_task_type="NMT")


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

def _bridge_llm_usage_to_request(request: Request) -> None:
    """
    Copy the LLM token counts and model name from the ai4i_core context vars
    onto ``request.state``.

    ContextVars set inside the app task are not visible in the
    BaseHTTPMiddleware task where ObservabilityMiddleware drains the response
    body, but ``request.state`` is backed by the shared ASGI scope, which does
    cross that boundary. This is the handoff that lets the middleware emit
    token metrics without buffering (and re-parsing) the response.
    """
    request.state.llm_usage_input_tokens = get_llm_usage_input_tokens()
    request.state.llm_usage_output_tokens = get_llm_usage_output_tokens()
    request.state.llm_usage_model_name = get_llm_usage_model_name()


async def _run_llm_chat_stream(request: Request, payload: Dict[str, Any], path: str) -> Response:
    """
    Streaming counterpart to _run_llm_chat. The upstream connection (and its
    status code) is resolved eagerly so a misconfiguration, entitlement
    rejection or upstream failure can still return a normal JSON error — only
    a genuine 200 SSE stream turns into a StreamingResponse.

    The "request" span can't be closed when this function returns (the client
    is still reading the body at that point), so on the success path it's
    opened inside the generator and kept alive until the stream ends, the same
    trick proxy_traced_stream() uses for the model/ai-inference spans.
    """
    # Captured here, before proxy_traced_stream's own deferred generator and
    # the one below, so all spans on this request share the same
    # correlation_id regardless of whether the ContextVars are still readable
    # once execution resumes inside a generator (see _bridge_llm_usage_to_request).
    context_attrs = get_context_attributes()

    kind, status_code, result = await OpenAIProxyService().proxy_traced_stream(
        path=path, payload=payload, request=request,
    )

    if kind == "error":
        with traced_span("request", root=True, classify_status=True) as req_attrs:
            req_attrs["url"] = request.url.path
            req_attrs["method"] = request.method
            req_attrs.update(context_attrs)
            req_attrs["status"] = "failure"
            req_attrs["status_code"] = status_code
        return JSONResponse(status_code=status_code, content=result)

    async def gen():
        with traced_span("request", root=True, classify_status=True) as req_attrs:
            req_attrs["url"] = request.url.path
            req_attrs["method"] = request.method
            req_attrs.update(context_attrs)
            async for chunk in result:
                yield chunk
        # Token usage only arrives in the final SSE chunk, so this must run
        # after the stream is fully drained (the model name is known earlier,
        # but is read here too for a single assignment point).
        _bridge_llm_usage_to_request(request)

    return StreamingResponse(
        gen(),
        status_code=status_code,
        media_type="text/event-stream",
        # Anti-buffering headers: without these an intermediate proxy can
        # accumulate the whole SSE body and defeat live streaming.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _run_llm_chat(request: Request, payload: Dict[str, Any], path: str) -> Response:
    """
    Shared handler for LLM chat routes. Owns only the request span — MMS
    resolution, tier gate, model + ai_inference spans are managed inside
    OpenAIProxyService.proxy_traced(), mirroring the Orchestrator +
    BaseTaskService pattern for Triton services.

    Requests with a truthy "stream" field are delegated to
    _run_llm_chat_stream, which returns a real text/event-stream response
    instead of buffering the upstream SSE body into a JSON payload.
    """
    # Set service_id on request state so the observability middleware picks it
    # up for Prometheus metrics without reading the body a second time.
    # LLM follows the OpenAI spec: the client sends the model name in `model`,
    # and we treat that as the service ID (used for MMS resolution and PPU
    # billing). Reading the same field proxy_traced resolves/bills on keeps
    # metrics tagging from ever diverging from what's billed downstream.
    service_id = payload.get("model", "")
    request.state.service_id = service_id

    if isinstance(payload, dict) and payload.get("stream"):
        return await _run_llm_chat_stream(request, payload, path)

    with traced_span("request", root=True, classify_status=True) as req_attrs:
        req_attrs["url"] = request.url.path
        req_attrs["method"] = request.method
        req_attrs.update(get_context_attributes())

        status_code, body = await OpenAIProxyService().proxy_traced(
            path=path, payload=payload, request=request,
        )
        _bridge_llm_usage_to_request(request)

        if status_code >= 400:
            req_attrs["status"] = "failure"
            req_attrs["status_code"] = status_code

    return JSONResponse(status_code=status_code, content=body)

@router.post(
    "/chat/completions",
    summary="OpenAI-compatible Chat Completions",
    description="Forwards the request to the upstream LLM at /v1/chat/completions",
)
async def chat_completions(
    request: Request,
    payload: Dict[str, Any] = Body(..., examples=[_CHAT_EXAMPLE]),
) -> Response:
    return await _run_llm_chat(request, payload, path="/v1/chat/completions")


@router.post(
    "/chat",
    summary="LLM Chat",
    description="Forwards the request to the upstream LLM at /v1/chat",
)
async def chat(
    request: Request,
    payload: Dict[str, Any] = Body(..., examples=[_CHAT_EXAMPLE]),
) -> Response:
    return await _run_llm_chat(request, payload, path="/v1/chat")

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
    request: Request,
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
        path=upstream_path, files=files, data=data, request=request,
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
    request: Request,
    file: UploadFile = File(
        ..., description="Audio file (flac/mp3/mp4/mpeg/mpga/m4a/ogg/wav/webm). Capped at 25 MB.",
    ),
    model: str = Form(
        ...,
        examples=["llm-service-1"],
        description="Model name (OpenAI `model` field); the service identifier as registered in the platform.",
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
    return await _proxy_audio_upload(request, file, data, "/audio/transcriptions")


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
    request: Request,
    file: UploadFile = File(
        ..., description="Audio file (flac/mp3/mp4/mpeg/mpga/m4a/ogg/wav/webm). Capped at 25 MB.",
    ),
    model: str = Form(
        ...,
        examples=["llm-service-1"],
        description="Model name (OpenAI `model` field); the service identifier as registered in the platform.",
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
    return await _proxy_audio_upload(request, file, data, "/audio/translations")


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
