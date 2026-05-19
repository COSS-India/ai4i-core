"""
OpenTelemetry Tracing Setup with Console Output

This module provides simple distributed tracing setup using OpenTelemetry.
Spans are exported to console for Phase 1 (local development).
In Phase 2, Kafka exporter will be added for production ingestion.
"""

import logging
from typing import Optional

from .config import get_default_config

logger = logging.getLogger(__name__)

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider, SpanProcessor
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.trace import Span
    from opentelemetry.propagate import set_global_textmap
    from opentelemetry.propagators.composite import CompositePropagator
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False
    logger.warning("OpenTelemetry not available, tracing disabled")


def setup_tracing(service_name: str, jaeger_endpoint: Optional[str] = None) -> Optional[object]:
    """
    Setup OpenTelemetry tracing with console output.

    Args:
        service_name: Name of the service (e.g., "ocr-service")
        jaeger_endpoint: Ignored (kept for backward compatibility with existing code)
                        In Phase 1, spans go to console. Phase 2 will use Kafka.

    Returns:
        Tracer instance or None if tracing is not available

    Note: Spans are exported to console. In Phase 2, Kafka exporter will be added.
    """
    if not TRACING_AVAILABLE:
        logger.warning("OpenTelemetry not available, skipping tracing setup")
        return None

    try:
        cfg = get_default_config()

        # Create resource with service name
        resource_attrs = {"service.name": service_name}
        if cfg.service_version:
            resource_attrs["service.version"] = cfg.service_version
        resource = Resource.create(resource_attrs)

        # Setup tracer provider
        tracer_provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(tracer_provider)

        # Add tenant_id processor to add tenant_id attribute to all spans
        tenant_processor = TenantSpanProcessor()
        tracer_provider.add_span_processor(tenant_processor)

        # Add console exporter for Phase 1 (local debugging)
        # In Phase 2, this will be replaced with Kafka exporter
        console_exporter = ConsoleSpanExporter()

        # Register composite propagator: W3C first (respects upstream traceparent),
        # then CorrelationPropagator (maps our correlation ID to the OTel trace ID).
        from .propagator import CorrelationPropagator

        set_global_textmap(CompositePropagator([
            TraceContextTextMapPropagator(),
            CorrelationPropagator(),
        ]))

        console_processor = SimpleSpanProcessor(console_exporter)
        tracer_provider.add_span_processor(console_processor)

        # Get tracer
        tracer = trace.get_tracer(service_name)
        logger.info(f"✅ Tracing initialized for service: {service_name}")
        logger.info("📤 Spans will be exported to console (Phase 1 - local development)")

        return tracer

    except Exception as e:
        logger.error(f"❌ Failed to setup tracing: {e}")
        return None


if TRACING_AVAILABLE:
    class TenantSpanProcessor(SpanProcessor):
        """
        Span processor that adds tenant_id attribute to all spans.

        Reads tenant_id from logging context and adds to every span.
        Used for multi-tenant RBAC filtering in Phase 2 (OpenSearch trace queries).

        ✅ SIMPLIFIED: Only tracks tenant_id (not organization)
        - tenant_id is required for RBAC filtering in OpenSearch
        - organization is not needed (tenant_id is the filtering criteria)
        """

        def on_start(self, span: Span, parent_context=None) -> None:
            """Add tenant_id to span on start."""
            try:
                from ai4icore_core.logging.context import get_tenant_id
                tenant_id = get_tenant_id()
                span.set_attribute("tenant_id", str(tenant_id) if tenant_id else "unknown")
            except Exception:
                pass

        def on_end(self, span: Span) -> None:
            """Called when a span is ended."""
            pass

        def shutdown(self) -> None:
            """Called when the processor is shut down."""
            pass

        def force_flush(self, timeout_millis: int = 30000) -> bool:
            """Force flush any pending spans."""
            return True
else:
    class TenantSpanProcessor:  # type: ignore
        """No-op fallback when OpenTelemetry is unavailable."""

        def on_start(self, span, parent_context=None) -> None:
            return None

        def on_end(self, span) -> None:
            return None

        def shutdown(self) -> None:
            return None

        def force_flush(self, timeout_millis: int = 30000) -> bool:
            return True


def get_tracer(service_name: str) -> Optional[object]:
    """
    Get or create a tracer for the service.

    Args:
        service_name: Name of the service

    Returns:
        Tracer instance or None
    """
    if not TRACING_AVAILABLE:
        return None

    try:
        return trace.get_tracer(service_name)
    except Exception as e:
        logger.warning(f"Failed to get tracer: {e}")
        return None
