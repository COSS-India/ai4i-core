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
    from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult
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
        base_exporter = None
        if OTLP_AVAILABLE:
            # Use OTLP exporter (recommended, works with Jaeger all-in-one)
            # Remove http:// prefix if present, OTLP expects host:port format
            endpoint = jaeger_endpoint.replace("http://", "").replace("https://", "")
            base_exporter = OTLPSpanExporter(
                endpoint=endpoint,
                insecure=True  # For local development
            )
            logger.info(f"✅ Using OTLP exporter for Jaeger at {endpoint}")
        elif JAEGER_THRIFT_AVAILABLE:
            # Fallback to Jaeger Thrift exporter
            base_exporter = JaegerExporter(
                agent_host_name="jaeger",
                agent_port=6831,
            )
            logger.info("✅ Using Jaeger Thrift exporter")
        else:
            logger.error("❌ No tracing exporter available")
            return None
        
        # Wrap exporter with filtering to reduce noise (filter out http receive/send spans)
        # Always include send/receive spans for API gateway for detailed breakdown
        exporter = FilteringSpanExporter(base_exporter, service_name=service_name)
        
        # Add span processors
        # First add organization processor to add org attribute to all spans
        organization_processor = OrganizationSpanProcessor()
        tracer_provider.add_span_processor(organization_processor)
        
        # Then add batch processor for exporting (with filtering exporter)
        span_processor = BatchSpanProcessor(exporter)
        tracer_provider.add_span_processor(span_processor)
        
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


class FilteringSpanExporter(SpanExporter):
    """
    Span exporter wrapper that filters out noisy spans like http receive/send.
    
    These spans are created by FastAPI instrumentation for ASGI operations
    and can clutter traces. This exporter filters them out before exporting.
    
    Exception: Always includes send/receive spans for api-gateway-service
    to provide detailed request/response breakdown.
    """
    
    # Spans to filter out (by name pattern)
    # These are created by ASGI instrumentation and create noise in traces
    FILTERED_SPAN_NAMES = [
        "http receive",
        "http send",
        " http receive",  # With leading space (common in ASGI spans)
        " http send",     # With leading space
    ]
    
    def __init__(self, base_exporter: SpanExporter, service_name: str = None):
        """Initialize the filtering exporter with a base exporter."""
        self.base_exporter = base_exporter
        self.service_name = service_name
        # Always include send/receive spans for API gateway
        self.include_send_receive = service_name == "api-gateway-service"
    
    def export(self, spans):
        """Export spans, filtering out noisy ones."""
        if not spans:
            return SpanExportResult.SUCCESS
        
        # Filter out spans matching filtered patterns
        filtered_spans = []
        filtered_count = 0
        # For API gateway, de‑duplicate http send/receive spans with the same name
        seen_http_span_names = set()
        for span in spans:
            span_name = span.name.lower() if span.name else ""
            should_filter = False
            
            # Always include send/receive spans for API gateway
            if self.include_send_receive:
                # For API gateway, enhance send/receive spans with more details,
                # but only keep a single http send/receive span per unique span name
                if any(filtered_name.strip() in span_name for filtered_name in self.FILTERED_SPAN_NAMES):
                    original_name = span.name or span_name
                    if original_name in seen_http_span_names:
                        # Skip duplicate http send/receive span for the same operation
                        continue
                    seen_http_span_names.add(original_name)
                    self._enhance_api_gateway_span(span)
                filtered_spans.append(span)
                continue
            
            # For other services, filter out send/receive spans
            # Check if span name ends with or contains any of the filtered patterns
            # ASGI spans typically have format: "service-name METHOD /path http receive/send"
            for filtered_name in self.FILTERED_SPAN_NAMES:
                filtered_lower = filtered_name.lower().strip()
                # Check if span name ends with the pattern or contains it
                if span_name.endswith(filtered_lower) or filtered_lower in span_name:
                    should_filter = True
                    filtered_count += 1
                    break
            
            if not should_filter:
                filtered_spans.append(span)
        
        # Log filtering stats (only if we filtered something and debug is enabled)
        if filtered_count > 0:
            logger.debug(f"Filtered out {filtered_count} noisy spans (http receive/send)")
        elif self.include_send_receive:
            logger.debug(f"Including all spans for {self.service_name} (including send/receive)")
        
        # Export filtered spans
        if filtered_spans:
            return self.base_exporter.export(filtered_spans)
        else:
            return SpanExportResult.SUCCESS
    
    def _enhance_api_gateway_span(self, span):
        """Add detailed attributes to API gateway send/receive spans for better breakdown."""
        try:
            # Extract operation details from span name
            span_name = span.name or ""
            
            # Add span type attribute
            if "http receive" in span_name.lower():
                span.set_attribute("span.type", "http.receive")
                span.set_attribute("span.phase", "request")
            elif "http send" in span_name.lower():
                span.set_attribute("span.type", "http.send")
                span.set_attribute("span.phase", "response")
            
            # Try to extract HTTP method and path from span name
            # Format: "api-gateway-service METHOD /path http receive/send"
            parts = span_name.split()
            if len(parts) >= 3:
                method = parts[1] if parts[1] in ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"] else None
                if method:
                    span.set_attribute("http.method_extracted", method)
                if len(parts) >= 3:
                    path = parts[2] if parts[2].startswith("/") else None
                    if path:
                        span.set_attribute("http.path_extracted", path)
        except Exception as e:
            # Silently fail if enhancement fails
            logger.debug(f"Failed to enhance API gateway span: {e}")
    
    def shutdown(self):
        """Shutdown the base exporter."""
        return self.base_exporter.shutdown()
    
    def force_flush(self, timeout_millis: int = 30000):
        """Force flush the base exporter."""
        return self.base_exporter.force_flush(timeout_millis)


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
