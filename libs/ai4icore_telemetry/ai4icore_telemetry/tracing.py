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
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.resources import Resource
    
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
        
        # Add span processor
        span_processor = BatchSpanProcessor(exporter)
        tracer_provider.add_span_processor(span_processor)
        
        # Get tracer
        tracer = trace.get_tracer(service_name)
        logger.info(f"✅ Tracing initialized for service: {service_name}")
        
        return tracer
    
    except Exception as e:
        logger.error(f"❌ Failed to setup tracing: {e}")
        return None


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
