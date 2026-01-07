"""
OpenTelemetry Tracing Setup for Jaeger

This module provides setup for distributed tracing using OpenTelemetry
and exports traces to Jaeger.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider, SpanProcessor
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.trace import Span
    
    # Try OTLP exporter first (recommended)
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        OTLP_AVAILABLE = True
    except ImportError:
        OTLP_AVAILABLE = False
        logger.warning("OTLP exporter not available, falling back to Jaeger Thrift")
    
    # Fallback to Jaeger Thrift exporter
    if not OTLP_AVAILABLE:
        try:
            from opentelemetry.exporter.jaeger.thrift import JaegerExporter
            JAEGER_THRIFT_AVAILABLE = True
        except ImportError:
            JAEGER_THRIFT_AVAILABLE = False
            logger.warning("Jaeger Thrift exporter not available")
    
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False
    logger.warning("OpenTelemetry not available, tracing disabled")


def setup_tracing(service_name: str, jaeger_endpoint: Optional[str] = None) -> Optional[object]:
    """
    Setup OpenTelemetry tracing with Jaeger exporter.
    
    Args:
        service_name: Name of the service (e.g., "ocr-service")
        jaeger_endpoint: Optional Jaeger endpoint (defaults to env var or http://jaeger:4317)
    
    Returns:
        Tracer instance or None if tracing is not available
    """
    if not TRACING_AVAILABLE:
        logger.warning("OpenTelemetry not available, skipping tracing setup")
        return None
    
    try:
        # Get Jaeger endpoint from parameter or environment
        if not jaeger_endpoint:
            jaeger_endpoint = os.getenv("JAEGER_ENDPOINT", "http://jaeger:4317")
        
        # Create resource with service name
        resource = Resource.create({
            "service.name": service_name,
            "service.version": os.getenv("SERVICE_VERSION", "1.0.0"),
        })
        
        # Setup tracer provider
        tracer_provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(tracer_provider)
        
        # Create exporter based on availability
        if OTLP_AVAILABLE:
            # Use OTLP exporter (recommended, works with Jaeger all-in-one)
            # Remove http:// prefix if present, OTLP expects host:port format
            endpoint = jaeger_endpoint.replace("http://", "").replace("https://", "")
            exporter = OTLPSpanExporter(
                endpoint=endpoint,
                insecure=True  # For local development
            )
            logger.info(f"✅ Using OTLP exporter for Jaeger at {endpoint}")
        elif JAEGER_THRIFT_AVAILABLE:
            # Fallback to Jaeger Thrift exporter
            exporter = JaegerExporter(
                agent_host_name="jaeger",
                agent_port=6831,
            )
            logger.info("✅ Using Jaeger Thrift exporter")
        else:
            logger.error("❌ No tracing exporter available")
            return None
        
        # Add span processors
        # First add organization processor to add org attribute to all spans
        organization_processor = OrganizationSpanProcessor()
        tracer_provider.add_span_processor(organization_processor)
        
        # Create batch processor for exporting
        batch_processor = BatchSpanProcessor(exporter)
        
        # Wrap batch processor with filter to exclude low-level HTTP spans
        # This reduces trace clutter by filtering out http receive/send/disconnect spans
        filtered_processor = FilterSpanProcessor(batch_processor)
        tracer_provider.add_span_processor(filtered_processor)
        
        # Get tracer
        tracer = trace.get_tracer(service_name)
        logger.info(f"✅ Tracing initialized for service: {service_name}")
        
        return tracer
    
    except Exception as e:
        logger.error(f"❌ Failed to setup tracing: {e}")
        return None


class OrganizationSpanProcessor(SpanProcessor):
    """
    Span processor that adds organization attribute to all spans.
    
    Reads organization from logging context and adds it as a span attribute.
    """
    
    def on_start(self, span: Span, parent_context=None) -> None:
        """Called when a span is started."""
        try:
            # Try to import organization context
            from ai4icore_logging.context import get_organization
            organization = get_organization()
            if organization:
                span.set_attribute("organization", organization)
        except Exception:
            # Silently fail if context is not available
            pass
    
    def on_end(self, span: Span) -> None:
        """Called when a span is ended."""
        # No action needed
        pass
    
    def shutdown(self) -> None:
        """Called when the processor is shut down."""
        # No cleanup needed
        pass
    
    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Force flush any pending spans."""
        return True


class FilterSpanProcessor(SpanProcessor):
    """
    Span processor that filters out low-level HTTP spans to reduce trace clutter.
    
    Filters out spans with names like:
    - "http receive"
    - "http send"
    - "http disconnect"
    
    These are low-level ASGI events that add noise without much value.
    """
    
    def __init__(self, processor: SpanProcessor):
        """
        Initialize the filter processor.
        
        Args:
            processor: The underlying span processor to forward filtered spans to
        """
        self.processor = processor
        # Patterns to filter out (case-insensitive matching)
        self.filter_patterns = [
            "http receive",
            "http send",
            "http disconnect",
        ]
    
    def _should_filter(self, span: Span) -> bool:
        """
        Check if a span should be filtered out.
        
        Args:
            span: The span to check
            
        Returns:
            True if the span should be filtered out, False otherwise
        """
        try:
            span_name = span.name.lower()
            should_filter = any(pattern in span_name for pattern in self.filter_patterns)
            
            # Optional: Log filtered spans for debugging (can be removed in production)
            if should_filter and logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Filtering out span: {span.name}")
            
            return should_filter
        except Exception as e:
            # If we can't check the span name, don't filter it (fail open)
            logger.warning(f"Error checking span name for filtering: {e}")
            return False
    
    def on_start(self, span: Span, parent_context=None) -> None:
        """Called when a span is started."""
        # Don't filter on start - we need to see the full span to make a decision
        # Forward all spans to the underlying processor on start
        if self.processor:
            self.processor.on_start(span, parent_context)
    
    def on_end(self, span: Span) -> None:
        """Called when a span is ended."""
        # Filter out unwanted spans before forwarding to the underlying processor
        # Only forward spans that should NOT be filtered
        if not self._should_filter(span):
            if self.processor:
                self.processor.on_end(span)
        # If span should be filtered, we simply don't forward it to the processor
        # This prevents it from being exported to Jaeger
    
    def shutdown(self) -> None:
        """Called when the processor is shut down."""
        if self.processor:
            self.processor.shutdown()
    
    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Force flush any pending spans."""
        if self.processor:
            return self.processor.force_flush(timeout_millis)
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
