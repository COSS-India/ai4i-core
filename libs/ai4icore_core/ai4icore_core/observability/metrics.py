"""
Metrics collection system for AI4ICore Observability Plugin

Handles Prometheus metrics collection, system monitoring, and business analytics.

Labels are scoped to ``tenant`` plus technical attributes (method, endpoint,
language, etc.). No organization/customer/app dimensions are tracked.
"""

import psutil
from typing import Dict, Any, Optional
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    CollectorRegistry,
    generate_latest,
)


class MetricsCollector:
    """Metrics collector for AI4ICore Observability."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize metrics collector."""
        self.config = config or {}
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

        # Service metrics
        self.enterprise_service_requests = Counter(
            "telemetry_obsv_service_requests_total",
            "Service requests by type",
            ["service_type", "tenant", "service_id"],
            registry=self.registry,
        )

        # System metrics
        self.enterprise_system_cpu = Gauge(
            "telemetry_obsv_system_cpu_percent",
            "System CPU usage",
            registry=self.registry,
        )

        self.enterprise_system_memory = Gauge(
            "telemetry_obsv_system_memory_percent",
            "System memory usage",
            registry=self.registry,
        )

        # SLA metrics
        self.enterprise_sla_availability = Gauge(
            "telemetry_obsv_sla_availability_percent",
            "Service availability percentage",
            ["tenant"],
            registry=self.registry,
        )

        self.enterprise_sla_response_time = Gauge(
            "telemetry_obsv_sla_response_time_seconds",
            "Average response time",
            ["tenant"],
            registry=self.registry,
        )

        # Error tracking metrics
        self.enterprise_errors_total = Counter(
            "telemetry_obsv_errors_total",
            "Total errors by status code",
            ["endpoint", "status_code", "error_type", "tenant", "service_id"],
            registry=self.registry,
        )

        # Data processing metrics
        self.enterprise_data_processed_total = Counter(
            "telemetry_obsv_data_processed_total",
            "Total data processed",
            ["data_type", "tenant"],
            registry=self.registry,
        )

        # LLM token tracking
        self.enterprise_llm_tokens_processed = Counter(
            "telemetry_obsv_llm_tokens_processed_total",
            "Total LLM tokens processed",
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

        # Transliteration character tracking (Histogram for percentile calculations)
        self.enterprise_transliteration_characters_processed = Histogram(
            "telemetry_obsv_transliteration_characters_processed",
            "Transliteration characters processed per request",
            ["source_language", "target_language", "tenant", "service_id"],
            buckets=(10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, float("inf")),
            registry=self.registry,
        )

        # Language detection character tracking (Histogram for percentile calculations)
        self.enterprise_language_detection_characters_processed = Histogram(
            "telemetry_obsv_language_detection_characters_processed",
            "Language detection characters processed per request",
            ["tenant", "service_id"],
            buckets=(10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, float("inf")),
            registry=self.registry,
        )

        # Audio language detection audio length tracking (Histogram for percentile calculations)
        self.enterprise_audio_lang_detection_seconds_processed = Histogram(
            "telemetry_obsv_audio_lang_detection_seconds_processed",
            "Audio language detection audio seconds processed per request",
            ["tenant", "service_id"],
            buckets=(1, 5, 10, 30, 50, 60, 120, 300, 600, 1800, 3600, float("inf")),
            registry=self.registry,
        )

        # NER token (word) tracking (Histogram for percentile calculations)
        self.enterprise_ner_tokens_processed = Histogram(
            "telemetry_obsv_ner_tokens_processed",
            "NER tokens (words) processed per request",
            ["tenant", "service_id"],
            buckets=(1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, float("inf")),
            registry=self.registry,
        )

        # Speaker diarization audio length tracking (Histogram for percentile calculations)
        self.enterprise_speaker_diarization_seconds_processed = Histogram(
            "telemetry_obsv_speaker_diarization_seconds_processed",
            "Speaker diarization audio seconds processed per request",
            ["tenant", "service_id"],
            buckets=(1, 5, 10, 30, 50, 60, 120, 300, 600, 1800, 3600, float("inf")),
            registry=self.registry,
        )

        # Language diarization audio length tracking (Histogram for percentile calculations)
        self.enterprise_language_diarization_seconds_processed = Histogram(
            "telemetry_obsv_language_diarization_seconds_processed",
            "Language diarization audio seconds processed per request",
            ["tenant", "service_id"],
            buckets=(1, 5, 10, 30, 50, 60, 120, 300, 600, 1800, 3600, float("inf")),
            registry=self.registry,
        )

        # Speaker verification audio length tracking (Histogram for percentile calculations)
        self.enterprise_speaker_verification_seconds_processed = Histogram(
            "telemetry_obsv_speaker_verification_seconds_processed",
            "Speaker verification audio seconds processed per request",
            ["tenant", "service_id"],
            buckets=(1, 5, 10, 30, 50, 60, 120, 300, 600, 1800, 3600, float("inf")),
            registry=self.registry,
        )

        # SLA compliance tracking
        self.enterprise_sla_compliance = Gauge(
            "telemetry_obsv_sla_compliance_percent",
            "SLA compliance percentage",
            ["sla_type", "tenant"],
            registry=self.registry,
        )

        # Component latency tracking
        self.enterprise_component_latency = Histogram(
            "telemetry_obsv_component_latency_seconds",
            "Component latency",
            ["component", "tenant"],
            registry=self.registry,
        )

        # System metrics
        self.enterprise_system_peak_throughput = Gauge(
            "telemetry_obsv_system_peak_throughput_rpm",
            "Peak throughput requests per minute",
            registry=self.registry,
        )

        self.enterprise_system_service_count = Gauge(
            "telemetry_obsv_system_service_count",
            "Total number of services",
            registry=self.registry,
        )

    def update_system_metrics(self):
        """Update system metrics."""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            self.enterprise_system_cpu.set(cpu_percent)

            memory = psutil.virtual_memory()
            self.enterprise_system_memory.set(memory.percent)
        except Exception as e:
            if self.config.get("debug", False):
                print(f"Error updating system metrics: {e}")

    def track_request(
        self,
        method: str,
        endpoint: str,
        status_code: int,
        duration: float,
        service_type: str = "unknown",
        tenant: str = "unknown",
        service_id: str = "",
    ):
        """Track a request."""
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

        self.enterprise_service_requests.labels(
            service_type=service_type, tenant=tenant, service_id=service_id
        ).inc()

        if status_code >= 400:
            error_type = self._get_error_type(status_code)
            self.enterprise_errors_total.labels(
                endpoint=endpoint,
                status_code=str(status_code),
                error_type=error_type,
                tenant=tenant,
                service_id=service_id,
            ).inc()

    def track_data_processing(
        self, data_type: str, amount: int, tenant: str = "unknown"
    ):
        """Track data processing."""
        self.enterprise_data_processed_total.labels(
            data_type=data_type, tenant=tenant
        ).inc(amount)

    def track_llm_tokens(self, model: str, tokens: int, tenant: str = "unknown"):
        """Track LLM token processing."""
        self.enterprise_llm_tokens_processed.labels(
            model=model, tenant=tenant
        ).inc(tokens)
        self.track_data_processing("llm_tokens", tokens, tenant=tenant)

    def track_tts_characters(
        self, language: str, characters: int, tenant: str = "unknown", service_id: str = ""
    ):
        """Track TTS character synthesis."""
        self.enterprise_tts_characters_synthesized.labels(
            language=language, tenant=tenant, service_id=service_id
        ).observe(characters)
        self.track_data_processing("tts_characters", characters, tenant=tenant)

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
        self.track_data_processing("nmt_characters", characters, tenant=tenant)

    def track_asr_audio_length(
        self, language: str, audio_seconds: float, tenant: str = "unknown", service_id: str = ""
    ):
        """Track ASR audio length processing."""
        self.enterprise_asr_audio_seconds_processed.labels(
            language=language, tenant=tenant, service_id=service_id
        ).observe(audio_seconds)
        self.track_data_processing("asr_audio_seconds", int(audio_seconds), tenant=tenant)

    def track_ocr_characters(
        self, characters: int, tenant: str = "unknown", service_id: str = ""
    ):
        """Track OCR character processing."""
        self.enterprise_ocr_characters_processed.labels(
            tenant=tenant, service_id=service_id
        ).observe(characters)
        self.track_data_processing("ocr_characters", characters, tenant=tenant)

    def track_ocr_image_size(
        self, image_size_kb: float, tenant: str = "unknown", service_id: str = ""
    ):
        """Track OCR image payload size in KB."""
        self.enterprise_ocr_image_size_kb.labels(
            tenant=tenant, service_id=service_id
        ).observe(image_size_kb)
        self.track_data_processing("ocr_image_kb", int(image_size_kb), tenant=tenant)

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
        self.track_data_processing("transliteration_characters", characters, tenant=tenant)

    def track_language_detection_characters(
        self, characters: int, tenant: str = "unknown", service_id: str = ""
    ):
        """Track Language Detection character processing."""
        self.enterprise_language_detection_characters_processed.labels(
            tenant=tenant, service_id=service_id
        ).observe(characters)
        self.track_data_processing("language_detection_characters", characters, tenant=tenant)

    def track_audio_lang_detection_length(
        self, audio_seconds: float, tenant: str = "unknown", service_id: str = ""
    ):
        """Track Audio Language Detection audio length processing."""
        self.enterprise_audio_lang_detection_seconds_processed.labels(
            tenant=tenant, service_id=service_id
        ).observe(audio_seconds)
        self.track_data_processing("audio_lang_detection_seconds", int(audio_seconds), tenant=tenant)

    def track_ner_tokens(
        self, tokens: int, tenant: str = "unknown", service_id: str = ""
    ):
        """Track NER token (word) processing."""
        self.enterprise_ner_tokens_processed.labels(
            tenant=tenant, service_id=service_id
        ).observe(tokens)
        self.track_data_processing("ner_tokens", tokens, tenant=tenant)

    def track_speaker_diarization_length(
        self, audio_seconds: float, tenant: str = "unknown", service_id: str = ""
    ):
        """Track Speaker Diarization audio length processing."""
        self.enterprise_speaker_diarization_seconds_processed.labels(
            tenant=tenant, service_id=service_id
        ).observe(audio_seconds)
        self.track_data_processing("speaker_diarization_seconds", int(audio_seconds), tenant=tenant)

    def track_language_diarization_length(
        self, audio_seconds: float, tenant: str = "unknown", service_id: str = ""
    ):
        """Track Language Diarization audio length processing."""
        self.enterprise_language_diarization_seconds_processed.labels(
            tenant=tenant, service_id=service_id
        ).observe(audio_seconds)
        self.track_data_processing("language_diarization_seconds", int(audio_seconds), tenant=tenant)

    def track_speaker_verification_length(
        self, audio_seconds: float, tenant: str = "unknown", service_id: str = ""
    ):
        """Track Speaker Verification audio length processing."""
        self.enterprise_speaker_verification_seconds_processed.labels(
            tenant=tenant, service_id=service_id
        ).observe(audio_seconds)
        self.track_data_processing("speaker_verification_seconds", int(audio_seconds), tenant=tenant)

    def track_component_latency(
        self, component: str, duration: float, tenant: str = "unknown"
    ):
        """Track component latency."""
        self.enterprise_component_latency.labels(
            component=component, tenant=tenant
        ).observe(duration)

    def update_sla_compliance(
        self, sla_type: str, compliance_percent: float, tenant: str = "unknown"
    ):
        """Update SLA compliance."""
        self.enterprise_sla_compliance.labels(
            sla_type=sla_type, tenant=tenant
        ).set(compliance_percent)

    def update_system_metrics_advanced(self):
        """Update advanced system metrics."""
        try:
            self.enterprise_system_peak_throughput.set(1000)  # Mock value
            self.enterprise_system_service_count.set(5)  # Mock value
        except Exception as e:
            if self.config.get("debug", False):
                print(f"Error updating advanced system metrics: {e}")

    def _get_error_type(self, status_code: int) -> str:
        """Get error type from status code."""
        if 400 <= status_code < 500:
            return "client_error"
        elif 500 <= status_code < 600:
            return "server_error"
        else:
            return "unknown_error"

    def get_metrics_text(self) -> str:
        """Get metrics in Prometheus text format."""
        try:
            self.update_system_metrics()
            self.update_system_metrics_advanced()
        except Exception as e:
            debug_enabled = self.config.get("debug", False) if isinstance(self.config, dict) else getattr(self.config, "debug", False)
            if debug_enabled:
                print(f"[DEBUG] Error in get_metrics_text: {e}")
                import traceback
                traceback.print_exc()
        return generate_latest(self.registry).decode("utf-8")


# Global metrics collector instance
_global_collector = None


def get_global_collector() -> MetricsCollector:
    """Get the global metrics collector instance."""
    global _global_collector
    if _global_collector is None:
        _global_collector = MetricsCollector()
    return _global_collector
