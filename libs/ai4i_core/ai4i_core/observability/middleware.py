"""
Middleware for AI4ICore Observability Plugin.

Handles request tracking, path-based service detection, and Prometheus metric
emission. Tenant is read from the gateway-injected ``X-Tenant-Id`` header
(set by ``auth-service /validate``) — this middleware does NOT decode JWTs and
does NOT open OpenTelemetry spans.

Unit counts (characters/audio-minutes/images/tokens) are NOT re-derived here.
They're computed exactly once by the request handler (task_service.py /
llm_service.py, via trace/span_attributes.py) — the same count already used
to bill the request and attached to the ai-inference OTel span. Orchestrator
.route_inference (Triton) and the LLM chat route mirror that single value
onto ``request.state.billed_*``; this middleware only reads it, so Prometheus
can never disagree with what was actually billed.
"""
import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, Optional, Tuple

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from .config import PluginConfig
from .metrics import MetricsCollector

logger = logging.getLogger(__name__)


# Service types whose request bodies carry language labels (source/target)
# worth extracting for metric labeling. Membership check is O(1). LLM is
# handled separately — no source/target language labels apply.
_BODY_METRIC_SERVICES = frozenset({
    "tts", "translation", "asr", "ocr", "transliteration",
    "language_detection", "audio_lang_detection",
    "speaker_diarization", "language_diarization", "ner",
})

# Body parsing is gated on the request path — only inference endpoints carry
# the structured payloads we extract from. Matches `/inference` as a path
# segment (followed by `/` or end-of-path), so it picks up both the unified
# `/api/v1/inference` endpoint and dedicated `…/nmt/inference` style paths.
_INFERENCE_PATH_RE = re.compile(r"/inference(?:/|$)")


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

        # Only read the body for POSTs to inference endpoints — needed for
        # language labels (source/target), NOT for unit counts anymore
        # (those come from request.state.billed_* below).
        body_bytes: Optional[bytes] = None
        if method == "POST" and _INFERENCE_PATH_RE.search(path) and service_type in _BODY_METRIC_SERVICES:
            try:
                body_bytes = await request.body()
            except Exception:
                body_bytes = None
                if self.config.debug:
                    logger.debug("Failed to read request body for metrics", exc_info=True)

        if self.config.debug:
            logger.debug(f"Request: {method} {path} -> service_type={service_type}")

        # Run the actual handler. All observability work happens AFTER the
        # response is in hand so we never block the user. No response-body
        # buffering needed anymore — billed_* already carries what we'd have
        # re-parsed the response for.
        response = await call_next(request)
        duration = time.time() - start_time

        # tenant_id comes from the gateway-injected X-Tenant-Id header (set by
        # auth-service /validate after verifying the bearer token; the gateway
        # forwards it upstream). HTTP header names are case-insensitive, so
        # this matches X-Tenant-Id / X-Tenant-ID / x-tenant-id.
        # service_id is populated during request handling by model-management.
        tenant_label = (request.headers.get("X-Tenant-Id") or "").strip() or "unknown"
        # service_id is set on request.state by the route handler for LLM
        # (from payload serviceId before proxy_traced is called) and by the
        # orchestrator for Triton services. Falls back to empty string.
        service_id = getattr(request.state, "service_id", "") or ""

        # The single billed count — set by orchestrator.route_inference
        # (Triton) or the LLM chat route, from the same computation used for
        # billing and the OpenSearch trace. None means the handler never set
        # it (e.g. a non-inference path, or an error before billing ran).
        billed_input = getattr(request.state, "billed_input", None)
        billed_output = getattr(request.state, "billed_output", None)
        billed_model = getattr(request.state, "billed_model", "") or ""

        # Fire-and-forget: emit metrics WITHOUT blocking the response.
        # Holding the task in self._pending_tasks keeps it alive —
        # asyncio.create_task only keeps a weak reference.
        task = asyncio.create_task(self._record_metrics(
            body_bytes=body_bytes,
            path=path,
            method=method,
            service_type=service_type,
            tenant=tenant_label,
            service_id=service_id,
            status_code=response.status_code,
            duration=duration,
            billed_input=billed_input,
            billed_output=billed_output,
            billed_model=billed_model,
        ))
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)

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
        body_bytes: Optional[bytes],
        path: str,
        method: str,
        service_type: str,
        tenant: str,
        service_id: str,
        status_code: int,
        duration: float,
        billed_input: Optional[float] = None,
        billed_output: Optional[float] = None,
        billed_model: str = "",
    ) -> None:
        """Emit Prometheus metrics out-of-band, using the already-billed count."""
        try:
            # Parsed only for language labels (source/target) now — unit
            # counts come from billed_input/billed_output, not this body.
            request_data: Optional[Dict[str, Any]] = None
            if body_bytes:
                try:
                    request_data = json.loads(body_bytes.decode("utf-8"))
                except Exception:
                    if self.config.debug:
                        logger.debug("Failed to parse inference body", exc_info=True)
                    request_data = None

            # Both `service_id` and `serviceId` appear in inference payloads.
            # Only override the request-state value when the payload provides
            # a non-empty one. (LLM endpoints already got service_id=model
            # from the caller — do not re-override from the request body.)
            if isinstance(request_data, dict) and service_type != "llm":
                cfg = request_data.get("config")
                if isinstance(cfg, dict):
                    payload_service_id = str(
                        cfg.get("service_id") or cfg.get("serviceId") or ""
                    ).strip()
                    if payload_service_id:
                        service_id = payload_service_id

            # Request count + duration fire for every request, regardless of
            # whether a billed unit was recorded.
            self.metrics_collector.track_request(
                method=method,
                endpoint=path,
                status_code=status_code,
                duration=duration,
                tenant=tenant,
                service_id=service_id,
            )

            # Non-2xx or no billed_* set (e.g. a non-inference path, or the
            # handler zeroed counts on failure — see trace/request_span.py
            # ``_zero_tokens``) — skip rather than emit a misleading 0.
            if status_code >= 400 or billed_input is None:
                return

            if service_type == "llm":
                if billed_input or billed_output:
                    self.metrics_collector.track_llm_tokens(
                        model=billed_model or "unknown",
                        prompt_tokens=billed_input,
                        completion_tokens=billed_output or 0,
                        total_tokens=billed_input + (billed_output or 0),
                        tenant=tenant,
                        service_id=service_id,
                        endpoint=path,
                    )
                return

            if billed_input > 0:
                source_lang, target_lang = (
                    self._extract_languages(request_data)
                    if isinstance(request_data, dict) else ("", "")
                )
                self._track_payload_metrics(
                    service_type=service_type,
                    billed_input=billed_input,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    tenant=tenant,
                    service_id=service_id,
                )

            # OCR's payload size (KB) is a size metric, not a unit count —
            # orthogonal to billing, so it still comes from the request body.
            if service_type == "ocr" and isinstance(request_data, dict):
                kb = self._extract_ocr_image_size_kb(request_data)
                if kb > 0:
                    self.metrics_collector.track_ocr_image_size(
                        image_size_kb=kb, tenant=tenant, service_id=service_id,
                    )
        except Exception:
            if self.config.debug:
                logger.debug("Background metrics recording failed", exc_info=True)

    def _track_payload_metrics(
        self,
        service_type: str,
        billed_input: float,
        source_lang: str,
        target_lang: str,
        tenant: str,
        service_id: str,
    ) -> None:
        """Dispatch billed_input (the single count already used for billing
        and the OpenSearch trace — see trace/span_attributes.py) to the
        matching Prometheus metric for this service_type.

        billed_input's unit depends on service_type's inference_types.yaml
        entry: characters (tts/translation/transliteration/language_detection/
        ner), audio minutes (asr/audio_lang_detection/*_diarization,
        converted to seconds below to match the histograms' existing unit),
        or images (ocr).
        """
        try:
            if service_type == "tts":
                self.metrics_collector.track_tts_characters(
                    language=source_lang, characters=billed_input,
                    tenant=tenant, service_id=service_id,
                )
            elif service_type == "translation":
                self.metrics_collector.track_nmt_characters(
                    source_lang=source_lang, target_lang=target_lang,
                    characters=billed_input, tenant=tenant, service_id=service_id,
                )
            elif service_type == "asr":
                self.metrics_collector.track_asr_audio_length(
                    language=source_lang, audio_seconds=billed_input * 60.0,
                    tenant=tenant, service_id=service_id,
                )
            elif service_type == "ocr":
                # billed_input is an image COUNT (inference_types.yaml unit:
                # images), not a character estimate — track_ocr_characters is
                # repurposed to carry the real billed unit instead of the
                # byte-size heuristic it used to compute independently.
                self.metrics_collector.track_ocr_characters(
                    characters=billed_input, tenant=tenant, service_id=service_id,
                )
            elif service_type == "transliteration":
                self.metrics_collector.track_transliteration_characters(
                    source_lang=source_lang, target_lang=target_lang,
                    characters=billed_input, tenant=tenant, service_id=service_id,
                )
            elif service_type == "language_detection":
                self.metrics_collector.track_language_detection_characters(
                    characters=billed_input, tenant=tenant, service_id=service_id,
                )
            elif service_type == "audio_lang_detection":
                self.metrics_collector.track_audio_lang_detection_length(
                    audio_seconds=billed_input * 60.0, tenant=tenant, service_id=service_id,
                )
            elif service_type == "speaker_diarization":
                self.metrics_collector.track_speaker_diarization_length(
                    audio_seconds=billed_input * 60.0, tenant=tenant, service_id=service_id,
                )
            elif service_type == "language_diarization":
                self.metrics_collector.track_language_diarization_length(
                    audio_seconds=billed_input * 60.0, tenant=tenant, service_id=service_id,
                )
            elif service_type == "ner":
                # billed_input is a CHARACTER count (inference_types.yaml
                # unit: characters), not a word count — track_ner_tokens
                # previously computed len(source.split()) independently;
                # it now carries the same character count billing uses.
                self.metrics_collector.track_ner_tokens(
                    tokens=billed_input, tenant=tenant, service_id=service_id,
                )
        except Exception:
            if self.config.debug:
                logger.debug("Per-service metric emission failed", exc_info=True)

    # ------------------------------------------------------------------
    # Pure extractors — operate on the already-parsed request_data dict.
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_languages(request_data: Dict[str, Any]) -> Tuple[str, str]:
        """Return (source_language, target_language) from ``config.language``.

        Empty strings when absent — Prometheus accepts "" label values, and
        we explicitly want no hardcoded defaults like ``en``/``hi``.
        """
        cfg = request_data.get("config")
        if not isinstance(cfg, dict):
            return "", ""
        lang = cfg.get("language")
        if not isinstance(lang, dict):
            return "", ""
        src = str(lang.get("sourceLanguage") or "").strip()
        tgt = str(lang.get("targetLanguage") or "").strip()
        return src, tgt

    @staticmethod
    def _extract_ocr_image_size_kb(request_data: Dict[str, Any]) -> float:
        """Image payload size in KB, corrected for base64 inflation.

        base64 inflates the underlying bytes by ~4/3, so the decoded payload
        is roughly ``len(content) * 3 / 4`` bytes. Using the raw base64 length
        over-reports by ~33%.
        """
        images = request_data.get("image")
        if not isinstance(images, list):
            return 0.0
        total_kb = 0.0
        for item in images:
            if not isinstance(item, dict):
                continue
            content = item.get("imageContent")
            if isinstance(content, str):
                total_kb += (len(content) * 3 / 4) / 1024
        return total_kb

