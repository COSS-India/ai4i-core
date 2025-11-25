"""
Metrics collection system for Dhruva Observability Plugin

Handles Prometheus metrics collection, system monitoring, and business analytics.
"""

import time
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
    """Metrics collector for Dhruva Observability."""

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
            ["organization", "app", "method", "endpoint", "status_code"],
            registry=self.registry,
        )

        self.enterprise_request_duration = Histogram(
            "telemetry_obsv_request_duration_seconds",
            "Enterprise request duration",
            ["organization", "app", "method", "endpoint"],
            registry=self.registry,
        )

        # Service metrics
        self.enterprise_service_requests = Counter(
            "telemetry_obsv_service_requests_total",
            "Service requests by type",
            ["organization", "app", "service_type"],
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
            ["organization", "app"],
            registry=self.registry,
        )

        self.enterprise_sla_response_time = Gauge(
            "telemetry_obsv_sla_response_time_seconds",
            "Average response time",
            ["organization", "app"],
            registry=self.registry,
        )

        # Error tracking metrics
        self.enterprise_errors_total = Counter(
            "telemetry_obsv_errors_total",
            "Total errors by status code",
            ["organization", "app", "endpoint", "status_code", "error_type"],
            registry=self.registry,
        )

        # Data processing metrics
        self.enterprise_data_processed_total = Counter(
            "telemetry_obsv_data_processed_total",
            "Total data processed",
            ["organization", "app", "data_type"],
            registry=self.registry,
        )

        # LLM token tracking
        self.enterprise_llm_tokens_processed = Counter(
            "telemetry_obsv_llm_tokens_processed_total",
            "Total LLM tokens processed",
            ["organization", "app", "model"],
            registry=self.registry,
        )

        # TTS character tracking (Histogram for percentile calculations)
        self.enterprise_tts_characters_synthesized = Histogram(
            "telemetry_obsv_tts_characters_synthesized",
            "TTS characters synthesized per request",
            ["organization", "app", "language"],
            buckets=(10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, float("inf")),
            registry=self.registry,
        )

        # NMT character tracking (Histogram for percentile calculations)
        self.enterprise_nmt_characters_translated = Histogram(
            "telemetry_obsv_nmt_characters_translated",
            "NMT characters translated per request",
            ["organization", "app", "source_language", "target_language"],
            buckets=(10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, float("inf")),
            registry=self.registry,
        )

        # ASR audio length tracking (Histogram for percentile calculations)
        self.enterprise_asr_audio_seconds_processed = Histogram(
            "telemetry_obsv_asr_audio_seconds_processed",
            "ASR audio seconds processed per request",
            ["organization", "app", "language"],
            buckets=(1, 5, 10, 30, 50, 60, 120, 300, 600, 1800, 3600, float("inf")),
            registry=self.registry,
        )

        # OCR character tracking (Histogram for percentile calculations)
        self.enterprise_ocr_characters_processed = Histogram(
            "telemetry_obsv_ocr_characters_processed",
            "OCR characters processed per request",
            ["organization", "app"],
            buckets=(10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, float("inf")),
            registry=self.registry,
        )

        # Transliteration character tracking (Histogram for percentile calculations)
        self.enterprise_transliteration_characters_processed = Histogram(
            "telemetry_obsv_transliteration_characters_processed",
            "Transliteration characters processed per request",
            ["organization", "app", "source_language", "target_language"],
            buckets=(10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, float("inf")),
            registry=self.registry,
        )

        # Language detection character tracking (Histogram for percentile calculations)
        self.enterprise_language_detection_characters_processed = Histogram(
            "telemetry_obsv_language_detection_characters_processed",
            "Language detection characters processed per request",
            ["organization", "app"],
            buckets=(10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, float("inf")),
            registry=self.registry,
        )

        # Audio language detection audio length tracking (Histogram for percentile calculations)
        self.enterprise_audio_lang_detection_seconds_processed = Histogram(
            "telemetry_obsv_audio_lang_detection_seconds_processed",
            "Audio language detection audio seconds processed per request",
            ["organization", "app"],
            buckets=(1, 5, 10, 30, 50, 60, 120, 300, 600, 1800, 3600, float("inf")),
            registry=self.registry,
        )

        # NER character tracking (Histogram for percentile calculations)
        self.enterprise_ner_characters_processed = Histogram(
            "telemetry_obsv_ner_characters_processed",
            "NER characters processed per request",
            ["organization", "app"],
            buckets=(10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000, float("inf")),
            registry=self.registry,
        )

        # Speaker diarization audio length tracking (Histogram for percentile calculations)
        self.enterprise_speaker_diarization_seconds_processed = Histogram(
            "telemetry_obsv_speaker_diarization_seconds_processed",
            "Speaker diarization audio seconds processed per request",
            ["organization", "app"],
            buckets=(1, 5, 10, 30, 50, 60, 120, 300, 600, 1800, 3600, float("inf")),
            registry=self.registry,
        )

        # Language diarization audio length tracking (Histogram for percentile calculations)
        self.enterprise_language_diarization_seconds_processed = Histogram(
            "telemetry_obsv_language_diarization_seconds_processed",
            "Language diarization audio seconds processed per request",
            ["organization", "app"],
            buckets=(1, 5, 10, 30, 50, 60, 120, 300, 600, 1800, 3600, float("inf")),
            registry=self.registry,
        )

        # Speaker verification audio length tracking (Histogram for percentile calculations)
        self.enterprise_speaker_verification_seconds_processed = Histogram(
            "telemetry_obsv_speaker_verification_seconds_processed",
            "Speaker verification audio seconds processed per request",
            ["organization", "app"],
            buckets=(1, 5, 10, 30, 50, 60, 120, 300, 600, 1800, 3600, float("inf")),
            registry=self.registry,
        )

        # SLA compliance tracking
        self.enterprise_sla_compliance = Gauge(
            "telemetry_obsv_sla_compliance_percent",
            "SLA compliance percentage",
            ["organization", "app", "sla_type"],
            registry=self.registry,
        )

        # Component latency tracking
        self.enterprise_component_latency = Histogram(
            "telemetry_obsv_component_latency_seconds",
            "Component latency",
            ["organization", "app", "component"],
            registry=self.registry,
        )

        # Organization quota tracking
        self.enterprise_organization_llm_quota = Gauge(
            "telemetry_obsv_organization_llm_quota_per_month",
            "Organization LLM quota per month",
            ["organization"],
            registry=self.registry,
        )

        self.enterprise_organization_tts_quota = Gauge(
            "telemetry_obsv_organization_tts_quota_per_month",
            "Organization TTS quota per month",
            ["organization"],
            registry=self.registry,
        )

        self.enterprise_organization_nmt_quota = Gauge(
            "telemetry_obsv_organization_nmt_quota_per_month",
            "Organization NMT quota per month",
            ["organization"],
            registry=self.registry,
        )

        self.enterprise_organization_asr_quota = Gauge(
            "telemetry_obsv_organization_asr_quota_per_month",
            "Organization ASR quota per month (in audio seconds)",
            ["organization"],
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
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            self.enterprise_system_cpu.set(cpu_percent)

            # Memory usage
            memory = psutil.virtual_memory()
            self.enterprise_system_memory.set(memory.percent)

            # SLA metrics (simplified)
            organizations = self.config.get("organizations", ["default"])
            apps = self.config.get("apps", ["default"])

            for organization in organizations:
                for app in apps:
                    self.enterprise_sla_availability.labels(
                        organization=organization, app=app
                    ).set(
                        99.9
                    )  # Mock availability

                    self.enterprise_sla_response_time.labels(
                        organization=organization, app=app
                    ).set(
                        0.5
                    )  # Mock response time

        except Exception as e:
            if self.config.get("debug", False):
                print(f"Error updating system metrics: {e}")

    def track_request(
        self,
        organization: str,
        app: str,
        method: str,
        endpoint: str,
        status_code: int,
        duration: float,
        service_type: str = "unknown",
    ):
        """Track a request."""
        self.enterprise_requests_total.labels(
            organization=organization,
            app=app,
            method=method,
            endpoint=endpoint,
            status_code=str(status_code),
        ).inc()

        self.enterprise_request_duration.labels(
            organization=organization, app=app, method=method, endpoint=endpoint
        ).observe(duration)

        self.enterprise_service_requests.labels(
            organization=organization, app=app, service_type=service_type
        ).inc()

        # Track errors if status code indicates error
        if status_code >= 400:
            error_type = self._get_error_type(status_code)
            self.enterprise_errors_total.labels(
                organization=organization,
                app=app,
                endpoint=endpoint,
                status_code=str(status_code),
                error_type=error_type,
            ).inc()

    def track_data_processing(
        self, organization: str, app: str, data_type: str, amount: int
    ):
        """Track data processing."""
        self.enterprise_data_processed_total.labels(
            organization=organization, app=app, data_type=data_type
        ).inc(amount)

    def track_llm_tokens(self, organization: str, app: str, model: str, tokens: int):
        """Track LLM token processing."""
        self.enterprise_llm_tokens_processed.labels(
            organization=organization, app=app, model=model
        ).inc(tokens)

        # Also track as data processing
        self.track_data_processing(organization, app, "llm_tokens", tokens)

    def track_tts_characters(
        self, organization: str, app: str, language: str, characters: int
    ):
        """Track TTS character synthesis."""
        self.enterprise_tts_characters_synthesized.labels(
            organization=organization, app=app, language=language
        ).observe(characters)

        # Also track as data processing
        self.track_data_processing(organization, app, "tts_characters", characters)

    def track_nmt_characters(
        self,
        organization: str,
        app: str,
        source_lang: str,
        target_lang: str,
        characters: int,
    ):
        """Track NMT character translation."""
        self.enterprise_nmt_characters_translated.labels(
            organization=organization,
            app=app,
            source_language=source_lang,
            target_language=target_lang,
        ).observe(characters)

        # Also track as data processing
        self.track_data_processing(organization, app, "nmt_characters", characters)

    def track_asr_audio_length(
        self, organization: str, app: str, language: str, audio_seconds: float
    ):
        """Track ASR audio length processing."""
        self.enterprise_asr_audio_seconds_processed.labels(
            organization=organization, app=app, language=language
        ).observe(audio_seconds)

        # Also track as data processing
        self.track_data_processing(organization, app, "asr_audio_seconds", int(audio_seconds))

    def track_ocr_characters(
        self, organization: str, app: str, characters: int
    ):
        """Track OCR character processing."""
        self.enterprise_ocr_characters_processed.labels(
            organization=organization, app=app
        ).observe(characters)

        # Also track as data processing
        self.track_data_processing(organization, app, "ocr_characters", characters)

    def track_transliteration_characters(
        self,
        organization: str,
        app: str,
        source_lang: str,
        target_lang: str,
        characters: int,
    ):
        """Track Transliteration character processing."""
        self.enterprise_transliteration_characters_processed.labels(
            organization=organization,
            app=app,
            source_language=source_lang,
            target_language=target_lang,
        ).observe(characters)

        # Also track as data processing
        self.track_data_processing(organization, app, "transliteration_characters", characters)

    def track_language_detection_characters(
        self, organization: str, app: str, characters: int
    ):
        """Track Language Detection character processing."""
        self.enterprise_language_detection_characters_processed.labels(
            organization=organization, app=app
        ).observe(characters)

        # Also track as data processing
        self.track_data_processing(organization, app, "language_detection_characters", characters)

    def track_audio_lang_detection_length(
        self, organization: str, app: str, audio_seconds: float
    ):
        """Track Audio Language Detection audio length processing."""
        self.enterprise_audio_lang_detection_seconds_processed.labels(
            organization=organization, app=app
        ).observe(audio_seconds)

        # Also track as data processing
        self.track_data_processing(organization, app, "audio_lang_detection_seconds", int(audio_seconds))

    def track_ner_characters(
        self, organization: str, app: str, characters: int
    ):
        """Track NER character processing."""
        self.enterprise_ner_characters_processed.labels(
            organization=organization, app=app
        ).observe(characters)

        # Also track as data processing
        self.track_data_processing(organization, app, "ner_characters", characters)

    def track_speaker_diarization_length(
        self, organization: str, app: str, audio_seconds: float
    ):
        """Track Speaker Diarization audio length processing."""
        self.enterprise_speaker_diarization_seconds_processed.labels(
            organization=organization, app=app
        ).observe(audio_seconds)

        # Also track as data processing
        self.track_data_processing(organization, app, "speaker_diarization_seconds", int(audio_seconds))

    def track_language_diarization_length(
        self, organization: str, app: str, audio_seconds: float
    ):
        """Track Language Diarization audio length processing."""
        self.enterprise_language_diarization_seconds_processed.labels(
            organization=organization, app=app
        ).observe(audio_seconds)

        # Also track as data processing
        self.track_data_processing(organization, app, "language_diarization_seconds", int(audio_seconds))

    def track_speaker_verification_length(
        self, organization: str, app: str, audio_seconds: float
    ):
        """Track Speaker Verification audio length processing."""
        self.enterprise_speaker_verification_seconds_processed.labels(
            organization=organization, app=app
        ).observe(audio_seconds)

        # Also track as data processing
        self.track_data_processing(organization, app, "speaker_verification_seconds", int(audio_seconds))

    def track_component_latency(
        self, organization: str, app: str, component: str, duration: float
    ):
        """Track component latency."""
        self.enterprise_component_latency.labels(
            organization=organization, app=app, component=component
        ).observe(duration)

    def update_sla_compliance(
        self, organization: str, app: str, sla_type: str, compliance_percent: float
    ):
        """Update SLA compliance."""
        self.enterprise_sla_compliance.labels(
            organization=organization, app=app, sla_type=sla_type
        ).set(compliance_percent)

    def update_organization_quotas(
        self,
        organization: str,
        llm_quota: int = 1000000,
        tts_quota: int = 1000000,
        nmt_quota: int = 1000000,
        asr_quota: int = 1000000,
    ):
        """Update organization quotas."""
        self.enterprise_organization_llm_quota.labels(organization=organization).set(llm_quota)
        self.enterprise_organization_tts_quota.labels(organization=organization).set(tts_quota)
        self.enterprise_organization_nmt_quota.labels(organization=organization).set(nmt_quota)
        self.enterprise_organization_asr_quota.labels(organization=organization).set(asr_quota)

    def update_system_metrics_advanced(self):
        """Update advanced system metrics."""
        try:
            # Update peak throughput (mock calculation)
            self.enterprise_system_peak_throughput.set(1000)  # Mock value

            # Update service count (mock calculation)
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
        self.update_system_metrics()
        self.update_system_metrics_advanced()
        return generate_latest(self.registry).decode("utf-8")


def prometheus_latest_text() -> str:
    """Get latest Prometheus metrics text."""
    # This would be implemented to return the latest metrics
    # For now, return a placeholder
    return "# Prometheus metrics would be generated here"


# Global metrics collector instance
_global_collector = None


def get_global_collector() -> MetricsCollector:
    """Get the global metrics collector instance."""
    global _global_collector
    if _global_collector is None:
        _global_collector = MetricsCollector()
    return _global_collector
