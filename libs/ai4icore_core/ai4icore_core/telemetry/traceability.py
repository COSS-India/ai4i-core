"""OpenTelemetry-based trace manager with console export for distributed tracing."""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource

from .registry import get_attribute_value
from ai4icore_core.context import get_trace_id

logger = logging.getLogger(__name__)


def _get_default_mapper_path() -> Path:
    """Resolve default mapper path to inference-service/utils/telemetry."""
    current = Path.cwd()

    while current != current.parent:
        inference_service = current / "services" / "inference-service" / "utils" / "telemetry"
        if inference_service.exists():
            return inference_service
        current = current.parent

    logger.warning("Could not find inference-service telemetry path, using src/mappers")
    return Path("src/mappers")


def _initialize_tracer_provider() -> TracerProvider:
    """Initialize OpenTelemetry TracerProvider with console JSON exporter."""
    resource = Resource.create({
        SERVICE_NAME: "ai4icore-telemetry",
        "environment": "development",
    })

    tracer_provider = TracerProvider(resource=resource)
    console_exporter = ConsoleSpanExporter()
    tracer_provider.add_span_processor(SimpleSpanProcessor(console_exporter))
    trace.set_tracer_provider(tracer_provider)
    return tracer_provider


_initialize_tracer_provider()


class OTelSpan:
    """Wrapper around OpenTelemetry Span with service/stage metadata and trace ID."""

    def __init__(self, otel_span: trace.Span, service: str, stage: str):
        """Initialize OTelSpan wrapper."""
        self.span = otel_span
        self.service = service
        self.stage = stage
        self.attributes: Dict[str, Any] = {}
        self.trace_id = get_trace_id()
        logger.info(f"[TRACE START] trace_id={self.trace_id} {service}/{stage}")

    def set_attribute(self, key: str, value: Any) -> None:
        """Attach attribute to span."""
        self.attributes[key] = value
        self.span.set_attribute(key, value)
        logger.debug(f"  [SPAN ATTR] {key} = {value}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "trace_id": self.trace_id,
            "span_id": self.span.get_span_context().span_id,
            "service": self.service,
            "stage": self.stage,
            "attributes": self.attributes,
        }


class TraceManager:
    """Manages distributed tracing by creating spans and computing attributes from JSON mappers."""

    def __init__(self, base_mapper_path: Optional[str] = None):
        """Initialize TraceManager. Auto-resolves inference-service telemetry path if not provided."""
        if base_mapper_path:
            self.base_mapper_path = Path(base_mapper_path)
        else:
            self.base_mapper_path = _get_default_mapper_path()
        self.service_configs: Dict[str, Dict] = {}
        self.tracer = trace.get_tracer(__name__)

    def load_mapper(self, service: str, stage: str) -> Dict[str, list]:
        """Load attribute mapper from <service>/stages.json (cached)."""
        if service not in self.service_configs:
            mapper_path = self.base_mapper_path / service / "stages.json"

            if not mapper_path.exists():
                logger.warning(f"Mapper not found: {mapper_path}")
                self.service_configs[service] = {}
            else:
                with open(mapper_path, "r") as f:
                    self.service_configs[service] = json.load(f)

        stages = self.service_configs.get(service, {})
        return stages.get(stage, {"start": [], "end": []})

    def trace_stage_start(
        self,
        service: str,
        stage: str,
        request: Dict[str, Any]
    ) -> OTelSpan:
        """Create span and attach START attributes computed from request."""
        otel_span = self.tracer.start_span(f"{service}/{stage}")
        span = OTelSpan(otel_span, service, stage)
        mapper = self.load_mapper(service, stage)
        for config in mapper.get("start", []):
            value = get_attribute_value(config, request)
            if value is not None:
                span.set_attribute(config.get("attr"), value)
        return span

    def trace_stage_end(self, span: OTelSpan, response: Dict[str, Any]) -> None:
        """Attach END attributes and close span (triggers console export)."""
        mapper = self.load_mapper(span.service, span.stage)
        for config in mapper.get("end", []):
            value = get_attribute_value(config, response)
            if value is not None:
                span.set_attribute(config.get("attr"), value)
        span.span.end()
        logger.info(f"[TRACE RESULT] {json.dumps(span.to_dict(), indent=2)}")


_trace_manager: Optional[TraceManager] = None


def get_trace_manager() -> TraceManager:
    """Get or create the global TraceManager instance."""
    global _trace_manager
    if _trace_manager is None:
        _trace_manager = TraceManager()
    return _trace_manager

