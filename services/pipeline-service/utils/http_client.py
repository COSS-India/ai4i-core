"""
HTTP Client utilities for calling other microservices.

Provides an async HTTP client for making requests to ASR, NMT, and TTS services.
Includes distributed tracing context propagation for end-to-end observability.
"""

import os
import logging
import time
import json
from typing import Dict, Any, Optional, Tuple
import httpx
from .service_registry_client import ServiceRegistryHttpClient

# Import OpenTelemetry for trace context propagation
try:
    from opentelemetry import trace
    from opentelemetry.propagate import inject
    TRACING_AVAILABLE = True
except ImportError:
    TRACING_AVAILABLE = False
    logging.warning("OpenTelemetry not available, trace context propagation disabled")

logger = logging.getLogger(__name__)


def parse_service_error_response(response: httpx.Response) -> Tuple[str, Dict[str, Any]]:
    """
    Parse error response from a service to extract meaningful error information.
    
    Handles nested error structures like:
    - {"detail": {"message": "...", "code": "...", ...}}
    - {"detail": "..."}
    - {"error": "..."}
    - Plain text responses
    
    Returns:
        Tuple of (error_message, error_details_dict)
    """
    try:
        error_body = response.json()
        
        # Handle nested detail structure (common in FastAPI)
        if isinstance(error_body, dict):
            detail = error_body.get("detail", error_body)
            
            # If detail is a dict with message/code structure
            if isinstance(detail, dict):
                message = detail.get("message", detail.get("detail", str(detail)))
                # Extract nested message if present (e.g., from Triton errors)
                if isinstance(message, dict):
                    nested_msg = message.get("message", str(message))
                    message = nested_msg
                
                error_details = {
                    "code": detail.get("code"),
                    "type": detail.get("type"),
                    "message": message,
                    "raw_detail": detail
                }
                return message, error_details
            
            # If detail is a string
            elif isinstance(detail, str):
                return detail, {"message": detail, "raw_detail": error_body}
            
            # Fallback: stringify the detail
            else:
                return str(detail), {"message": str(detail), "raw_detail": error_body}
        
        # If response is a list or other structure
        else:
            return str(error_body), {"message": str(error_body), "raw_detail": error_body}
            
    except (json.JSONDecodeError, ValueError):
        # Not JSON, return text
        text = response.text[:500]  # Limit length
        return text, {"message": text, "raw_detail": text}


class ServiceClient:
    """HTTP client for calling AI microservices via service discovery."""
    
    def __init__(self):
        """Initialize the service client with service registry."""
        # Registry client for discovery (HTTP-backed, e.g. config-service → ZooKeeper)
        self._registry_client = ServiceRegistryHttpClient()
        
        # Service URLs will be discovered via registry (no hardcoded defaults)
        self.asr_service_url: Optional[str] = None
        self.nmt_service_url: Optional[str] = None
        self.tts_service_url: Optional[str] = None
        
        self._discovered: bool = False

        # Create HTTP client with configurable timeout
        # Use environment variable or default to 120 seconds (2 minutes) for inference
        # This is more reasonable than 5 minutes and helps identify slow services faster
        timeout_seconds = float(os.getenv('PIPELINE_HTTP_TIMEOUT', '120.0'))
        # Use httpx.Timeout for more granular control: connect, read, write, pool
        timeout = httpx.Timeout(
            timeout=timeout_seconds,  # Total timeout
            connect=10.0,  # Connection timeout (10 seconds to establish connection)
            read=timeout_seconds - 10.0,  # Read timeout (remaining time for response)
        )
        self.client = httpx.AsyncClient(timeout=timeout)
        logger.info(f"Pipeline HTTP client initialized with timeout: {timeout_seconds}s (connect: 10s, read: {timeout_seconds - 10.0}s)")

    async def _ensure_urls(self) -> None:
        """Discover service URLs via service registry. Raises if services are not found."""
        if self._discovered:
            return

        try:
            # Discover all services via registry
            # Environment variables can override discovery if explicitly set
            asr_env = os.getenv('ASR_SERVICE_URL')
            nmt_env = os.getenv('NMT_SERVICE_URL')
            tts_env = os.getenv('TTS_SERVICE_URL')
            
            if asr_env:
                self.asr_service_url = asr_env.rstrip('/')
                logger.info("ASR service URL provided via environment: %s", self.asr_service_url)
            else:
                url = await self._registry_client.discover_url('asr-service')
                if not url:
                    raise ValueError("ASR service not found in service registry. Ensure asr-service is registered.")
                self.asr_service_url = url.rstrip('/')
                logger.info("ASR service URL discovered via registry: %s", self.asr_service_url)
            
            if nmt_env:
                self.nmt_service_url = nmt_env.rstrip('/')
                logger.info("NMT service URL provided via environment: %s", self.nmt_service_url)
            else:
                url = await self._registry_client.discover_url('nmt-service')
                if not url:
                    raise ValueError("NMT service not found in service registry. Ensure nmt-service is registered.")
                self.nmt_service_url = url.rstrip('/')
                logger.info("NMT service URL discovered via registry: %s", self.nmt_service_url)
            
            if tts_env:
                self.tts_service_url = tts_env.rstrip('/')
                logger.info("TTS service URL provided via environment: %s", self.tts_service_url)
            else:
                url = await self._registry_client.discover_url('tts-service')
                if not url:
                    raise ValueError("TTS service not found in service registry. Ensure tts-service is registered.")
                self.tts_service_url = url.rstrip('/')
                logger.info("TTS service URL discovered via registry: %s", self.tts_service_url)
        except Exception as e:
            logger.error(f"Service discovery failed: {e}")
            raise ValueError(f"Failed to discover required services: {e}") from e
        finally:
            # Mark as attempted to avoid re-discovery per request; TTL/refresh can be added later if needed
            self._discovered = True
    
    def _inject_trace_context(self, headers: Dict[str, str]) -> None:
        """
        Inject OpenTelemetry trace context into headers for distributed tracing.
        
        This allows downstream services to continue the trace span, enabling
        end-to-end observability across the pipeline.
        
        Args:
            headers: Dictionary of HTTP headers to inject trace context into
        """
        if not TRACING_AVAILABLE:
            return
        
        try:
            # Get current span context
            current_span = trace.get_current_span()
            if current_span and current_span.is_recording():
                # Inject trace context into headers (W3C Trace Context format)
                inject(headers)
                logger.debug("✅ Trace context injected into request headers")
            else:
                logger.debug("⚠️ No active span found, skipping trace context injection")
        except Exception as e:
            logger.warning(f"⚠️ Failed to inject trace context: {e}")
    
    async def call_asr_service(self, request_data: Dict[str, Any], jwt_token: Optional[str] = None, api_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Call ASR service for speech-to-text conversion.
        
        Propagates distributed tracing context to enable end-to-end observability.
        """
        await self._ensure_urls()
        headers = {}
        if jwt_token:
            headers['Authorization'] = f'Bearer {jwt_token}'
        if api_key:
            headers['X-API-Key'] = api_key
        # Set X-Auth-Source to BOTH when both JWT and API key are present
        if jwt_token and api_key:
            headers['X-Auth-Source'] = 'BOTH'
        
        # Inject trace context for distributed tracing
        self._inject_trace_context(headers)
        
        service_url = f"{self.asr_service_url}/api/v1/asr/inference"
        logger.info(f"🔗 Calling ASR service: {service_url}")
        
        # Create manual span with proper service name for Jaeger
        # Use a clear, descriptive name that identifies the service being called
        if TRACING_AVAILABLE:
            # Get tracer - use the same service name as the main app to ensure proper nesting
            tracer = trace.get_tracer("pipeline-service")
            span_name = "ASR Service Call"
        else:
            tracer = None
            span_name = None
        
        try:
            if tracer:
                # Create span as child of current active span (task span)
                # Use explicit context to ensure proper nesting
                current_span = trace.get_current_span()
                if current_span and current_span.get_span_context().is_valid:
                    # Create span as child of current span
                    with tracer.start_as_current_span(span_name, context=current_span.get_span_context()) as span:
                        span.set_attribute("http.method", "POST")
                        span.set_attribute("http.url", service_url)
                        span.set_attribute("http.service", "asr-service")
                        span.set_attribute("service.name", "asr")
                        span.set_attribute("service.type", "asr")
                        span.set_attribute("span.kind", "client")  # Mark as outgoing client call
                        
                        start_time = time.time()
                        response = await self.client.post(
                            service_url,
                            json=request_data,
                            headers=headers
                        )
                        elapsed_time = time.time() - start_time
                        
                        span.set_attribute("http.status_code", response.status_code)
                        span.set_attribute("http.duration_ms", elapsed_time * 1000)
                        
                        response.raise_for_status()
                        result = response.json()
                        logger.info(f"✅ ASR service completed successfully in {elapsed_time:.2f}s")
                        return result
                else:
                    # No active span, create root span
                    with tracer.start_as_current_span(span_name) as span:
                        span.set_attribute("http.method", "POST")
                        span.set_attribute("http.url", service_url)
                        span.set_attribute("http.service", "asr-service")
                        span.set_attribute("service.name", "asr")
                        span.set_attribute("service.type", "asr")
                        span.set_attribute("span.kind", "client")
                        
                        start_time = time.time()
                        response = await self.client.post(
                            service_url,
                            json=request_data,
                            headers=headers
                        )
                        elapsed_time = time.time() - start_time
                        
                        span.set_attribute("http.status_code", response.status_code)
                        span.set_attribute("http.duration_ms", elapsed_time * 1000)
                        
                        response.raise_for_status()
                        result = response.json()
                        logger.info(f"✅ ASR service completed successfully in {elapsed_time:.2f}s")
                        return result
            else:
                start_time = time.time()
                response = await self.client.post(
                    service_url,
                    json=request_data,
                    headers=headers
                )
                elapsed_time = time.time() - start_time
                response.raise_for_status()
                result = response.json()
                logger.info(f"✅ ASR service completed successfully in {elapsed_time:.2f}s")
                return result
        except httpx.TimeoutException as e:
            if TRACING_AVAILABLE:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.type", "TimeoutException")
                    current_span.set_attribute("error.message", "ASR service request timed out")
            timeout_val = self.client.timeout.timeout if hasattr(self.client.timeout, 'timeout') else 'unknown'
            error_detail = f"ASR service request timed out after {timeout_val}s. The service may be overloaded or unreachable."
            logger.error(f"❌ ASR service timeout: {error_detail}")
            raise ValueError(error_detail) from e
        except httpx.ConnectError as e:
            if TRACING_AVAILABLE:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.type", "ConnectError")
                    current_span.set_attribute("error.message", "ASR service connection failed")
            error_detail = f"ASR service connection failed. Unable to reach {self.asr_service_url}. Service may be down or unreachable."
            logger.error(f"❌ ASR service connection error: {error_detail}")
            raise ValueError(error_detail) from e
        except httpx.HTTPStatusError as e:
            if TRACING_AVAILABLE:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.type", "HTTPStatusError")
                    current_span.set_attribute("error.message", f"ASR service returned status {e.response.status_code}")
                    current_span.set_attribute("http.status_code", e.response.status_code)
            error_message, error_details = parse_service_error_response(e.response)
            error_detail = f"ASR service returned status {e.response.status_code}: {error_message}"
            logger.error(f"❌ ASR service error: {error_detail}")
            # Create a structured error that can be parsed upstream
            error_dict = {
                "service": "asr",
                "status_code": e.response.status_code,
                "message": error_message,
                "details": error_details
            }
            raise ValueError(json.dumps(error_dict)) from e
        except httpx.HTTPError as e:
            if TRACING_AVAILABLE:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.type", "HTTPError")
                    current_span.set_attribute("error.message", str(e))
            logger.error(f"❌ ASR service HTTP error: {e}")
            raise ValueError(f"ASR service HTTP error: {str(e)}") from e
    
    async def call_nmt_service(self, request_data: Dict[str, Any], jwt_token: Optional[str] = None, api_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Call NMT service for translation.
        
        Propagates distributed tracing context to enable end-to-end observability.
        """
        await self._ensure_urls()
        headers = {}
        if jwt_token:
            headers['Authorization'] = f'Bearer {jwt_token}'
        if api_key:
            headers['X-API-Key'] = api_key
        # Set X-Auth-Source to BOTH when both JWT and API key are present
        if jwt_token and api_key:
            headers['X-Auth-Source'] = 'BOTH'
        
        # Inject trace context for distributed tracing
        self._inject_trace_context(headers)
        
        service_url = f"{self.nmt_service_url}/api/v1/nmt/inference"
        logger.info(f"🔗 Calling NMT service: {service_url}")
        
        # Create manual span with proper service name for Jaeger
        # Use a clear, descriptive name that identifies the service being called
        if TRACING_AVAILABLE:
            # Get tracer - use the same service name as the main app to ensure proper nesting
            tracer = trace.get_tracer("pipeline-service")
            span_name = "NMT Service Call"
        else:
            tracer = None
            span_name = None
        
        try:
            if tracer:
                # Create span as child of current active span (task span)
                # Use explicit context to ensure proper nesting
                current_span = trace.get_current_span()
                if current_span and current_span.get_span_context().is_valid:
                    # Create span as child of current span
                    with tracer.start_as_current_span(span_name, context=current_span.get_span_context()) as span:
                        span.set_attribute("http.method", "POST")
                        span.set_attribute("http.url", service_url)
                        span.set_attribute("http.service", "nmt-service")
                        span.set_attribute("service.name", "nmt")
                        span.set_attribute("service.type", "nmt")
                        span.set_attribute("span.kind", "client")  # Mark as outgoing client call
                        
                        start_time = time.time()
                        response = await self.client.post(
                            service_url,
                            json=request_data,
                            headers=headers
                        )
                        elapsed_time = time.time() - start_time
                        
                        span.set_attribute("http.status_code", response.status_code)
                        span.set_attribute("http.duration_ms", elapsed_time * 1000)
                        
                        response.raise_for_status()
                        result = response.json()
                        logger.info(f"✅ NMT service completed successfully in {elapsed_time:.2f}s")
                        return result
                else:
                    # No active span, create root span
                    with tracer.start_as_current_span(span_name) as span:
                        span.set_attribute("http.method", "POST")
                        span.set_attribute("http.url", service_url)
                        span.set_attribute("http.service", "nmt-service")
                        span.set_attribute("service.name", "nmt")
                        span.set_attribute("service.type", "nmt")
                        span.set_attribute("span.kind", "client")
                        
                        start_time = time.time()
                        response = await self.client.post(
                            service_url,
                            json=request_data,
                            headers=headers
                        )
                        elapsed_time = time.time() - start_time
                        
                        span.set_attribute("http.status_code", response.status_code)
                        span.set_attribute("http.duration_ms", elapsed_time * 1000)
                        
                        response.raise_for_status()
                        result = response.json()
                        logger.info(f"✅ NMT service completed successfully in {elapsed_time:.2f}s")
                        return result
            else:
                start_time = time.time()
                response = await self.client.post(
                    service_url,
                    json=request_data,
                    headers=headers
                )
                elapsed_time = time.time() - start_time
                response.raise_for_status()
                result = response.json()
                logger.info(f"✅ NMT service completed successfully in {elapsed_time:.2f}s")
                return result
        except httpx.TimeoutException as e:
            if TRACING_AVAILABLE and tracer:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.type", "TimeoutException")
                    current_span.set_attribute("error.message", "NMT service request timed out")
            timeout_val = self.client.timeout.timeout if hasattr(self.client.timeout, 'timeout') else 'unknown'
            error_detail = f"NMT service request timed out after {timeout_val}s. The service may be overloaded or unreachable."
            logger.error(f"❌ NMT service timeout: {error_detail}")
            raise ValueError(error_detail) from e
        except httpx.ConnectError as e:
            if TRACING_AVAILABLE and tracer:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.type", "ConnectError")
                    current_span.set_attribute("error.message", "NMT service connection failed")
            error_detail = f"NMT service connection failed. Unable to reach {self.nmt_service_url}. Service may be down or unreachable."
            logger.error(f"❌ NMT service connection error: {error_detail}")
            raise ValueError(error_detail) from e
        except httpx.HTTPStatusError as e:
            if TRACING_AVAILABLE and tracer:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.type", "HTTPStatusError")
                    current_span.set_attribute("error.message", f"NMT service returned status {e.response.status_code}")
                    current_span.set_attribute("http.status_code", e.response.status_code)
            error_message, error_details = parse_service_error_response(e.response)
            error_detail = f"NMT service returned status {e.response.status_code}: {error_message}"
            logger.error(f"❌ NMT service error: {error_detail}")
            # Create a structured error that can be parsed upstream
            error_dict = {
                "service": "nmt",
                "status_code": e.response.status_code,
                "message": error_message,
                "details": error_details
            }
            raise ValueError(json.dumps(error_dict)) from e
        except httpx.HTTPError as e:
            if TRACING_AVAILABLE and tracer:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.type", "HTTPError")
                    current_span.set_attribute("error.message", str(e))
            logger.error(f"❌ NMT service HTTP error: {e}")
            raise ValueError(f"NMT service HTTP error: {str(e)}") from e
    
    async def call_tts_service(self, request_data: Dict[str, Any], jwt_token: Optional[str] = None, api_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Call TTS service for text-to-speech conversion.
        
        Propagates distributed tracing context to enable end-to-end observability.
        """
        await self._ensure_urls()
        headers = {}
        if jwt_token:
            headers['Authorization'] = f'Bearer {jwt_token}'
        if api_key:
            headers['X-API-Key'] = api_key
        # Set X-Auth-Source to BOTH when both JWT and API key are present
        if jwt_token and api_key:
            headers['X-Auth-Source'] = 'BOTH'
        
        # Inject trace context for distributed tracing
        self._inject_trace_context(headers)
        
        service_url = f"{self.tts_service_url}/api/v1/tts/inference"
        logger.info(f"🔗 Calling TTS service: {service_url}")
        
        # Create manual span with proper service name for Jaeger
        # Use a clear, descriptive name that identifies the service being called
        if TRACING_AVAILABLE:
            # Get tracer - use the same service name as the main app to ensure proper nesting
            tracer = trace.get_tracer("pipeline-service")
            span_name = "TTS Service Call"
        else:
            tracer = None
            span_name = None
        
        try:
            if tracer:
                # Create span as child of current active span (task span)
                # Use explicit context to ensure proper nesting
                current_span = trace.get_current_span()
                if current_span and current_span.get_span_context().is_valid:
                    # Create span as child of current span
                    with tracer.start_as_current_span(span_name, context=current_span.get_span_context()) as span:
                        span.set_attribute("http.method", "POST")
                        span.set_attribute("http.url", service_url)
                        span.set_attribute("http.service", "tts-service")
                        span.set_attribute("service.name", "tts")
                        span.set_attribute("service.type", "tts")
                        span.set_attribute("span.kind", "client")  # Mark as outgoing client call
                        
                        start_time = time.time()
                        response = await self.client.post(
                            service_url,
                            json=request_data,
                            headers=headers
                        )
                        elapsed_time = time.time() - start_time
                        
                        span.set_attribute("http.status_code", response.status_code)
                        span.set_attribute("http.duration_ms", elapsed_time * 1000)
                        
                        response.raise_for_status()
                        result = response.json()
                        logger.info(f"✅ TTS service completed successfully in {elapsed_time:.2f}s")
                        return result
                else:
                    # No active span, create root span
                    with tracer.start_as_current_span(span_name) as span:
                        span.set_attribute("http.method", "POST")
                        span.set_attribute("http.url", service_url)
                        span.set_attribute("http.service", "tts-service")
                        span.set_attribute("service.name", "tts")
                        span.set_attribute("service.type", "tts")
                        span.set_attribute("span.kind", "client")
                        
                        start_time = time.time()
                        response = await self.client.post(
                            service_url,
                            json=request_data,
                            headers=headers
                        )
                        elapsed_time = time.time() - start_time
                        
                        span.set_attribute("http.status_code", response.status_code)
                        span.set_attribute("http.duration_ms", elapsed_time * 1000)
                        
                        response.raise_for_status()
                        result = response.json()
                        logger.info(f"✅ TTS service completed successfully in {elapsed_time:.2f}s")
                        return result
            else:
                start_time = time.time()
                response = await self.client.post(
                    service_url,
                    json=request_data,
                    headers=headers
                )
                elapsed_time = time.time() - start_time
                response.raise_for_status()
                result = response.json()
                logger.info(f"✅ TTS service completed successfully in {elapsed_time:.2f}s")
                return result
                response.raise_for_status()
                result = response.json()
                logger.info(f"✅ TTS service completed successfully in {elapsed_time:.2f}s")
                return result
        except httpx.TimeoutException as e:
            if TRACING_AVAILABLE:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.type", "TimeoutException")
                    current_span.set_attribute("error.message", "TTS service request timed out")
            timeout_val = self.client.timeout.timeout if hasattr(self.client.timeout, 'timeout') else 'unknown'
            error_detail = f"TTS service request timed out after {timeout_val}s. The service may be overloaded or unreachable."
            logger.error(f"❌ TTS service timeout: {error_detail}")
            raise ValueError(error_detail) from e
        except httpx.ConnectError as e:
            if TRACING_AVAILABLE:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.type", "ConnectError")
                    current_span.set_attribute("error.message", "TTS service connection failed")
            error_detail = f"TTS service connection failed. Unable to reach {self.tts_service_url}. Service may be down or unreachable."
            logger.error(f"❌ TTS service connection error: {error_detail}")
            raise ValueError(error_detail) from e
        except httpx.HTTPStatusError as e:
            if TRACING_AVAILABLE:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.type", "HTTPStatusError")
                    current_span.set_attribute("error.message", f"TTS service returned status {e.response.status_code}")
                    current_span.set_attribute("http.status_code", e.response.status_code)
            error_message, error_details = parse_service_error_response(e.response)
            error_detail = f"TTS service returned status {e.response.status_code}: {error_message}"
            logger.error(f"❌ TTS service error: {error_detail}")
            # Create a structured error that can be parsed upstream
            error_dict = {
                "service": "tts",
                "status_code": e.response.status_code,
                "message": error_message,
                "details": error_details
            }
            raise ValueError(json.dumps(error_dict)) from e
        except httpx.HTTPError as e:
            if TRACING_AVAILABLE:
                current_span = trace.get_current_span()
                if current_span:
                    current_span.set_attribute("error", True)
                    current_span.set_attribute("error.type", "HTTPError")
                    current_span.set_attribute("error.message", str(e))
            logger.error(f"❌ TTS service HTTP error: {e}")
            raise ValueError(f"TTS service HTTP error: {str(e)}") from e
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
