"""
IP Address Capture Utilities for Telemetry

Provides utilities to extract client IP addresses from requests
and add them to OpenTelemetry spans for tracing.
"""

import logging
from typing import Optional
from fastapi import Request

logger = logging.getLogger(__name__)

try:
    from opentelemetry import trace
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False
    logger.warning("OpenTelemetry not available, IP capture for spans disabled")


def extract_client_ip(request: Request) -> str:
    """
    Extract client IP address from FastAPI request.
    
    Handles various proxy headers in order of priority:
    1. X-Forwarded-For (first IP in the chain)
    2. X-Real-IP
    3. X-Client-IP
    4. Direct connection IP (request.client.host)
    
    Note: In Docker environments, direct connection IP may show Docker bridge gateway IP
    (e.g., 172.31.0.1) instead of the actual client IP. Use X-Forwarded-For header
    when accessing through a reverse proxy or load balancer.
    
    Args:
        request: FastAPI Request object
        
    Returns:
        Client IP address as string, or "unknown" if not available
    """
    # Debug: Log all relevant headers for troubleshooting
    logger.debug(f"IP extraction - Headers: X-Forwarded-For={request.headers.get('X-Forwarded-For')}, "
                f"X-Real-IP={request.headers.get('X-Real-IP')}, "
                f"X-Client-IP={request.headers.get('X-Client-IP')}, "
                f"Direct IP={request.client.host if request.client else None}")
    
    # Priority 1: X-Forwarded-For header (most common in proxy setups)
    # Format: "client_ip, proxy1_ip, proxy2_ip"
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP (original client)
        # Handle multiple IPs separated by comma
        ip = forwarded_for.split(",")[0].strip()
        if ip:
            logger.debug(f"Using X-Forwarded-For IP: {ip}")
            return ip
    
    # Priority 2: X-Real-IP header (nginx and other proxies)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        ip = real_ip.strip()
        if ip:
            logger.debug(f"Using X-Real-IP: {ip}")
            return ip
    
    # Priority 3: X-Client-IP header (some proxies)
    client_ip_header = request.headers.get("X-Client-IP")
    if client_ip_header:
        ip = client_ip_header.strip()
        if ip:
            logger.debug(f"Using X-Client-IP: {ip}")
            return ip
    
    # Priority 4: Direct connection IP (fallback)
    # WARNING: In Docker, this may be the Docker bridge gateway IP (e.g., 172.31.0.1)
    # This is NOT the actual client IP when accessing from host machine
    if request.client:
        direct_ip = request.client.host
        logger.debug(f"Using direct connection IP: {direct_ip} (may be Docker gateway IP)")
        return direct_ip
    
    logger.warning("No IP address found in request")
    return "unknown"


def add_ip_to_current_span(request: Request) -> None:
    """
    Add client IP address to the current OpenTelemetry span.
    
    This function should be called from middleware after FastAPIInstrumentor
    has created the span for the HTTP request.
    
    Args:
        request: FastAPI Request object
    """
    if not TRACING_AVAILABLE:
        return
    
    try:
        current_span = trace.get_current_span()
        if current_span and current_span.is_recording():
            client_ip = extract_client_ip(request)
            # Add IP as span attribute using standard OpenTelemetry semantic conventions
            current_span.set_attribute("client.ip", client_ip)
            # Also add as http.client_ip for HTTP-specific spans
            current_span.set_attribute("http.client_ip", client_ip)
    except Exception as e:
        # Silently fail - don't break request flow if IP capture fails
        logger.debug(f"Failed to add IP to span: {e}")
