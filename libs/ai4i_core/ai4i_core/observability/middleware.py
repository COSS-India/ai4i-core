"""
Middleware for AI4ICore Observability Plugin.

Handles request tracking, path-based service detection, and Prometheus metric
emission. Tenant is read from the gateway-injected ``X-Tenant-Id`` header
(set by ``auth-service /validate``) — this middleware does NOT decode JWTs and
does NOT open OpenTelemetry spans.
"""
import asyncio
import base64
import io
import json
import logging
import re
import time
import wave
from typing import Any, Dict, Optional, Tuple

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .config import PluginConfig
from .metrics import MetricsCollector

logger = logging.getLogger(__name__)


# Service types whose request bodies carry payload-size metrics worth
# extracting. Membership check is O(1). LLM is handled separately because its
# token counts come from the response (vLLM `usage` block), not the request.
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

        # Only read the body for POSTs to inference endpoints — that's the
        # only place a body carries payload-size metrics worth extracting.
        body_bytes: Optional[bytes] = None
        if method == "POST" and _INFERENCE_PATH_RE.search(path):
            try:
                body_bytes = await request.body()
            except Exception:
                body_bytes = None
                if self.config.debug:
                    logger.debug("Failed to read request body for metrics", exc_info=True)

        if self.config.debug:
            logger.debug(f"Request: {method} {path} -> service_type={service_type}")

        # Run the actual handler. All observability work happens AFTER the
        # response is in hand so we never block the user.
        response = await call_next(request)
        duration = time.time() - start_time

        # LLM (chat / chat-completions): the route always returns a plain
        # JSONResponse, but Starlette's BaseHTTPMiddleware wraps it so the
        # body is only readable by draining `body_iterator` (which destroys
        # the original). Buffer once, rebuild the response, and pull the
        # `usage` block (prompt/completion/total tokens + the model name).
        llm_prompt_tokens = 0
        llm_completion_tokens = 0
        llm_total_tokens = 0
        llm_model = ""
        if service_type == "llm":
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
        # service_id is set on request.state by the route handler for LLM
        # (from payload serviceId before proxy_traced is called) and by the
        # orchestrator for Triton services. Falls back to empty string.
        service_id = getattr(request.state, "service_id", "") or ""

        # Fire-and-forget: parse the body and emit metrics WITHOUT blocking
        # the response. Holding the task in self._pending_tasks keeps it
        # alive — asyncio.create_task only keeps a weak reference.
        task = asyncio.create_task(self._record_metrics(
            body_bytes=body_bytes,
            path=path,
            method=method,
            service_type=service_type,
            tenant=tenant_label,
            service_id=service_id,
            status_code=response.status_code,
            duration=duration,
            llm_prompt_tokens=llm_prompt_tokens,
            llm_completion_tokens=llm_completion_tokens,
            llm_total_tokens=llm_total_tokens,
            llm_model=llm_model,
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
        llm_prompt_tokens: int = 0,
        llm_completion_tokens: int = 0,
        llm_total_tokens: int = 0,
        llm_model: str = "",
    ) -> None:
        """Parse request body once and emit Prometheus metrics out-of-band."""
        try:
            # Parse the body ONCE; reuse the dict for every extractor.
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
            # whether we extracted a payload metric.
            self.metrics_collector.track_request(
                method=method,
                endpoint=path,
                status_code=status_code,
                duration=duration,
                tenant=tenant,
                service_id=service_id,
                model=(llm_model or "unknown") if service_type == "llm" else "",
            )

            # LLM: token counts come from the inference engine's response
            # `usage` block (extracted in dispatch). Skipped for streaming
            # responses (no usage block).
            if service_type == "llm" and (
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

            if isinstance(request_data, dict) and service_type in _BODY_METRIC_SERVICES:
                self._track_payload_metrics(
                    request_data=request_data,
                    service_type=service_type,
                    tenant=tenant,
                    service_id=service_id,
                )
        except Exception:
            if self.config.debug:
                logger.debug("Background metrics recording failed", exc_info=True)

    def _track_payload_metrics(
        self,
        request_data: Dict[str, Any],
        service_type: str,
        tenant: str,
        service_id: str,
    ) -> None:
        """Dispatch to per-service payload extractors using the already-parsed body."""
        source_lang, target_lang = self._extract_languages(request_data)
        try:
            if service_type == "tts":
                chars = self._extract_input_characters(request_data)
                if chars > 0:
                    self.metrics_collector.track_tts_characters(
                        language=source_lang,
                        characters=chars,
                        tenant=tenant,
                        service_id=service_id,
                    )
            elif service_type == "translation":
                chars = self._extract_input_characters(request_data)
                if chars > 0:
                    self.metrics_collector.track_nmt_characters(
                        source_lang=source_lang,
                        target_lang=target_lang,
                        characters=chars,
                        tenant=tenant,
                        service_id=service_id,
                    )
            elif service_type == "asr":
                seconds = self._extract_asr_audio_length(request_data)
                if seconds > 0:
                    self.metrics_collector.track_asr_audio_length(
                        language=source_lang,
                        audio_seconds=seconds,
                        tenant=tenant,
                        service_id=service_id,
                    )
            elif service_type == "ocr":
                chars = self._extract_ocr_characters(request_data)
                if chars > 0:
                    self.metrics_collector.track_ocr_characters(
                        characters=chars,
                        tenant=tenant,
                        service_id=service_id,
                    )
                kb = self._extract_ocr_image_size_kb(request_data)
                if kb > 0:
                    self.metrics_collector.track_ocr_image_size(
                        image_size_kb=kb,
                        tenant=tenant,
                        service_id=service_id,
                    )
            elif service_type == "transliteration":
                chars = self._extract_input_characters(request_data)
                if chars > 0:
                    self.metrics_collector.track_transliteration_characters(
                        source_lang=source_lang,
                        target_lang=target_lang,
                        characters=chars,
                        tenant=tenant,
                        service_id=service_id,
                    )
            elif service_type == "language_detection":
                chars = self._extract_input_characters(request_data)
                if chars > 0:
                    self.metrics_collector.track_language_detection_characters(
                        characters=chars,
                        tenant=tenant,
                        service_id=service_id,
                    )
            elif service_type == "audio_lang_detection":
                seconds = self._extract_asr_audio_length(request_data)
                if seconds > 0:
                    self.metrics_collector.track_audio_lang_detection_length(
                        audio_seconds=seconds,
                        tenant=tenant,
                        service_id=service_id,
                    )
            elif service_type == "speaker_diarization":
                seconds = self._extract_asr_audio_length(request_data)
                if seconds > 0:
                    self.metrics_collector.track_speaker_diarization_length(
                        audio_seconds=seconds,
                        tenant=tenant,
                        service_id=service_id,
                    )
            elif service_type == "language_diarization":
                seconds = self._extract_asr_audio_length(request_data)
                if seconds > 0:
                    self.metrics_collector.track_language_diarization_length(
                        audio_seconds=seconds,
                        tenant=tenant,
                        service_id=service_id,
                    )
            elif service_type == "ner":
                tokens = self._extract_ner_tokens(request_data)
                if tokens > 0:
                    self.metrics_collector.track_ner_tokens(
                        tokens=tokens,
                        tenant=tenant,
                        service_id=service_id,
                    )
        except Exception:
            if self.config.debug:
                logger.debug("Per-service metric extraction failed", exc_info=True)

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
    def _extract_input_characters(request_data: Dict[str, Any]) -> int:
        """Sum lengths of ``source`` strings under ``input[]`` (or ``inputData.input[]``)."""
        items = request_data.get("input")
        if items is None:
            inp = request_data.get("inputData")
            if isinstance(inp, dict):
                items = inp.get("input")
        if not isinstance(items, list):
            return 0
        return sum(
            len(item["source"])
            for item in items
            if isinstance(item, dict) and isinstance(item.get("source"), str)
        )

    @staticmethod
    def _extract_ner_tokens(request_data: Dict[str, Any]) -> int:
        """Word count across ``input[*].source``."""
        items = request_data.get("input")
        if not isinstance(items, list):
            return 0
        total = 0
        for item in items:
            if isinstance(item, dict):
                src = item.get("source")
                if isinstance(src, str):
                    total += len(src.split())
        return total

    def _extract_asr_audio_length(self, request_data: Dict[str, Any]) -> float:
        """Audio length in seconds from base64-encoded ``audio[*].audioContent``.

        Tolerates both ``audio[]`` (direct) and ``inputData.audio[]`` shapes.
        ``audioUri`` payloads are intentionally skipped — fetching would block
        the event loop.
        """
        audio_list = request_data.get("audio")
        if audio_list is None:
            inp = request_data.get("inputData")
            if isinstance(inp, dict):
                audio_list = inp.get("audio")
        if not isinstance(audio_list, list):
            return 0.0
        total = 0.0
        for item in audio_list:
            if not isinstance(item, dict):
                continue
            content = item.get("audioContent")
            if isinstance(content, str):
                total += self._calculate_audio_length_from_base64(content)
            elif "audioUri" in item and self.config.debug:
                logger.debug("audioUri detected — skipping (would block event loop)")
        return total

    def _extract_ocr_characters(self, request_data: Dict[str, Any]) -> int:
        """Conservative estimate of extracted characters from ``image[*].imageContent``.

        Heuristic: ~0.5% of the base64-encoded length becomes extracted text.
        """
        images = request_data.get("image")
        if not isinstance(images, list):
            return 0
        total = 0
        for item in images:
            if not isinstance(item, dict):
                continue
            content = item.get("imageContent")
            if isinstance(content, str):
                total += len(content) // 200
            elif "imageUri" in item and self.config.debug:
                logger.debug("OCR imageUri detected — skipping download")
        return total

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

    @staticmethod
    def _calculate_audio_length_from_base64(base64_audio: str) -> float:
        """Audio length in seconds from base64-encoded audio."""
        try:
            audio_data = base64.b64decode(base64_audio)
            with wave.open(io.BytesIO(audio_data), "rb") as wav_file:
                return wav_file.getnframes() / float(wav_file.getframerate())
        except Exception:
            # Fallback: estimate from raw size (16-bit @ 16kHz ≈ 32 KB/s).
            try:
                return len(base64.b64decode(base64_audio)) / 32000
            except Exception:
                return 0.0

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
