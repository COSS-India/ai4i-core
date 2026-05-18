"""
Middleware for AI4ICore Observability Plugin

Handles request tracking, service detection, and metrics collection.

Performance design
------------------
The middleware is structured so that the request is held up by observability
work as little as possible:

  * Pre-``call_next`` we only do work that downstream middleware/handlers
    *depend* on: a single JWT decode, populating ``request.state``, and
    seeding the tracing/logging context with tenant.
  * The request body is still buffered before ``call_next`` (Starlette needs
    that to replay it to the inner app), but it is NOT parsed there.
  * All payload-size calculations (token counts, character counts, audio
    length, image size, etc.) and Prometheus metric emission happen AFTER
    ``call_next`` in a fire-and-forget ``asyncio`` task, so they run
    concurrently with response streaming and never delay the response.
"""
import asyncio
import base64
import io
import json
import logging
import time
import wave
from typing import Any, Dict, Optional

import jwt
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from .config import PluginConfig
from .metrics import MetricsCollector

# Hoist optional integrations to module level so we pay the import cost
# once at startup, not on every request.
try:
    from opentelemetry import trace as _otel_trace
except Exception:  # pragma: no cover - tracing is optional
    _otel_trace = None

try:
    from ai4icore_core.logging.context import set_tenant_id as _set_tenant_id
except Exception:  # pragma: no cover - logging context is optional
    _set_tenant_id = None

logger = logging.getLogger(__name__)


# Service types whose request bodies carry payload-size metrics worth
# extracting. Membership check is O(1).
_BODY_METRIC_SERVICES = frozenset({
    "tts", "translation", "asr", "ocr", "transliteration",
    "language_detection", "audio_lang_detection", "speaker_verification",
    "speaker_diarization", "language_diarization", "ner",
})


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Middleware for tracking requests and collecting metrics."""

    def __init__(self, app, metrics_collector: Optional[MetricsCollector] = None,
                 config: Optional[PluginConfig] = None):
        """Initialize middleware."""
        super().__init__(app)
        self.metrics_collector = metrics_collector or MetricsCollector()
        self.config = config or PluginConfig()
        # asyncio.create_task only keeps a weak reference; hold strong refs
        # here so background metric tasks aren't GC'd before they finish.
        self._pending_tasks: "set[asyncio.Task[Any]]" = set()

    async def dispatch(self, request: Request, call_next):
        """Process request through middleware."""
        if not self.config.enabled:
            return await call_next(request)

        start_time = time.time()
        path = request.url.path
        method = request.method

        # Decode JWT (without verification) to extract tenant_id.
        decoded_token: Optional[Dict[str, Any]] = None
        auth_header = request.headers.get("authorization", "")
        if auth_header:
            decoded_token = self._decode_jwt_token(auth_header)

        tenant_id: Optional[str] = None
        if decoded_token is not None:
            tid = decoded_token.get("tenant_id")
            if tid not in (None, ""):
                tenant_id = str(tid)

        tenant_label = tenant_id if tenant_id else "unknown"

        # Downstream middlewares/handlers may read tenant_id off request.state.
        request.state.tenant_id = tenant_id

        # Seed tracing span with tenant so any spans started during request
        # handling are labeled correctly.
        if _otel_trace is not None:
            try:
                current_span = _otel_trace.get_current_span()
                if current_span:
                    current_span.set_attribute("tenant_id", tenant_label)
            except Exception:
                pass

        # Seed logging context so log records emitted during handling carry
        # tenant. The background metrics task does not need it (it passes
        # the tenant label in directly).
        if _set_tenant_id is not None:
            try:
                _set_tenant_id(tenant_id)
            except Exception:
                if self.config.debug:
                    logger.debug("Failed to set tenant in logging context", exc_info=True)

        # Detect service type up front (cheap string ops) so we know whether
        # we need to buffer the body for later metric extraction.
        service_type = self._detect_service_type(path)
        is_generic_pipeline = (
            method == "POST"
            and (path.endswith("/pipeline") or path == "/services/inference/pipeline")
            and "/pipeline/" not in path
        )
        needs_body = method == "POST" and (
            is_generic_pipeline or service_type in _BODY_METRIC_SERVICES
        )

        # Read (but do NOT parse) the body so it's available to the
        # background task. Starlette caches this on the request, so the
        # inner handler still sees the body normally.
        body_bytes: Optional[bytes] = None
        if needs_body:
            try:
                body_bytes = await request.body()
            except Exception:
                body_bytes = None
                if self.config.debug:
                    logger.debug("Failed to read request body for metrics", exc_info=True)

        if self.config.debug:
            logger.debug(
                f"Request: {method} {path} -> Service: {service_type}, "
                f"Tenant: {tenant_label}"
            )

        # --- Process request. Everything observability-related from here
        # runs AFTER the response is in hand. ---
        response = await call_next(request)
        duration = time.time() - start_time

        # service_id is resolved by the model-management middleware during
        # request handling.
        service_id = getattr(request.state, "service_id", "") or ""

        # Fire-and-forget: parse the body and emit metrics WITHOUT blocking
        # the response. Holding the task in self._pending_tasks keeps it
        # alive — asyncio.create_task only keeps a weak reference.
        task = asyncio.create_task(self._record_metrics(
            body_bytes=body_bytes,
            path=path,
            method=method,
            is_generic_pipeline=is_generic_pipeline,
            service_type=service_type,
            tenant=tenant_label,
            service_id=service_id,
            status_code=response.status_code,
            duration=duration,
        ))
        self._pending_tasks.add(task)
        task.add_done_callback(self._pending_tasks.discard)

        return response

    # ------------------------------------------------------------------
    # Background processing — runs AFTER the response is returned.
    # ------------------------------------------------------------------
    async def _record_metrics(
        self,
        body_bytes: Optional[bytes],
        path: str,
        method: str,
        is_generic_pipeline: bool,
        service_type: str,
        tenant: str,
        service_id: str,
        status_code: int,
        duration: float,
    ) -> None:
        """Parse request body and emit Prometheus metrics out-of-band."""
        try:
            # If the request hit the generic /pipeline endpoint, refine the
            # metric path label based on the taskType in the body. The route
            # has already been served — this only affects the metric label.
            if is_generic_pipeline and body_bytes:
                try:
                    request_data = json.loads(body_bytes.decode('utf-8'))
                    tasks = request_data.get('pipelineTasks') or []
                    if tasks:
                        task_type = tasks[0].get('taskType', '')
                        if task_type == 'txt-lang-detection':
                            path = path + '/txt-lang-detection'
                            service_type = 'language_detection'
                            if self.config.debug:
                                logger.debug(f"Detected txt-lang-detection in generic pipeline endpoint, refined path to: {path}")
                except Exception:
                    if self.config.debug:
                        logger.debug("Failed to parse pipeline body for taskType", exc_info=True)

            # Per-service payload metrics. Defaults of 0 mean unset values
            # contribute nothing if extraction is skipped or fails.
            tts_characters = 0
            translation_characters = 0
            asr_audio_length = 0.0
            ocr_characters = 0
            ocr_image_size_kb = 0.0
            transliteration_characters = 0
            language_detection_characters = 0
            audio_lang_detection_length = 0.0
            ner_tokens = 0
            speaker_verification_length = 0.0
            speaker_diarization_length = 0.0
            language_diarization_length = 0.0

            if body_bytes and service_type in _BODY_METRIC_SERVICES:
                if service_type == "tts":
                    tts_characters = self._extract_tts_characters_from_body(body_bytes)
                elif service_type == "translation":
                    translation_characters = self._extract_translation_characters_from_body(body_bytes)
                elif service_type == "asr":
                    asr_audio_length = self._extract_asr_audio_length_from_body(body_bytes)
                elif service_type == "ocr":
                    ocr_characters = self._extract_ocr_characters_from_body(body_bytes)
                    ocr_image_size_kb = self._extract_ocr_image_size_kb_from_body(body_bytes)
                elif service_type == "transliteration":
                    transliteration_characters = self._extract_transliteration_characters_from_body(body_bytes)
                elif service_type == "language_detection":
                    language_detection_characters = self._extract_language_detection_characters_from_body(body_bytes)
                elif service_type == "audio_lang_detection":
                    audio_lang_detection_length = self._extract_asr_audio_length_from_body(body_bytes)
                elif service_type == "speaker_verification":
                    speaker_verification_length = self._extract_asr_audio_length_from_body(body_bytes)
                elif service_type == "speaker_diarization":
                    speaker_diarization_length = self._extract_asr_audio_length_from_body(body_bytes)
                elif service_type == "language_diarization":
                    language_diarization_length = self._extract_asr_audio_length_from_body(body_bytes)
                elif service_type == "ner":
                    ner_tokens = self._extract_ner_tokens_from_body(body_bytes)

            if self.config.debug:
                logger.debug(f"Tracking metrics for endpoint: {path}, service_type: {service_type}")

            self.metrics_collector.track_request(
                method=method,
                endpoint=path,
                status_code=status_code,
                duration=duration,
                service_type=service_type,
                tenant=tenant,
                service_id=service_id,
            )

            self._track_additional_metrics(
                tenant, service_type, path, duration,
                tts_characters, translation_characters, asr_audio_length,
                ocr_characters, ocr_image_size_kb, transliteration_characters,
                language_detection_characters, audio_lang_detection_length,
                ner_tokens, speaker_verification_length, speaker_diarization_length,
                language_diarization_length, service_id=service_id,
            )
        except Exception:
            if self.config.debug:
                logger.debug("Background metrics recording failed", exc_info=True)

    def _decode_jwt_token(self, authorization_header: str) -> Optional[Dict[str, Any]]:
        """Decode JWT token from authorization header."""
        try:
            if not authorization_header.startswith("Bearer "):
                return None

            token = authorization_header[7:]  # Remove "Bearer " prefix

            # Decode without verification — we only need the tenant_id claim
            # for metric labeling, not authentication.
            decoded_token = jwt.decode(token, options={"verify_signature": False})

            return decoded_token
        except Exception as e:
            if self.config.debug:
                logger.debug(f"[TENANT_DEBUG] JWT decoding failed: {type(e).__name__}: {e}", exc_info=True)
            return None

    def _detect_service_type(self, path: str) -> str:
        """Detect service type from URL path."""
        path_lower = path.lower()

        # IMPORTANT: Check specific endpoints FIRST before generic patterns
        # This ensures specific endpoints are matched correctly and the full path is preserved in metrics

        # Dedicated text language detection endpoint (txt-lang-detection) - check FIRST
        if any(pattern in path_lower for pattern in ["/services/inference/txt-lang-detection", "/inference/txt-lang-detection", "/txt-lang-detection"]):
            return "language_detection"
        # Pipeline text language detection endpoint (txt-lang-detection) - check SECOND
        elif any(pattern in path_lower for pattern in ["/services/inference/pipeline/txt-lang-detection", "/services/inference/pipeline/txt-language-detection", "/pipeline/txt-lang-detection"]):
            return "language_detection"
        # Pipeline OCR endpoint
        elif any(pattern in path_lower for pattern in ["/services/inference/pipeline/ocr", "/pipeline/ocr"]):
            return "ocr"
        # Pipeline Transliteration endpoint
        elif any(pattern in path_lower for pattern in ["/services/inference/pipeline/transliteration", "/services/inference/pipeline/translation/transliteration", "/pipeline/transliteration", "/pipeline/translation/transliteration"]):
            return "transliteration"
        # Pipeline audio language detection endpoint
        elif any(pattern in path_lower for pattern in ["/services/inference/pipeline/audio-lang-detection", "/services/inference/pipeline/audio-language-detection", "/pipeline/audio-lang-detection"]):
            return "audio_lang_detection"
        # Pipeline speaker verification endpoint
        elif any(pattern in path_lower for pattern in ["/services/inference/pipeline/speaker-verification", "/pipeline/speaker-verification"]):
            return "speaker_verification"
        # Pipeline speaker diarization endpoint
        elif any(pattern in path_lower for pattern in ["/services/inference/pipeline/speaker-diarization", "/pipeline/speaker-diarization"]):
            return "speaker_diarization"
        # Pipeline language diarization endpoint
        elif any(pattern in path_lower for pattern in ["/services/inference/pipeline/language-diarization", "/pipeline/language-diarization"]):
            return "language_diarization"

        # Then check for generic service patterns (non-pipeline endpoints)
        elif any(pattern in path_lower for pattern in ["/translation", "/nmt", "/translate"]):
            return "translation"
        elif any(pattern in path_lower for pattern in ["/asr", "/transcribe", "/speech"]):
            return "asr"
        elif any(pattern in path_lower for pattern in ["/tts", "/synthesize"]):
            return "tts"
        elif any(pattern in path_lower for pattern in ["/ocr", "/text-recognition"]):
            return "ocr"
        elif any(pattern in path_lower for pattern in ["/transliteration", "/xlit", "/transliterate"]):
            return "transliteration"
        elif any(pattern in path_lower for pattern in ["/audio-lang-detection", "/audio-language-detection", "/audio-detect"]):
            return "audio_lang_detection"
        elif any(pattern in path_lower for pattern in ["/language-detection", "/lang-detect", "/detect-language"]):
            return "language_detection"
        elif any(pattern in path_lower for pattern in ["/language-diarization", "/language-diarization-compute-call"]):
            return "language_diarization"
        elif any(pattern in path_lower for pattern in ["/speaker-diarization", "/speaker-diarization-compute-call"]):
            return "speaker_diarization"
        elif any(pattern in path_lower for pattern in ["/ner", "/entity", "/entities"]):
            return "ner"
        elif any(pattern in path_lower for pattern in ["/speaker", "/speaker-enrollment", "/speaker-verification", "/speak"]):
            return "speaker_verification"
        elif any(pattern in path_lower for pattern in ["/llm", "/generate", "/chat", "/completion"]):
            return "llm"
        elif any(pattern in path_lower for pattern in ["/enterprise", "/health", "/metrics", "/config"]):
            return "enterprise"
        elif any(pattern in path_lower for pattern in ["/docs", "/openapi", "/redoc"]):
            return "documentation"
        else:
            return "unknown"

    def _track_additional_metrics(
        self,
        tenant: str,
        service_type: str,
        path: str,
        duration: float,
        tts_characters: int = 0,
        translation_characters: int = 0,
        asr_audio_length: float = 0,
        ocr_characters: int = 0,
        ocr_image_size_kb: float = 0.0,
        transliteration_characters: int = 0,
        language_detection_characters: int = 0,
        audio_lang_detection_length: float = 0,
        ner_tokens: int = 0,
        speaker_verification_length: float = 0,
        speaker_diarization_length: float = 0,
        language_diarization_length: float = 0,
        service_id: str = "",
    ):
        """Track additional metrics based on service type."""
        try:
            # Track component latency
            self.metrics_collector.track_component_latency(
                component=service_type,
                duration=duration,
                tenant=tenant,
            )

            # Track data processing based on service type
            if service_type == "llm":
                # Mock LLM token processing
                tokens = self._estimate_llm_tokens(path)
                self.metrics_collector.track_llm_tokens(
                    model="gpt-3.5-turbo",  # Mock model
                    tokens=tokens,
                    tenant=tenant,
                )
            elif service_type == "tts":
                if tts_characters > 0:
                    self.metrics_collector.track_tts_characters(
                        language="en",
                        characters=tts_characters,
                        tenant=tenant,
                        service_id=service_id,
                    )
            elif service_type == "translation":
                if translation_characters > 0:
                    self.metrics_collector.track_nmt_characters(
                        source_lang="en",
                        target_lang="hi",
                        characters=translation_characters,
                        tenant=tenant,
                        service_id=service_id,
                    )
            elif service_type == "asr":
                if asr_audio_length > 0:
                    self.metrics_collector.track_asr_audio_length(
                        language="en",
                        audio_seconds=asr_audio_length,
                        tenant=tenant,
                        service_id=service_id,
                    )
            elif service_type == "ocr":
                if ocr_characters > 0:
                    self.metrics_collector.track_ocr_characters(
                        characters=ocr_characters,
                        tenant=tenant,
                        service_id=service_id,
                    )
                if ocr_image_size_kb > 0:
                    self.metrics_collector.track_ocr_image_size(
                        image_size_kb=ocr_image_size_kb,
                        tenant=tenant,
                        service_id=service_id,
                    )
            elif service_type == "transliteration":
                if transliteration_characters > 0:
                    self.metrics_collector.track_transliteration_characters(
                        source_lang="en",
                        target_lang="hi",
                        characters=transliteration_characters,
                        tenant=tenant,
                        service_id=service_id,
                    )
            elif service_type == "language_detection":
                if language_detection_characters > 0:
                    self.metrics_collector.track_language_detection_characters(
                        characters=language_detection_characters,
                        tenant=tenant,
                        service_id=service_id,
                    )
            elif service_type == "audio_lang_detection":
                if audio_lang_detection_length > 0:
                    self.metrics_collector.track_audio_lang_detection_length(
                        audio_seconds=audio_lang_detection_length,
                        tenant=tenant,
                        service_id=service_id,
                    )
            elif service_type == "ner":
                if ner_tokens > 0:
                    self.metrics_collector.track_ner_tokens(
                        tokens=ner_tokens,
                        tenant=tenant,
                        service_id=service_id,
                    )
            elif service_type == "speaker_verification":
                if speaker_verification_length > 0:
                    self.metrics_collector.track_speaker_verification_length(
                        audio_seconds=speaker_verification_length,
                        tenant=tenant,
                        service_id=service_id,
                    )
            elif service_type == "speaker_diarization":
                if speaker_diarization_length > 0:
                    self.metrics_collector.track_speaker_diarization_length(
                        audio_seconds=speaker_diarization_length,
                        tenant=tenant,
                        service_id=service_id,
                    )
            elif service_type == "language_diarization":
                if language_diarization_length > 0:
                    self.metrics_collector.track_language_diarization_length(
                        audio_seconds=language_diarization_length,
                        tenant=tenant,
                        service_id=service_id,
                    )

            # Update SLA compliance (mock calculation)
            compliance = self._calculate_sla_compliance(service_type, duration)
            self.metrics_collector.update_sla_compliance(
                sla_type=f"{service_type}_availability",
                compliance_percent=compliance,
                tenant=tenant,
            )

        except Exception as e:
            if self.config.debug:
                logger.debug(f"Additional metrics tracking failed: {e}", exc_info=True)

    def _estimate_llm_tokens(self, path: str) -> int:
        """Estimate LLM tokens based on path."""
        # Mock estimation - in real implementation, this would analyze request content
        return 100  # Mock value

    def _extract_tts_characters_from_body(self, body_bytes: bytes) -> int:
        """Extract real character count from TTS request body."""
        try:
            if not body_bytes:
                return 0
            request_data = json.loads(body_bytes.decode('utf-8'))
            total_characters = 0
            if 'input' in request_data:
                for input_item in request_data['input']:
                    if 'source' in input_item:
                        total_characters += len(input_item['source'])
            return total_characters
        except Exception:
            if self.config.debug:
                logger.debug("Failed to extract TTS characters", exc_info=True)
            return 0

    def _extract_translation_characters_from_body(self, body_bytes: bytes) -> int:
        """Extract real character count from translation request body."""
        try:
            if not body_bytes:
                return 0
            request_data = json.loads(body_bytes.decode('utf-8'))
            total_characters = 0
            if 'input' in request_data:
                for input_item in request_data['input']:
                    if 'source' in input_item:
                        total_characters += len(input_item['source'])
            return total_characters
        except Exception:
            if self.config.debug:
                logger.debug("Failed to extract translation characters", exc_info=True)
            return 0

    def _extract_ocr_characters_from_body(self, body_bytes: bytes) -> int:
        """Extract estimated character count from OCR request body.

        Note: ``imageUri`` payloads are intentionally skipped — downloading
        the referenced image to estimate its size blocks the event loop
        (the original implementation used a synchronous ``httpx.get`` with
        a 5s timeout) and is not appropriate inside middleware. The same
        approach is used for ASR ``audioUri``.
        """
        try:
            if not body_bytes:
                return 0

            request_data = json.loads(body_bytes.decode('utf-8'))
            total_characters = 0

            # OCR uses pipeline format: {"inputData": {"image": [...]}, ...}
            if 'inputData' in request_data and 'image' in request_data['inputData']:
                for image_item in request_data['inputData']['image']:
                    if 'imageContent' in image_item:
                        content = image_item['imageContent']
                        # Conservative estimate: ~0.5% of base64 chars become extracted text.
                        estimated_chars = len(content) // 200
                        total_characters += estimated_chars
                    elif 'imageUri' in image_item and self.config.debug:
                        logger.debug("OCR imageUri detected; skipping download (would block event loop)")

            return total_characters
        except Exception:
            if self.config.debug:
                logger.debug("Failed to extract OCR characters", exc_info=True)
            return 0

    def _extract_transliteration_characters_from_body(self, body_bytes: bytes) -> int:
        """Extract real character count from transliteration request body."""
        try:
            if not body_bytes:
                return 0
            request_data = json.loads(body_bytes.decode('utf-8'))
            total_characters = 0
            # Support both direct `input` and pipeline `inputData.input` formats
            if 'input' in request_data:
                for input_item in request_data['input']:
                    if 'source' in input_item and isinstance(input_item['source'], str):
                        total_characters += len(input_item['source'])
            elif 'inputData' in request_data and 'input' in request_data['inputData']:
                for input_item in request_data['inputData']['input']:
                    if 'source' in input_item and isinstance(input_item['source'], str):
                        total_characters += len(input_item['source'])
            return total_characters
        except Exception:
            if self.config.debug:
                logger.debug("Failed to extract transliteration characters", exc_info=True)
            return 0

    def _extract_language_detection_characters_from_body(self, body_bytes: bytes) -> int:
        """Extract real character count from language detection request body."""
        try:
            if not body_bytes:
                return 0
            request_data = json.loads(body_bytes.decode('utf-8'))
            total_characters = 0
            # Support both direct `input` and pipeline `inputData.input` formats
            if 'input' in request_data:
                for input_item in request_data['input']:
                    if 'source' in input_item and isinstance(input_item['source'], str):
                        total_characters += len(input_item['source'])
            elif 'inputData' in request_data and 'input' in request_data['inputData']:
                for input_item in request_data['inputData']['input']:
                    if 'source' in input_item and isinstance(input_item['source'], str):
                        total_characters += len(input_item['source'])
            return total_characters
        except Exception:
            if self.config.debug:
                logger.debug("Failed to extract language detection characters", exc_info=True)
            return 0

    def _extract_ner_tokens_from_body(self, body_bytes: bytes) -> int:
        """Extract real token (word) count from NER request body."""
        try:
            if not body_bytes:
                return 0
            request_data = json.loads(body_bytes.decode('utf-8'))
            total_tokens = 0
            if 'input' in request_data:
                for input_item in request_data['input']:
                    if 'source' in input_item:
                        total_tokens += len(input_item['source'].split())
            return total_tokens
        except Exception:
            if self.config.debug:
                logger.debug("Failed to extract NER tokens", exc_info=True)
            return 0

    def _extract_asr_audio_length_from_body(self, body_bytes: bytes) -> float:
        """Extract real audio length in seconds from ASR request body."""
        try:
            if not body_bytes:
                return 0.0
            request_data = json.loads(body_bytes.decode('utf-8'))
            total_audio_length = 0.0

            # Standard ASR format: {"audio": [...], "config": {...}}
            audio_list = request_data.get('audio')
            # Pipeline format: {"inputData": {"audio": [...]}, ...}
            if audio_list is None:
                input_data = request_data.get('inputData')
                if isinstance(input_data, dict):
                    audio_list = input_data.get('audio')

            if not audio_list:
                if self.config.debug:
                    logger.debug(f"ASR request structure not recognized. Keys: {list(request_data.keys())}")
                return 0.0

            for audio_item in audio_list:
                if 'audioContent' in audio_item:
                    total_audio_length += self._calculate_audio_length_from_base64(audio_item['audioContent'])
                elif 'audioUri' in audio_item and self.config.debug:
                    logger.debug("audioUri detected but audio length cannot be calculated from URI without downloading file")

            return total_audio_length
        except Exception:
            if self.config.debug:
                logger.debug("Failed to extract ASR audio length", exc_info=True)
            return 0.0

    def _calculate_audio_length_from_base64(self, base64_audio: str) -> float:
        """Calculate audio length in seconds from base64 encoded audio."""
        try:
            audio_data = base64.b64decode(base64_audio)
            audio_buffer = io.BytesIO(audio_data)
            with wave.open(audio_buffer, 'rb') as wav_file:
                frames = wav_file.getnframes()
                sample_rate = wav_file.getframerate()
                return frames / float(sample_rate)
        except Exception:
            # Fallback: estimate from raw size (16-bit @ 16kHz ≈ 32KB/s)
            try:
                audio_data = base64.b64decode(base64_audio)
                return len(audio_data) / 32000
            except Exception:
                return 0.0

    def _extract_ocr_image_size_kb_from_body(self, body_bytes: bytes) -> float:
        """Extract image payload size in KB from OCR request body."""
        try:
            if not body_bytes:
                return 0.0

            request_data = json.loads(body_bytes.decode('utf-8'))
            total_size_kb = 0.0

            # Direct OCR format
            if 'image' in request_data:
                for image_item in request_data['image']:
                    if 'imageContent' in image_item:
                        total_size_kb += len(image_item['imageContent']) / 1024

            # Pipeline format
            if 'inputData' in request_data and 'image' in request_data['inputData']:
                for image_item in request_data['inputData']['image']:
                    if 'imageContent' in image_item:
                        total_size_kb += len(image_item['imageContent']) / 1024

            return total_size_kb
        except Exception:
            if self.config.debug:
                logger.debug("Failed to extract OCR image size", exc_info=True)
            return 0.0

    def _calculate_sla_compliance(self, service_type: str, duration: float) -> float:
        """Calculate SLA compliance based on service type and duration."""
        # Mock SLA compliance calculation
        if service_type == "llm":
            return 99.5 if duration < 2.0 else 95.0
        elif service_type == "tts":
            return 99.8 if duration < 1.0 else 97.0
        elif service_type == "translation":
            return 99.9 if duration < 0.5 else 98.0
        elif service_type == "asr":
            return 99.7 if duration < 1.5 else 96.0
        elif service_type == "ocr":
            return 99.8 if duration < 1.0 else 97.0
        elif service_type == "transliteration":
            return 99.9 if duration < 0.5 else 98.0
        elif service_type == "language_detection":
            return 99.9 if duration < 0.3 else 98.5
        elif service_type == "audio_lang_detection":
            return 99.7 if duration < 1.5 else 96.0
        elif service_type == "ner":
            return 99.8 if duration < 0.8 else 97.5
        elif service_type == "speaker_verification":
            return 99.6 if duration < 2.0 else 95.5
        elif service_type == "speaker_diarization":
            return 99.5 if duration < 3.0 else 95.0
        elif service_type == "language_diarization":
            return 99.6 if duration < 2.5 else 95.5
        else:
            return 99.0
