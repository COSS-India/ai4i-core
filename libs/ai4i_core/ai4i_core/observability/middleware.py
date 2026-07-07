"""
Middleware for AI4ICore Observability Plugin.

Handles request tracking, path-based service detection, payload analysis, and
Prometheus metric emission. Tenant is read from the gateway-injected
``X-Tenant-Id`` header (set by ``auth-service /validate``) — this middleware
does NOT decode JWTs and does NOT open OpenTelemetry spans.

For JSON inference requests, payload analysis runs **before** ``call_next``.
Pre-computed attributes are injected as ``X-Tracing-*`` request headers for
downstream tracing layers and stored on ``request.state`` for post-response
Prometheus emission.
"""
import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional, Tuple

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .config import PluginConfig
from .metrics import MetricsCollector
from .payload_analysis import analyze_payload, build_observability_metrics
from .tracing_headers import inject_tracing_headers

logger = logging.getLogger(__name__)

# Service types whose request bodies carry payload-size metrics worth
# extracting. Membership check is O(1). LLM is handled separately because its
# token counts come from the response (vLLM `usage` block), not the request.
_BODY_METRIC_SERVICES = frozenset({
    "tts", "translation", "asr", "ocr", "transliteration",
    "language_detection", "audio_lang_detection",
    "speaker_diarization", "language_diarization", "ner",
})

_INFERENCE_JSON_PATH_HINTS = (
    "/inference",
    "/nmt",
    "/asr",
    "/tts",
    "/ocr",
    "/ner",
    "/transliteration",
    "/translate",
    "/translation",
    "/language-detection",
    "/lang-detect",
    "/audio-lang-detection",
    "/audio-language-detection",
    "/speaker-diarization",
    "/language-diarization",
    "/chat",
    "/completion",
    "/generate",
    "/llm",
)


def _has_llm_metrics(trace_metrics: Optional[Dict[str, Any]]) -> bool:
    if not trace_metrics:
        return False
    return bool(
        trace_metrics.get("llm_prompt_tokens")
        or trace_metrics.get("llm_completion_tokens")
        or trace_metrics.get("llm_total_tokens")
    )


def _track_characters(
    trace_metrics: Dict[str, Any],
    track_fn,
    **extra_labels,
) -> None:
    chars = int(trace_metrics.get("characters") or 0)
    if chars > 0:
        track_fn(characters=chars, **extra_labels)


def _track_audio_seconds(
    trace_metrics: Dict[str, Any],
    track_fn,
    **extra_labels,
) -> None:
    seconds = float(trace_metrics.get("audio_seconds") or 0.0)
    if seconds > 0:
        track_fn(audio_seconds=seconds, **extra_labels)


def _emit_tts_metrics(collector, trace_metrics, source_lang, target_lang, tenant, service_id):
    _track_characters(
        trace_metrics,
        collector.track_tts_characters,
        language=source_lang,
        tenant=tenant,
        service_id=service_id,
    )


def _emit_translation_metrics(collector, trace_metrics, source_lang, target_lang, tenant, service_id):
    _track_characters(
        trace_metrics,
        collector.track_nmt_characters,
        source_lang=source_lang,
        target_lang=target_lang,
        tenant=tenant,
        service_id=service_id,
    )


def _emit_asr_metrics(collector, trace_metrics, source_lang, target_lang, tenant, service_id):
    _track_audio_seconds(
        trace_metrics,
        collector.track_asr_audio_length,
        language=source_lang,
        tenant=tenant,
        service_id=service_id,
    )


def _emit_ocr_metrics(collector, trace_metrics, source_lang, target_lang, tenant, service_id):
    chars = int(trace_metrics.get("ocr_characters") or 0)
    if chars > 0:
        collector.track_ocr_characters(characters=chars, tenant=tenant, service_id=service_id)
    kb = float(trace_metrics.get("ocr_image_kb") or 0.0)
    if kb > 0:
        collector.track_ocr_image_size(image_size_kb=kb, tenant=tenant, service_id=service_id)


def _emit_transliteration_metrics(collector, trace_metrics, source_lang, target_lang, tenant, service_id):
    _track_characters(
        trace_metrics,
        collector.track_transliteration_characters,
        source_lang=source_lang,
        target_lang=target_lang,
        tenant=tenant,
        service_id=service_id,
    )


def _emit_language_detection_metrics(collector, trace_metrics, source_lang, target_lang, tenant, service_id):
    _track_characters(
        trace_metrics,
        collector.track_language_detection_characters,
        tenant=tenant,
        service_id=service_id,
    )


def _emit_audio_lang_detection_metrics(collector, trace_metrics, source_lang, target_lang, tenant, service_id):
    _track_audio_seconds(
        trace_metrics,
        collector.track_audio_lang_detection_length,
        tenant=tenant,
        service_id=service_id,
    )


def _emit_speaker_diarization_metrics(collector, trace_metrics, source_lang, target_lang, tenant, service_id):
    _track_audio_seconds(
        trace_metrics,
        collector.track_speaker_diarization_length,
        tenant=tenant,
        service_id=service_id,
    )


def _emit_language_diarization_metrics(collector, trace_metrics, source_lang, target_lang, tenant, service_id):
    _track_audio_seconds(
        trace_metrics,
        collector.track_language_diarization_length,
        tenant=tenant,
        service_id=service_id,
    )


def _emit_ner_metrics(collector, trace_metrics, source_lang, target_lang, tenant, service_id):
    tokens = int(trace_metrics.get("ner_tokens") or 0)
    if tokens > 0:
        collector.track_ner_tokens(tokens=tokens, tenant=tenant, service_id=service_id)


_TRACE_PAYLOAD_EMITTERS = {
    "tts": _emit_tts_metrics,
    "translation": _emit_translation_metrics,
    "asr": _emit_asr_metrics,
    "ocr": _emit_ocr_metrics,
    "transliteration": _emit_transliteration_metrics,
    "language_detection": _emit_language_detection_metrics,
    "audio_lang_detection": _emit_audio_lang_detection_metrics,
    "speaker_diarization": _emit_speaker_diarization_metrics,
    "language_diarization": _emit_language_diarization_metrics,
    "ner": _emit_ner_metrics,
}


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Middleware for tracking requests and collecting metrics."""

    def __init__(self, app, metrics_collector: Optional[MetricsCollector] = None,
                 config: Optional[PluginConfig] = None):
        super().__init__(app)
        self.metrics_collector = metrics_collector or MetricsCollector()
        self.config = config or PluginConfig()
        # asyncio.create_task only keeps a weak reference; hold strong refs
        # here so background metric tasks aren't GC'd before they finish.
        self._pending_tasks: "set[asyncio.Task[Any]]" = set()

    async def dispatch(self, request: Request, call_next):
        if not self.config.enabled:
            return await call_next(request)

        start_time = time.time()
        path = request.url.path
        method = request.method
        service_type = self._detect_service_type(path)

        if self.config.debug:
            logger.debug(f"Request: {method} {path} -> service_type={service_type}")

        trace_metrics: Optional[Dict[str, Any]] = None
        body_bytes: Optional[bytes] = None

        if self._should_analyze_request_body(request, method, path):
            body_bytes, trace_metrics = await self._prepare_inference_request(
                request, service_type
            )

        if body_bytes is not None:
            response = await self._call_next_with_body(request, body_bytes, call_next)
        else:
            response = await call_next(request)

        duration = time.time() - start_time

        if trace_metrics is None:
            trace_metrics = getattr(request.state, "observability_payload_metrics", None)

        # LLM (chat / chat-completions): token counts come from the upstream
        # response `usage` block. Buffer the response body once when needed.
        llm_prompt_tokens = 0
        llm_completion_tokens = 0
        llm_total_tokens = 0
        llm_model = ""
        if _has_llm_metrics(trace_metrics):
            llm_prompt_tokens = int(trace_metrics.get("llm_prompt_tokens") or 0)
            llm_completion_tokens = int(trace_metrics.get("llm_completion_tokens") or 0)
            llm_total_tokens = int(trace_metrics.get("llm_total_tokens") or 0)
            llm_model = str(trace_metrics.get("llm_model") or "")
        elif service_type == "llm" or (trace_metrics or {}).get("service_type") == "llm":
            response, response_body_bytes = await self._buffer_response(response)
            (
                llm_prompt_tokens,
                llm_completion_tokens,
                llm_total_tokens,
                llm_model,
            ) = self._extract_llm_usage_from_body(response_body_bytes)

        tenant_label = (request.headers.get("X-Tenant-Id") or "").strip() or "unknown"
        service_id = getattr(request.state, "service_id", "") or ""
        if service_type == "llm" and llm_model:
            service_id = llm_model
        elif trace_metrics and trace_metrics.get("service_id"):
            service_id = str(trace_metrics.get("service_id") or service_id)

        task = asyncio.create_task(self._record_metrics(
            path=path,
            method=method,
            service_type=service_type,
            tenant=tenant_label,
            service_id=service_id,
            status_code=response.status_code,
            duration=duration,
            trace_metrics=trace_metrics,
            llm_prompt_tokens=llm_prompt_tokens,
            llm_completion_tokens=llm_completion_tokens,
            llm_total_tokens=llm_total_tokens,
            llm_model=llm_model,
        ))
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)

        return response

    async def _prepare_inference_request(
        self,
        request: Request,
        path_service_type: str,
    ) -> Tuple[Optional[bytes], Optional[Dict[str, Any]]]:
        """Analyze JSON body, inject tracing headers, and cache metrics on state."""
        body_bytes: Optional[bytes] = None
        try:
            body_bytes = await request.body()
            if not body_bytes:
                return None, None

            payload = json.loads(body_bytes)
            if not isinstance(payload, dict):
                return body_bytes, None

            analysis = analyze_payload(payload)
            if path_service_type != "unknown" and analysis.get("service_type") == "unknown":
                analysis["service_type"] = path_service_type

            inject_tracing_headers(request.scope, analysis)
            trace_metrics = build_observability_metrics(
                analysis,
                path_service_type=path_service_type,
            )
            request.state.observability_payload_metrics = trace_metrics
            request.state.observability_payload_analysis = analysis

            if self.config.debug:
                logger.debug(
                    "Injected tracing headers for %s (service_type=%s)",
                    request.url.path,
                    analysis.get("service_type"),
                )
            return body_bytes, trace_metrics
        except json.JSONDecodeError:
            return body_bytes, None
        except Exception:
            if self.config.debug:
                logger.debug("Inference payload analysis failed", exc_info=True)
            return body_bytes, None

    @staticmethod
    async def _call_next_with_body(request: Request, body: bytes, call_next):
        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        replayed = Request(request.scope, receive)
        return await call_next(replayed)

    @staticmethod
    def _should_analyze_request_body(request: Request, method: str, path: str) -> bool:
        if method.upper() not in {"POST", "PUT", "PATCH"}:
            return False
        path_lower = path.lower()
        if not any(hint in path_lower for hint in _INFERENCE_JSON_PATH_HINTS):
            return False
        content_type = (request.headers.get("content-type") or "").lower()
        if content_type and "application/json" not in content_type:
            return False
        return True

    # ------------------------------------------------------------------
    # Path-based service detection.
    # ------------------------------------------------------------------
    @staticmethod
    def _detect_service_type(path: str) -> str:
        """Detect service type from URL path.

        Pure path-based; never inspects the body. The unified
        ``/api/v1/inference`` endpoint resolves to ``"unknown"`` because the
        task is only knowable from the body — dedicated per-task paths like
        ``/nmt/inference`` resolve to a specific type.
        """
        path_lower = path.lower()
        if any(p in path_lower for p in ("/translation", "/nmt", "/translate")):
            return "translation"
        if any(p in path_lower for p in ("/asr", "/transcribe", "/speech")):
            return "asr"
        if any(p in path_lower for p in ("/tts", "/synthesize")):
            return "tts"
        if any(p in path_lower for p in ("/ocr", "/text-recognition")):
            return "ocr"
        if any(p in path_lower for p in ("/transliteration", "/xlit", "/transliterate")):
            return "transliteration"
        if any(p in path_lower for p in ("/audio-lang-detection", "/audio-language-detection", "/audio-detect")):
            return "audio_lang_detection"
        if any(p in path_lower for p in ("/language-detection", "/lang-detect", "/detect-language")):
            return "language_detection"
        if any(p in path_lower for p in ("/language-diarization", "/language-diarization-compute-call")):
            return "language_diarization"
        if any(p in path_lower for p in ("/speaker-diarization", "/speaker-diarization-compute-call")):
            return "speaker_diarization"
        if any(p in path_lower for p in ("/ner", "/entity", "/entities")):
            return "ner"
        if any(p in path_lower for p in ("/speaker", "/speaker-enrollment", "/speaker-verification", "/speak")):
            return "speaker_verification"
        if any(p in path_lower for p in ("/llm", "/generate", "/chat", "/completion")):
            return "llm"
        if any(p in path_lower for p in ("/enterprise", "/health", "/metrics", "/config")):
            return "enterprise"
        if any(p in path_lower for p in ("/docs", "/openapi", "/redoc")):
            return "documentation"
        return "unknown"

    # ------------------------------------------------------------------
    # Background processing — runs AFTER the response is returned.
    # ------------------------------------------------------------------
    async def _record_metrics(
        self,
        path: str,
        method: str,
        service_type: str,
        tenant: str,
        service_id: str,
        status_code: int,
        duration: float,
        trace_metrics: Optional[Dict[str, Any]] = None,
        llm_prompt_tokens: int = 0,
        llm_completion_tokens: int = 0,
        llm_total_tokens: int = 0,
        llm_model: str = "",
    ) -> None:
        """Emit Prometheus metrics out-of-band."""
        try:
            effective_service_type = service_type
            if trace_metrics:
                effective_service_type = str(
                    trace_metrics.get("service_type") or service_type
                )
                payload_service_id = str(trace_metrics.get("service_id") or "").strip()
                if payload_service_id:
                    service_id = payload_service_id

            self.metrics_collector.track_request(
                method=method,
                endpoint=path,
                status_code=status_code,
                duration=duration,
                tenant=tenant,
                service_id=service_id,
            )

            if effective_service_type == "llm" and (
                llm_prompt_tokens or llm_completion_tokens or llm_total_tokens
            ):
                self.metrics_collector.track_llm_tokens(
                    model=llm_model or "unknown",
                    prompt_tokens=llm_prompt_tokens,
                    completion_tokens=llm_completion_tokens,
                    total_tokens=llm_total_tokens,
                    tenant=tenant,
                    service_id=service_id,
                    endpoint=path,
                )
                return

            if trace_metrics and effective_service_type in _BODY_METRIC_SERVICES:
                self._emit_trace_payload_metrics(
                    trace_metrics=trace_metrics,
                    service_type=effective_service_type,
                    tenant=tenant,
                    service_id=service_id,
                )
        except Exception:
            if self.config.debug:
                logger.debug("Background metrics recording failed", exc_info=True)

    def _emit_trace_payload_metrics(
        self,
        trace_metrics: Dict[str, Any],
        service_type: str,
        tenant: str,
        service_id: str,
    ) -> None:
        """Emit Prometheus payload metrics from a pre-computed snapshot."""
        emitter = _TRACE_PAYLOAD_EMITTERS.get(service_type)
        if emitter is None:
            return
        source_lang = str(trace_metrics.get("source_lang") or "")
        target_lang = str(trace_metrics.get("target_lang") or "")
        try:
            emitter(
                self.metrics_collector,
                trace_metrics,
                source_lang,
                target_lang,
                tenant,
                service_id,
            )
        except Exception:
            if self.config.debug:
                logger.debug("Trace payload metric emission failed", exc_info=True)

    # ------------------------------------------------------------------
    # LLM response handling — buffer the JSON body and pull `usage`.
    # ------------------------------------------------------------------
    async def _buffer_response(self, response) -> Tuple[Response, bytes]:
        """Drain ``response.body_iterator`` and return a fresh Response.

        The Starlette body iterator can only be consumed once; reading it to
        inspect ``usage`` makes the original response unusable, so we rebuild
        a new Response that carries the same bytes back to the client.
        """
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode())
        body = b"".join(chunks)
        headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
        new_response = Response(
            content=body,
            status_code=response.status_code,
            headers=headers,
            media_type=response.media_type,
        )
        return new_response, body

    def _extract_llm_usage_from_body(
        self, body_bytes: bytes
    ) -> Tuple[int, int, int, str]:
        """Return (prompt_tokens, completion_tokens, total_tokens, model).

        Reads an OpenAI / vLLM-shaped JSON response. Zeros + empty model on
        any parse failure — the request still gets counted, only the token
        histogram is skipped.
        """
        try:
            if not body_bytes:
                return 0, 0, 0, ""
            data = json.loads(body_bytes)
            usage = data.get("usage") or {}
            prompt = int(usage.get("prompt_tokens") or 0)
            completion = int(usage.get("completion_tokens") or 0)
            total = int(usage.get("total_tokens") or (prompt + completion))
            model = str(data.get("model") or "")
            return prompt, completion, total, model
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            if self.config.debug:
                logger.debug(f"LLM usage extraction failed: {e}")
            return 0, 0, 0, ""
