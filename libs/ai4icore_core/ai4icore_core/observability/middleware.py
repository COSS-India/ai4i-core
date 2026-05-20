"""
Middleware for AI4ICore Observability Plugin

Handles request tracking, service detection, and metrics collection.
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
    "speaker_diarization", "language_diarization", "ner", "llm",
})

# Maps inference-service ``task_type`` payload values (case-insensitive)
# to the lowercase ``service_type`` identifier used internally by this
# middleware. The unified ``POST /api/v1/inference`` endpoint receives
# the model selector in the body, not the URL, so we refine the
# service_type post-call_next once the body is parsed.
_INFERENCE_TASK_TO_SERVICE_TYPE = {
    "nmt": "translation",
    "asr": "asr",
    "ocr": "ocr",
    "ner": "ner",
    "llm": "llm",
    "tts": "tts",
    "transliteration": "transliteration",
    "language_detection": "language_detection",
    "audio_lang_detection": "audio_lang_detection",
    "speaker_diarization": "speaker_diarization",
    "speaker_verification": "speaker_verification",
    "language_diarization": "language_diarization",
    "pii": "pii",
    "smr": "smr",
}


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

        # Unified inference-service endpoint: single POST /api/v1/inference where
        # the model selector lives in the body (`task_type`), not the URL.
        # service_type stays "unknown" until refined from the body post-call_next.
        # Request count/duration metrics still populate for every request;
        # only payload-size extraction depends on a real service_type.
        service_type = "unknown"
        is_unified_inference = (
            method == "POST"
            and path.rstrip("/").lower() == "/api/v1/inference"
        )
        needs_body = is_unified_inference

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
            is_unified_inference=is_unified_inference,
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
        is_unified_inference: bool,
        service_type: str,
        tenant: str,
        service_id: str,
        status_code: int,
        duration: float,
    ) -> None:
        """Parse request body and emit Prometheus metrics out-of-band."""
        try:
            # Unified inference endpoint refinement: the model selector lives
            # in the body, not the URL. Parse `task_type` (to map service_type
            # and refine the path label) and `config.service_id` (so the
            # service_id Prometheus label populates without needing a separate
            # middleware to copy it onto request.state).
            if is_unified_inference and body_bytes:
                try:
                    request_data = json.loads(body_bytes.decode('utf-8'))
                    raw_task = str(request_data.get('task_type') or '').strip().lower()
                    mapped = _INFERENCE_TASK_TO_SERVICE_TYPE.get(raw_task)
                    if mapped:
                        service_type = mapped
                        path = f"{path.rstrip('/')}/{raw_task}"
                        if self.config.debug:
                            logger.debug(
                                f"Unified inference: task_type={raw_task}, "
                                f"service_type={service_type}, refined path={path}"
                            )

                    # Pull service_id from `config.service_id` or `config.serviceId`
                    # — both spellings appear in inference-service docs/tests.
                    # Only override the existing service_id (from request.state)
                    # if the payload provides a non-empty value.
                    config_obj = request_data.get('config')
                    if isinstance(config_obj, dict):
                        payload_service_id = str(
                            config_obj.get('service_id')
                            or config_obj.get('serviceId')
                            or ''
                        ).strip()
                        if payload_service_id:
                            service_id = payload_service_id
                            if self.config.debug:
                                logger.debug(
                                    f"Unified inference: service_id={service_id} from payload"
                                )
                except Exception:
                    if self.config.debug:
                        logger.debug("Failed to parse unified inference body", exc_info=True)

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
            llm_tokens = 0

            if body_bytes and service_type in _BODY_METRIC_SERVICES:
                if service_type == "tts":
                    tts_characters = self._extract_input_characters(body_bytes)
                elif service_type == "translation":
                    translation_characters = self._extract_input_characters(body_bytes)
                elif service_type == "asr":
                    asr_audio_length = self._extract_asr_audio_length_from_body(body_bytes)
                elif service_type == "ocr":
                    ocr_characters = self._extract_ocr_characters_from_body(body_bytes)
                    ocr_image_size_kb = self._extract_ocr_image_size_kb_from_body(body_bytes)
                elif service_type == "transliteration":
                    transliteration_characters = self._extract_input_characters(body_bytes)
                elif service_type == "language_detection":
                    language_detection_characters = self._extract_input_characters(body_bytes)
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
                elif service_type == "llm":
                    llm_tokens = self._extract_llm_tokens_from_body(body_bytes)

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
                language_diarization_length, llm_tokens=llm_tokens, service_id=service_id,
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
        llm_tokens: int = 0,
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
                if llm_tokens > 0:
                    self.metrics_collector.track_llm_tokens(
                        model=service_id or "unknown",
                        tokens=llm_tokens,
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

        except Exception as e:
            if self.config.debug:
                logger.debug(f"Additional metrics tracking failed: {e}", exc_info=True)

    def _extract_input_characters(self, body_bytes: bytes) -> int:
        """Sum lengths of every ``source`` string in a request body.

        Supports both shapes:
        - direct: ``{"input": [{"source": "..."}, ...]}`` (TTS, translation, LLM)
        - pipeline-wrapped: ``{"inputData": {"input": [...]}}`` (transliteration, language_detection)
        """
        try:
            if not body_bytes:
                return 0
            data = json.loads(body_bytes.decode('utf-8'))
            items = data.get('input')
            if items is None:
                input_data = data.get('inputData')
                if isinstance(input_data, dict):
                    items = input_data.get('input')
            if not items:
                return 0
            return sum(
                len(item['source'])
                for item in items
                if isinstance(item, dict) and isinstance(item.get('source'), str)
            )
        except Exception:
            if self.config.debug:
                logger.debug("Failed to extract input characters from body", exc_info=True)
            return 0

    def _extract_ocr_characters_from_body(self, body_bytes: bytes) -> int:
        """Extract estimated character count from OCR request body.

        Supports both shapes:
        - direct: ``{"image": [{"imageContent": "base64..."}, ...]}`` (inference-service)
        - pipeline-wrapped: ``{"inputData": {"image": [...]}}`` (legacy pipeline)

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

            # Try root-level `image` (direct) first, then `inputData.image` (pipeline).
            images = request_data.get('image')
            if not isinstance(images, list):
                input_data = request_data.get('inputData')
                if isinstance(input_data, dict):
                    images = input_data.get('image')
            if not isinstance(images, list):
                return 0

            total_characters = 0
            for image_item in images:
                if not isinstance(image_item, dict):
                    continue
                if 'imageContent' in image_item:
                    content = image_item['imageContent']
                    if isinstance(content, str):
                        # Conservative estimate: ~0.5% of base64 chars become extracted text.
                        total_characters += len(content) // 200
                elif 'imageUri' in image_item and self.config.debug:
                    logger.debug("OCR imageUri detected; skipping download (would block event loop)")

            return total_characters
        except Exception:
            if self.config.debug:
                logger.debug("Failed to extract OCR characters", exc_info=True)
            return 0

    def _extract_llm_tokens_from_body(self, body_bytes: bytes) -> int:
        """Approximate LLM input token count from request body.

        Uses OpenAI's chars/4 rule of thumb. For exact tokenizer-aligned
        counts (billing-grade), the llm-service should emit the metric
        itself post-inference with the real tokenizer output.
        """
        return (self._extract_input_characters(body_bytes) + 3) // 4

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
