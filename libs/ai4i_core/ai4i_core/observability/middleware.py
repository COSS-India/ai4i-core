"""
Middleware for AI4ICore Observability Plugin.

Handles request tracking, path-based service detection, and Prometheus metric
emission. Tenant is read from the gateway-injected ``X-Tenant-Id`` header
(set by ``auth-service /validate``) — this middleware does NOT decode JWTs and
does NOT open OpenTelemetry spans.

When inference-service trace publishes pre-computed payload metrics (via
``set_inference_payload_metrics``), this middleware skips re-parsing the
request body and emits Prometheus metrics from that snapshot instead.
"""
import asyncio
import json
import logging
import re
import time
from contextvars import ContextVar
from typing import Any, Dict, Optional, Tuple

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .config import PluginConfig
from .metrics import MetricsCollector

logger = logging.getLogger(__name__)

# Populated by inference-service trace after a single payload analysis pass.
_inference_payload_metrics: ContextVar[Optional[Dict[str, Any]]] = ContextVar(
    "inference_payload_metrics", default=None
)


def set_inference_payload_metrics(metrics: Dict[str, Any]) -> None:
    """Store payload metrics computed during inference tracing (one pass per request)."""
    _inference_payload_metrics.set(metrics)


def get_inference_payload_metrics() -> Optional[Dict[str, Any]]:
    """Peek at trace-computed payload metrics without clearing."""
    return _inference_payload_metrics.get()


def clear_inference_payload_metrics() -> None:
    """Clear trace-computed metrics after the HTTP request is done with them."""
    _inference_payload_metrics.set(None)


# Service types whose request bodies carry payload-size metrics worth
# extracting. Membership check is O(1). LLM is handled separately because its
# token counts come from the response (vLLM `usage` block), not the request.
_BODY_METRIC_SERVICES = frozenset({
    "tts", "translation", "asr", "ocr", "transliteration",
    "language_detection", "audio_lang_detection",
    "speaker_diarization", "language_diarization", "ner",
})

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

        # Run the actual handler. All observability work happens AFTER the
        # response is in hand so we never block the user.
        response = await call_next(request)
        duration = time.time() - start_time

        # LLM (chat / chat-completions): prefer usage captured during tracing;
        # otherwise buffer the response body once to read the vLLM `usage` block.
        trace_metrics = get_inference_payload_metrics()
        llm_prompt_tokens = 0
        llm_completion_tokens = 0
        llm_total_tokens = 0
        llm_model = ""
        if _has_llm_metrics(trace_metrics):
            llm_prompt_tokens = int(trace_metrics.get("llm_prompt_tokens") or 0)
            llm_completion_tokens = int(trace_metrics.get("llm_completion_tokens") or 0)
            llm_total_tokens = int(trace_metrics.get("llm_total_tokens") or 0)
            llm_model = str(trace_metrics.get("llm_model") or "")
        elif service_type == "llm":
            response, response_body_bytes = await self._buffer_response(response)
            (
                llm_prompt_tokens,
                llm_completion_tokens,
                llm_total_tokens,
                llm_model,
            ) = self._extract_llm_usage_from_body(response_body_bytes)

        # tenant_id comes from the gateway-injected X-Tenant-Id header (set by
        # auth-service /validate after verifying the bearer token; the gateway
        # forwards it upstream). HTTP header names are case-insensitive, so
        # this matches X-Tenant-Id / X-Tenant-ID / x-tenant-id.
        # service_id is populated during request handling by model-management.
        tenant_label = (request.headers.get("X-Tenant-Id") or "").strip() or "unknown"
        service_id = getattr(request.state, "service_id", "") or ""
        # LLM endpoints don't go through model-management; per spec the
        # model name echoed in the response acts as the service identifier.
        if service_type == "llm" and llm_model:
            service_id = llm_model

        # Fire-and-forget: parse the body and emit metrics WITHOUT blocking
        # the response. Holding the task in self._pending_tasks keeps it
        # alive — asyncio.create_task only keeps a weak reference.
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
        clear_inference_payload_metrics()

        return response

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

            # Request count + duration fire for every request, regardless of
            # whether we extracted a payload metric.
            self.metrics_collector.track_request(
                method=method,
                endpoint=path,
                status_code=status_code,
                duration=duration,
                tenant=tenant,
                service_id=service_id,
            )

            # LLM: token counts come from the inference engine's response
            # `usage` block (extracted in dispatch). Skipped for streaming
            # responses (no usage block).
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
        """Emit Prometheus payload metrics from a trace-computed snapshot."""
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
        # Drop Content-Length — Response recomputes it from the buffered body.
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
