"""
Metrics collection for AI4ICore Observability Plugin.

Per-request Prometheus metrics labeled by tenant, service_id, and technical
attributes (method, endpoint, language, etc.). System-level metrics
(CPU, memory, host stats) are intentionally NOT collected here — that is
node_exporter's responsibility.
"""

from prometheus_client import (
    Counter,
    Histogram,
    CollectorRegistry,
    generate_latest,
)


class MetricsCollector:
    """Metrics collector for AI4ICore Observability."""

    def __init__(self):
        self.registry = CollectorRegistry()
        self._init_metrics()

    def _init_metrics(self):
        """Initialize Prometheus metrics."""
        # Request metrics
        # `model_id` is the Model Registry's stable identifier for the model
        # backing the service (platform-core-service's mm_models.model_id,
        # surfaced to inference-service as `modelId` in the MMS service
        # lookup response — see InferenceServerResolver._normalize_mms_response).
        # Unlike `service_id` (the client-supplied, renameable service name)
        # or `model` (the upstream engine's own echoed model name, LLM-only
        # and absent on failures), model_id is immutable and shared across
        # every service backed by the same registry model — added so
        # metering can aggregate/filter by model identity without a
        # best-effort DB join on service_id alone. Empty string when the
        # service/model couldn't be resolved (e.g. before MMS resolution
        # completes, or resolution failed).
        self.enterprise_requests_total = Counter(
            "telemetry_obsv_requests_total",
            "Total enterprise requests",
            ["method", "endpoint", "status_code", "tenant", "service_id", "model_id"],
            registry=self.registry,
        )

        self.enterprise_request_duration = Histogram(
            "telemetry_obsv_request_duration_seconds",
            "Enterprise request duration",
            ["method", "endpoint", "tenant", "service_id", "model_id"],
            registry=self.registry,
        )

        # LLM token tracking — observations come from the inference engine's
        # `usage` block (vLLM / OpenAI-compatible response shape). One request
        # produces up to three observations (token_type=prompt|completion|total)
        # so dashboards can break down by either dimension. The `endpoint`
        # label lets queries distinguish e.g. /chat vs /chat/completions volumes.
        # `model` (upstream-echoed model name) and `model_id` (Registry
        # identity, see above) are deliberately both kept — they answer
        # different questions and neither substitutes for the other.
        self.enterprise_llm_tokens_processed = Histogram(
            "telemetry_obsv_llm_tokens_processed",
            "LLM tokens processed per request, as reported by the inference engine (vLLM 'usage' block)",
            ["model", "model_id", "tenant", "service_id", "endpoint", "token_type"],
            buckets=(10, 50, 100, 250, 500, 1000, 2500, 5000, 10000, 25000, 50000, 100000, float("inf")),
            registry=self.registry,
        )

        # TTS character tracking (Histogram for percentile calculations)
        self.enterprise_tts_characters_synthesized = Histogram(
            "telemetry_obsv_tts_characters_synthesized",
            "TTS characters synthesized per request",
            ["language", "tenant", "service_id"],
            buckets=(10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, float("inf")),
            registry=self.registry,
        )

        # NMT character tracking (Histogram for percentile calculations)
        self.enterprise_nmt_characters_translated = Histogram(
            "telemetry_obsv_nmt_characters_translated",
            "NMT characters translated per request",
            ["source_language", "target_language", "tenant", "service_id"],
            buckets=(10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, float("inf")),
            registry=self.registry,
        )

        # ASR audio length tracking (Histogram for percentile calculations)
        self.enterprise_asr_audio_minutes_processed = Histogram(
            "telemetry_obsv_asr_audio_minutes_processed",
            "ASR audio minutes processed per request",
            ["language", "tenant", "service_id"],
            buckets=(0.017, 0.083, 0.167, 0.5, 0.833, 1, 2, 5, 10, 30, 60, float("inf")),
            registry=self.registry,
        )

        # OCR tracking (Histogram for percentile calculations). Renamed from
        # telemetry_obsv_ocr_characters_processed — this carries an image
        # COUNT, not a character count (billed_input's unit for OCR is images,
        # per inference_types.yaml); the old name silently meant something
        # different pre-rename, so any external dashboard/alert needs updating.
        self.enterprise_ocr_images_processed = Histogram(
            "telemetry_obsv_ocr_images_processed",
            "OCR images processed per request",
            ["tenant", "service_id"],
            buckets=(1, 2, 3, 5, 10, 20, 50, 100, float("inf")),
            registry=self.registry,
        )

        # Transliteration character tracking
        self.enterprise_transliteration_characters_processed = Histogram(
            "telemetry_obsv_transliteration_characters_processed",
            "Transliteration characters processed per request",
            ["source_language", "target_language", "tenant", "service_id"],
            buckets=(10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, float("inf")),
            registry=self.registry,
        )

        # Language detection character tracking
        self.enterprise_language_detection_characters_processed = Histogram(
            "telemetry_obsv_language_detection_characters_processed",
            "Language detection characters processed per request",
            ["tenant", "service_id"],
            buckets=(10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, float("inf")),
            registry=self.registry,
        )

        # Audio language detection audio length tracking
        self.enterprise_audio_lang_detection_minutes_processed = Histogram(
            "telemetry_obsv_audio_lang_detection_minutes_processed",
            "Audio language detection audio minutes processed per request",
            ["tenant", "service_id"],
            buckets=(0.017, 0.083, 0.167, 0.5, 0.833, 1, 2, 5, 10, 30, 60, float("inf")),
            registry=self.registry,
        )

        # NER token (word) tracking
        self.enterprise_ner_tokens_processed = Histogram(
            "telemetry_obsv_ner_tokens_processed",
            "NER tokens (words) processed per request",
            ["tenant", "service_id"],
            buckets=(1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, float("inf")),
            registry=self.registry,
        )

        # Speaker diarization audio length tracking
        self.enterprise_speaker_diarization_minutes_processed = Histogram(
            "telemetry_obsv_speaker_diarization_minutes_processed",
            "Speaker diarization audio minutes processed per request",
            ["tenant", "service_id"],
            buckets=(0.017, 0.083, 0.167, 0.5, 0.833, 1, 2, 5, 10, 30, 60, float("inf")),
            registry=self.registry,
        )

        # Language diarization audio length tracking
        self.enterprise_language_diarization_minutes_processed = Histogram(
            "telemetry_obsv_language_diarization_minutes_processed",
            "Language diarization audio minutes processed per request",
            ["tenant", "service_id"],
            buckets=(0.017, 0.083, 0.167, 0.5, 0.833, 1, 2, 5, 10, 30, 60, float("inf")),
            registry=self.registry,
        )

    def track_request(
        self,
        method: str,
        endpoint: str,
        status_code: int,
        duration: float,
        tenant: str = "unknown",
        service_id: str = "",
        model_id: str = "",
    ):
        """Track a request — count + duration histogram."""
        self.enterprise_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status_code=str(status_code),
            tenant=tenant,
            service_id=service_id,
            model_id=model_id,
        ).inc()

        self.enterprise_request_duration.labels(
            method=method, endpoint=endpoint, tenant=tenant, service_id=service_id, model_id=model_id
        ).observe(duration)

    def track_llm_tokens(
        self,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        tenant: str = "unknown",
        service_id: str = "",
        endpoint: str = "",
        model_id: str = "",
    ):
        """Track LLM token usage from the inference engine's ``usage`` block.

        Emits up to three series per request — ``token_type=prompt``,
        ``completion``, and ``total`` — so PromQL can break down by either
        dimension. Counts ≤ 0 are skipped (so a streaming response with no
        usage block contributes nothing).
        """
        for token_type, count in (
            ("prompt", prompt_tokens),
            ("completion", completion_tokens),
            ("total", total_tokens),
        ):
            if count > 0:
                self.enterprise_llm_tokens_processed.labels(
                    model=model,
                    model_id=model_id,
                    tenant=tenant,
                    service_id=service_id,
                    endpoint=endpoint,
                    token_type=token_type,
                ).observe(count)

    def track_tts_characters(
        self, language: str, characters: int, tenant: str = "unknown", service_id: str = ""
    ):
        """Track TTS character synthesis."""
        self.enterprise_tts_characters_synthesized.labels(
            language=language, tenant=tenant, service_id=service_id
        ).observe(characters)

    def track_nmt_characters(
        self,
        source_lang: str,
        target_lang: str,
        characters: int,
        tenant: str = "unknown",
        service_id: str = "",
    ):
        """Track NMT character translation."""
        self.enterprise_nmt_characters_translated.labels(
            source_language=source_lang,
            target_language=target_lang,
            tenant=tenant,
            service_id=service_id,
        ).observe(characters)

    def track_asr_audio_length(
        self, language: str, audio_minutes: float, tenant: str = "unknown", service_id: str = ""
    ):
        """Track ASR audio length processing."""
        self.enterprise_asr_audio_minutes_processed.labels(
            language=language, tenant=tenant, service_id=service_id
        ).observe(audio_minutes)

    def track_ocr_characters(
        self, characters: int, tenant: str = "unknown", service_id: str = ""
    ):
        """Track OCR images processed (see enterprise_ocr_images_processed)."""
        self.enterprise_ocr_images_processed.labels(
            tenant=tenant, service_id=service_id
        ).observe(characters)

    def track_transliteration_characters(
        self,
        source_lang: str,
        target_lang: str,
        characters: int,
        tenant: str = "unknown",
        service_id: str = "",
    ):
        """Track Transliteration character processing."""
        self.enterprise_transliteration_characters_processed.labels(
            source_language=source_lang,
            target_language=target_lang,
            tenant=tenant,
            service_id=service_id,
        ).observe(characters)

    def track_language_detection_characters(
        self, characters: int, tenant: str = "unknown", service_id: str = ""
    ):
        """Track Language Detection character processing."""
        self.enterprise_language_detection_characters_processed.labels(
            tenant=tenant, service_id=service_id
        ).observe(characters)

    def track_audio_lang_detection_length(
        self, audio_minutes: float, tenant: str = "unknown", service_id: str = ""
    ):
        """Track Audio Language Detection audio length processing."""
        self.enterprise_audio_lang_detection_minutes_processed.labels(
            tenant=tenant, service_id=service_id
        ).observe(audio_minutes)

    def track_ner_tokens(
        self, tokens: int, tenant: str = "unknown", service_id: str = ""
    ):
        """Track NER token (word) processing."""
        self.enterprise_ner_tokens_processed.labels(
            tenant=tenant, service_id=service_id
        ).observe(tokens)

    def track_speaker_diarization_length(
        self, audio_minutes: float, tenant: str = "unknown", service_id: str = ""
    ):
        """Track Speaker Diarization audio length processing."""
        self.enterprise_speaker_diarization_minutes_processed.labels(
            tenant=tenant, service_id=service_id
        ).observe(audio_minutes)

    def track_language_diarization_length(
        self, audio_minutes: float, tenant: str = "unknown", service_id: str = ""
    ):
        """Track Language Diarization audio length processing."""
        self.enterprise_language_diarization_minutes_processed.labels(
            tenant=tenant, service_id=service_id
        ).observe(audio_minutes)

    def render(self) -> str:
        """Render the registry to Prometheus text-exposition format."""
        return generate_latest(self.registry).decode("utf-8")
