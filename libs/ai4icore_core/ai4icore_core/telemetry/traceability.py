"""
OpenTelemetry-based trace manager with console export.

Distributed tracing using OpenTelemetry SDK with console exporter.
Spans are automatically exported as structured JSON to console.

Architecture:
  - OpenTelemetry SDK for Python (tracing, span management)
  - ConsoleSpanExporter outputs spans as JSON
  - W3C Trace Context for distributed tracing
  - JSON mapper-based attribute computation (no code rebuild needed)

Usage:
  manager = get_trace_manager()
  span = manager.trace_stage_start("ocr", "preprocess", request)
  # ... do work ...
  manager.trace_stage_end(span, response)  # Auto-exports to console
"""

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


# ============================================================================
# OpenTelemetry Configuration
# ============================================================================

def _initialize_tracer_provider() -> TracerProvider:
    """
    Initialize OpenTelemetry TracerProvider with console exporter.

    Sets up:
    - Resource with service name and metadata
    - Built-in ConsoleSpanExporter for JSON output
    - SimpleSpanProcessor for synchronous export

    Returns:
        Configured TracerProvider instance
    """
    resource = Resource.create({
        SERVICE_NAME: "ai4icore-telemetry",
        "environment": "development",
    })

    tracer_provider = TracerProvider(resource=resource)

    # Use built-in ConsoleSpanExporter
    console_exporter = ConsoleSpanExporter()
    tracer_provider.add_span_processor(SimpleSpanProcessor(console_exporter))

    # Set as global provider
    trace.set_tracer_provider(tracer_provider)

    return tracer_provider


# Initialize global tracer provider on module import
_tracer_provider = _initialize_tracer_provider()


class OTelSpan:
    """
    Wrapper around OpenTelemetry Span for convenience.

    Provides:
    - Attribute and event management
    - Trace ID tracking (distributed tracing)
    - Service/stage metadata
    - Dictionary export for logging

    Attributes:
        span: Underlying OpenTelemetry Span
        service: Service name (e.g., "ocr", "nmt")
        stage: Processing stage (e.g., "preprocess", "inference")
        trace_id: Distributed trace ID from context
        attributes: Span attributes dictionary
    """

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
    """
    Manages distributed tracing for microservices.

    Responsibilities:
    - Create spans for service stages
    - Load stage configurations from JSON mappers
    - Compute and attach attributes (from request/response)
    - End spans and trigger export

    Mapper format (src/mappers/<service>/stages.json):
        {
            "preprocess": {
                "start": [
                    {"attr": "input_length", "expr": "len(text)"},
                    {"attr": "quality", "func": "compute_quality"}
                ],
                "end": [
                    {"attr": "output_size", "expr": "len(result)"}
                ]
            }
        }

    Attributes computed via:
    - "expr": Simple expressions like "len(text)" or "data.get('key', 0)"
    - "func": Registry functions in registry.py for complex logic
    """

    def __init__(self, base_mapper_path: str = "src/mappers"):
        """Initialize TraceManager."""
        self.base_mapper_path = Path(base_mapper_path)
        self.service_configs: Dict[str, Dict] = {}
        self.tracer = trace.get_tracer(__name__)

    def load_mapper(self, service: str, stage: str) -> Dict[str, list]:
        """
        Load attribute mapper for a service stage from JSON.

        Caches mappers to avoid repeated file I/O.

        Args:
            service: Service name (e.g., "ocr", "nmt")
            stage: Stage name (e.g., "preprocess", "inference")

        Returns:
            Dictionary with "start" and "end" keys
        """
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
        """
        Start tracing a processing stage.

        Workflow:
        1. Create OpenTelemetry span
        2. Load mapper for service/stage
        3. Compute and attach START attributes from request
        4. Return span (caller ends it after method completes)

        Args:
            service: Service name
            stage: Stage name
            request: Request data dictionary

        Returns:
            OTelSpan ready for use

        Example:
            span = manager.trace_stage_start("ocr", "preprocess", request)
            # ... do work ...
            manager.trace_stage_end(span, response)
        """
        otel_span = self.tracer.start_span(f"{service}/{stage}")
        span = OTelSpan(otel_span, service, stage)

        # Load mapper and compute START attributes
        mapper = self.load_mapper(service, stage)
        start_configs = mapper.get("start", [])

        for config in start_configs:
            attr_name = config.get("attr")
            value = get_attribute_value(config, request)
            if value is not None:
                span.set_attribute(attr_name, value)

        return span

    def trace_stage_end(self, span: OTelSpan, response: Dict[str, Any]) -> None:
        """
        End tracing for a processing stage.

        Workflow:
        1. Load mapper for this stage
        2. Compute and attach END attributes from response
        3. End the OpenTel span (triggers export)
        4. Log summary

        Args:
            span: OTelSpan to end
            response: Response data dictionary
        """
        service = span.service
        stage = span.stage

        # Load mapper and compute END attributes
        mapper = self.load_mapper(service, stage)
        end_configs = mapper.get("end", [])

        for config in end_configs:
            attr_name = config.get("attr")
            value = get_attribute_value(config, response)
            if value is not None:
                span.set_attribute(attr_name, value)

        # End span (ConsoleSpanExporter.export() is triggered automatically)
        span.span.end()

        # Log summary
        logger.info(f"[TRACE RESULT] {json.dumps(span.to_dict(), indent=2)}")


# ============================================================================
# Global Trace Manager Instance
# ============================================================================

_trace_manager: Optional[TraceManager] = None


def get_trace_manager() -> TraceManager:
    """Get or create the global TraceManager instance."""
    global _trace_manager
    if _trace_manager is None:
        _trace_manager = TraceManager()
    return _trace_manager

