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
        self.enterprise_requests_total = Counter(
            "telemetry_obsv_requests_total",
            "Total enterprise requests",
            ["method", "endpoint", "status_code", "tenant", "service_id"],
            registry=self.registry,
        )

        self.enterprise_request_duration = Histogram(
            "telemetry_obsv_request_duration_seconds",
            "Enterprise request duration",
            ["method", "endpoint", "tenant", "service_id"],
            registry=self.registry,
        )

        # LLM input-token tracking (approximated from input characters: chars/4,
        # OpenAI's English-prompt rule of thumb; for multilingual workloads
        # this is a rough lower bound, not exact tokenizer output).
        self.enterprise_llm_tokens_processed = Counter(
            "telemetry_obsv_llm_tokens_processed_total",
            "Total LLM input tokens processed (approximated from input characters)",
            ["model", "tenant"],
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
        self.enterprise_asr_audio_seconds_processed = Histogram(
            "telemetry_obsv_asr_audio_seconds_processed",
            "ASR audio seconds processed per request",
            ["language", "tenant", "service_id"],
            buckets=(1, 5, 10, 30, 50, 60, 120, 300, 600, 1800, 3600, float("inf")),
            registry=self.registry,
        )

        # OCR character tracking (Histogram for percentile calculations)
        self.enterprise_ocr_characters_processed = Histogram(
            "telemetry_obsv_ocr_characters_processed",
            "OCR characters processed per request",
            ["tenant", "service_id"],
            buckets=(10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, float("inf")),
            registry=self.registry,
        )
        # OCR image size tracking (Histogram for percentile calculations)
        self.enterprise_ocr_image_size_kb = Histogram(
            "telemetry_obsv_ocr_image_size_kb",
            "OCR image payload size in kilobytes per request",
            ["tenant", "service_id"],
            buckets=(10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, float("inf")),
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
        self.enterprise_audio_lang_detection_seconds_processed = Histogram(
            "telemetry_obsv_audio_lang_detection_seconds_processed",
            "Audio language detection audio seconds processed per request",
            ["tenant", "service_id"],
            buckets=(1, 5, 10, 30, 50, 60, 120, 300, 600, 1800, 3600, float("inf")),
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
        self.enterprise_speaker_diarization_seconds_processed = Histogram(
            "telemetry_obsv_speaker_diarization_seconds_processed",
            "Speaker diarization audio seconds processed per request",
            ["tenant", "service_id"],
            buckets=(1, 5, 10, 30, 50, 60, 120, 300, 600, 1800, 3600, float("inf")),
            registry=self.registry,
        )

        # Language diarization audio length tracking
        self.enterprise_language_diarization_seconds_processed = Histogram(
            "telemetry_obsv_language_diarization_seconds_processed",
            "Language diarization audio seconds processed per request",
            ["tenant", "service_id"],
            buckets=(1, 5, 10, 30, 50, 60, 120, 300, 600, 1800, 3600, float("inf")),
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
    ):
        """Track a request — count + duration histogram."""
        self.enterprise_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status_code=str(status_code),
            tenant=tenant,
            service_id=service_id,
        ).inc()

        self.enterprise_request_duration.labels(
            method=method, endpoint=endpoint, tenant=tenant, service_id=service_id
        ).observe(duration)

    def track_llm_tokens(self, model: str, tokens: int, tenant: str = "unknown"):
        """Track LLM input token processing.

        ``tokens`` should be a real measurement from the request input
        (e.g. char-based approximation in middleware, or exact tokenizer
        output if the llm-service emits it post-inference).
        """
        self.enterprise_llm_tokens_processed.labels(
            model=model, tenant=tenant
        ).inc(tokens)

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
        self, language: str, audio_seconds: float, tenant: str = "unknown", service_id: str = ""
    ):
        """Track ASR audio length processing."""
        self.enterprise_asr_audio_seconds_processed.labels(
            language=language, tenant=tenant, service_id=service_id
        ).observe(audio_seconds)

    def track_ocr_characters(
        self, characters: int, tenant: str = "unknown", service_id: str = ""
    ):
        """Track OCR character processing."""
        self.enterprise_ocr_characters_processed.labels(
            tenant=tenant, service_id=service_id
        ).observe(characters)

    def track_ocr_image_size(
        self, image_size_kb: float, tenant: str = "unknown", service_id: str = ""
    ):
        """Track OCR image payload size in KB."""
        self.enterprise_ocr_image_size_kb.labels(
            tenant=tenant, service_id=service_id
        ).observe(image_size_kb)

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
        self, audio_seconds: float, tenant: str = "unknown", service_id: str = ""
    ):
        """Track Audio Language Detection audio length processing."""
        self.enterprise_audio_lang_detection_seconds_processed.labels(
            tenant=tenant, service_id=service_id
        ).observe(audio_seconds)

    def track_ner_tokens(
        self, tokens: int, tenant: str = "unknown", service_id: str = ""
    ):
        """Track NER token (word) processing."""
        self.enterprise_ner_tokens_processed.labels(
            tenant=tenant, service_id=service_id
        ).observe(tokens)

    def track_speaker_diarization_length(
        self, audio_seconds: float, tenant: str = "unknown", service_id: str = ""
    ):
        """Track Speaker Diarization audio length processing."""
        self.enterprise_speaker_diarization_seconds_processed.labels(
            tenant=tenant, service_id=service_id
        ).observe(audio_seconds)

    def track_language_diarization_length(
        self, audio_seconds: float, tenant: str = "unknown", service_id: str = ""
    ):
        """Track Language Diarization audio length processing."""
        self.enterprise_language_diarization_seconds_processed.labels(
            tenant=tenant, service_id=service_id
        ).observe(audio_seconds)

    def render(self) -> str:
        """Render the registry to Prometheus text-exposition format."""
        return generate_latest(self.registry).decode("utf-8")
