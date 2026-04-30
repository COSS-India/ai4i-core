"""
Metrics collection system for Dhruva Observability Plugin

Handles Prometheus metrics collection, system monitoring, and business analytics.
"""

import time
import re
import psutil
from typing import Dict, Any, Optional
from collections import defaultdict
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
        # Track running totals for organization-level system metrics (time-windowed)
        self._org_duration_totals: Dict[str, float] = defaultdict(float)
        self._org_request_totals: Dict[str, int] = defaultdict(int)
        self._org_data_totals: Dict[str, int] = defaultdict(int)
        self._total_duration = 0.0
        self._total_requests = 0
        self._total_data = 0
        self._last_reset_time = time.time()
        self._reset_interval = 300  # Reset totals every 5 minutes (sliding window)
        self._init_metrics()
        # Initialize organization-level metrics with default organizations
        # This ensures metrics are always exposed, even before any requests
        self._initialize_organization_metrics()

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

        # Organization-level system resource usage (estimated)
        self.enterprise_org_cpu_usage = Gauge(
            "telemetry_obsv_organization_cpu_percent",
            "Estimated CPU usage per organization (based on request processing time)",
            ["organization"],
            registry=self.registry,
        )

        self.enterprise_org_memory_usage = Gauge(
            "telemetry_obsv_organization_memory_percent",
            "Estimated memory usage per organization (based on request volume)",
            ["organization"],
            registry=self.registry,
        )

        self.enterprise_org_disk_usage = Gauge(
            "telemetry_obsv_organization_disk_percent",
            "Estimated disk usage per organization (based on data processed)",
            ["organization"],
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
        # OCR image size tracking (Histogram for percentile calculations)
        self.enterprise_ocr_image_size_kb = Histogram(
            "telemetry_obsv_ocr_image_size_kb",
            "OCR image payload size in kilobytes per request",
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

        # NER token (word) tracking (Histogram for percentile calculations)
        self.enterprise_ner_tokens_processed = Histogram(
            "telemetry_obsv_ner_tokens_processed",
            "NER tokens (words) processed per request",
            ["organization", "app"],
            buckets=(1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, float("inf")),
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

            # Update organization-level system metrics
            self._update_organization_system_metrics(cpu_percent, memory.percent)

            # SLA metrics (simplified)
            # Config can be a dict (from to_dict()) or a PluginConfig object
            if isinstance(self.config, dict):
                organizations = self.config.get("organizations", []) or self.config.get("customers", ["default"])
                apps = self.config.get("apps", ["default"])
            else:
                # PluginConfig dataclass
                organizations = getattr(self.config, "customers", []) or getattr(self.config, "organizations", ["default"])
                apps = getattr(self.config, "apps", ["default"])

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

    def _initialize_organization_metrics(self):
        """Initialize organization-level metrics with default organizations.
        
        This ensures metrics are always exposed in Prometheus, even before any requests are made.
        """
        try:
            # Get organizations from config if available
            if isinstance(self.config, dict):
                config_orgs = self.config.get("organizations", []) or self.config.get("customers", [])
            else:
                config_orgs = getattr(self.config, "customers", []) or getattr(self.config, "organizations", [])
            
            # Use default organizations if none in config
            default_orgs = ["irctc", "kisanmitra", "bashadaan", "beml"]
            orgs_to_init = config_orgs if config_orgs else default_orgs
            
            # Initialize all organization-level metrics to 0
            # This is critical - Prometheus Gauges only appear after they've been set at least once
            for org in orgs_to_init:
                if org and org != "unknown":
                    try:
                        self.enterprise_org_cpu_usage.labels(organization=org).set(0.0)
                        self.enterprise_org_memory_usage.labels(organization=org).set(0.0)
                        self.enterprise_org_disk_usage.labels(organization=org).set(0.0)
                    except Exception as label_error:
                        # If label setting fails, log but continue
                        debug_enabled = self.config.get("debug", False) if isinstance(self.config, dict) else getattr(self.config, "debug", False)
                        if debug_enabled:
                            print(f"[DEBUG] Error setting labels for org {org}: {label_error}")
        except Exception as e:
            debug_enabled = self.config.get("debug", False) if isinstance(self.config, dict) else getattr(self.config, "debug", False)
            if debug_enabled:
                print(f"[DEBUG] Error initializing organization metrics: {e}")
                import traceback
                traceback.print_exc()

    def _reset_totals_if_needed(self):
        """Reset running totals periodically to maintain a sliding window."""
        current_time = time.time()
        if current_time - self._last_reset_time >= self._reset_interval:
            # Reset all totals (sliding window approach)
            self._org_duration_totals.clear()
            self._org_request_totals.clear()
            self._org_data_totals.clear()
            self._total_duration = 0.0
            self._total_requests = 0
            self._total_data = 0
            self._last_reset_time = current_time

    def _update_organization_system_metrics(self, system_cpu_percent: float, system_memory_percent: float):
        """
        Calculate and update organization-level system resource usage.
        
        This estimates each organization's share of system resources based on:
        - CPU: Proportion of total request processing time
        - Memory: Proportion of total request volume
        - Disk: Proportion of total data processed
        
        Args:
            system_cpu_percent: Overall system CPU usage percentage
            system_memory_percent: Overall system memory usage percentage
        """
        try:
            # Reset totals if needed (sliding window)
            self._reset_totals_if_needed()
            
            # Get system disk usage
            try:
                disk = psutil.disk_usage('/')
                system_disk_percent = (disk.used / disk.total) * 100
            except:
                system_disk_percent = 50.0  # Fallback estimate
            
            # Get all organizations that have made requests
            all_orgs = set(self._org_duration_totals.keys()) | set(self._org_request_totals.keys()) | set(self._org_data_totals.keys())
            
            # CRITICAL: Extract organizations from existing metric objects
            # Directly access the Counter/Histogram objects to get their label combinations
            try:
                # Get organizations from the requests_total counter
                # Prometheus client stores metrics with their label combinations
                # We need to access the _metrics dict which contains all label combinations
                if hasattr(self.enterprise_requests_total, '_metrics'):
                    for labels_tuple, metric_obj in self.enterprise_requests_total._metrics.items():
                        # labels_tuple is a tuple of label values in order: (organization, app, method, endpoint, status_code)
                        if labels_tuple and len(labels_tuple) > 0:
                            org = labels_tuple[0]  # First label is organization
                            if org and org != 'unknown':
                                all_orgs.add(org)
                
                # Also check request_duration histogram
                if hasattr(self.enterprise_request_duration, '_metrics'):
                    for labels_tuple, metric_obj in self.enterprise_request_duration._metrics.items():
                        if labels_tuple and len(labels_tuple) > 0:
                            org = labels_tuple[0]  # First label is organization
                            if org and org != 'unknown':
                                all_orgs.add(org)
            except Exception as e:
                debug_enabled = self.config.get("debug", False) if isinstance(self.config, dict) else getattr(self.config, "debug", False)
                if debug_enabled:
                    print(f"[DEBUG] Error extracting orgs from metric objects: {e}")
                    import traceback
                    traceback.print_exc()
            
            # Also include organizations from config if available
            # Config can be a dict (from to_dict()) or a PluginConfig object
            if isinstance(self.config, dict):
                config_orgs = self.config.get("organizations", []) or self.config.get("customers", [])
            else:
                # PluginConfig dataclass
                config_orgs = getattr(self.config, "customers", []) or getattr(self.config, "organizations", [])
            if config_orgs:
                all_orgs.update(config_orgs)
            
            # Remove "unknown" from the set
            all_orgs.discard("unknown")
            
            # FALLBACK: If no organizations found anywhere, initialize for common test organizations
            # This ensures metrics exist even before any requests are made
            # This is important so Prometheus can see the metrics immediately
            if not all_orgs:
                if isinstance(self.config, dict):
                    config_orgs = self.config.get("organizations", []) or self.config.get("customers", [])
                else:
                    config_orgs = getattr(self.config, "customers", []) or getattr(self.config, "organizations", [])
                default_orgs = config_orgs if config_orgs else ["irctc", "kisanmitra", "bashadaan", "beml"]
                for org in default_orgs:
                    if org and org != "unknown":
                        all_orgs.add(org)
            
            # CRITICAL: Always ensure at least default organizations are initialized
            # This guarantees metrics are always exposed in Prometheus
            if not all_orgs:
                default_orgs = ["irctc", "kisanmitra", "bashadaan", "beml"]
                all_orgs.update(default_orgs)
            
            # Calculate and set organization-level CPU usage
            # Based on request processing time proportion
            if self._total_duration > 0:
                for org in all_orgs:
                    org_duration = self._org_duration_totals.get(org, 0.0)
                    org_cpu_share = (org_duration / self._total_duration) * system_cpu_percent
                    self.enterprise_org_cpu_usage.labels(organization=org).set(org_cpu_share)
            else:
                # No requests yet, set all to 0
                for org in all_orgs:
                    self.enterprise_org_cpu_usage.labels(organization=org).set(0.0)
            
            # Calculate and set organization-level memory usage
            # Based on request volume proportion
            if self._total_requests > 0:
                for org in all_orgs:
                    org_requests = self._org_request_totals.get(org, 0)
                    org_memory_share = (org_requests / self._total_requests) * system_memory_percent
                    self.enterprise_org_memory_usage.labels(organization=org).set(org_memory_share)
            else:
                # No requests yet, set all to 0
                for org in all_orgs:
                    self.enterprise_org_memory_usage.labels(organization=org).set(0.0)
            
            # Calculate and set organization-level disk usage
            # Based on data processed proportion
            if self._total_data > 0:
                for org in all_orgs:
                    org_data = self._org_data_totals.get(org, 0)
                    org_disk_share = (org_data / self._total_data) * system_disk_percent
                    self.enterprise_org_disk_usage.labels(organization=org).set(org_disk_share)
            else:
                # No data processed yet, set all to 0
                for org in all_orgs:
                    self.enterprise_org_disk_usage.labels(organization=org).set(0.0)
            
            # CRITICAL: Final safety check - ensure metrics are always set for at least default orgs
            # This guarantees metrics appear in Prometheus even if something went wrong above
            if not all_orgs:
                default_orgs = ["irctc", "kisanmitra", "bashadaan", "beml"]
                for org in default_orgs:
                    try:
                        self.enterprise_org_cpu_usage.labels(organization=org).set(0.0)
                        self.enterprise_org_memory_usage.labels(organization=org).set(0.0)
                        self.enterprise_org_disk_usage.labels(organization=org).set(0.0)
                    except Exception as metric_error:
                        # Log but don't fail - metrics might already be set
                        pass
            
            # Debug logging
            debug_enabled = self.config.get("debug", False) if isinstance(self.config, dict) else getattr(self.config, "debug", False)
            if debug_enabled:
                print(f"[DEBUG] Organization metrics update:")
                print(f"  Total duration: {self._total_duration}, Total requests: {self._total_requests}, Total data: {self._total_data}")
                print(f"  Organizations tracked: {list(all_orgs)}")
                print(f"  Org duration totals: {dict(self._org_duration_totals)}")
                print(f"  Org request totals: {dict(self._org_request_totals)}")
                print(f"  Org data totals: {dict(self._org_data_totals)}")
                        
        except Exception as e:
            debug_enabled = self.config.get("debug", False) if isinstance(self.config, dict) else getattr(self.config, "debug", False)
            if debug_enabled:
                print(f"Error updating organization system metrics: {e}")
                import traceback
                traceback.print_exc()
            # Even if there's an error, try to set default metrics
            try:
                default_orgs = ["irctc", "kisanmitra", "bashadaan", "beml"]
                for org in default_orgs:
                    self.enterprise_org_cpu_usage.labels(organization=org).set(0.0)
                    self.enterprise_org_memory_usage.labels(organization=org).set(0.0)
                    self.enterprise_org_disk_usage.labels(organization=org).set(0.0)
            except:
                pass  # If this also fails, we can't do anything

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

        # Track running totals for organization-level system metrics
        if organization and organization != "unknown":
            self._org_duration_totals[organization] = self._org_duration_totals.get(organization, 0.0) + duration
            self._org_request_totals[organization] = self._org_request_totals.get(organization, 0) + 1
            self._total_duration += duration
            self._total_requests += 1

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
        
        # Track running totals for organization-level disk usage
        if organization and organization != "unknown":
            self._org_data_totals[organization] = self._org_data_totals.get(organization, 0) + amount
            self._total_data += amount

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
    
    def track_ocr_image_size(
        self, organization: str, app: str, image_size_kb: float
    ):
        """Track OCR image payload size in KB."""
        self.enterprise_ocr_image_size_kb.labels(
            organization=organization, app=app
        ).observe(image_size_kb)

        # Also track as data processing
        self.track_data_processing(organization, app, "ocr_image_kb", int(image_size_kb))

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

    def track_ner_tokens(
        self, organization: str, app: str, tokens: int
    ):
        """Track NER token (word) processing."""
        self.enterprise_ner_tokens_processed.labels(
            organization=organization, app=app
        ).observe(tokens)

        # Also track as data processing
        self.track_data_processing(organization, app, "ner_tokens", tokens)

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
        try:
            self.update_system_metrics()
            self.update_system_metrics_advanced()
        except Exception as e:
            # Don't let errors in metric updates break the metrics endpoint
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

