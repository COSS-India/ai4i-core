"""
HTTP Client utilities for calling other microservices.

Provides an async HTTP client for making requests to ASR, NMT, and TTS services.
Includes distributed tracing context propagation for end-to-end observability.
"""

import os
import logging
import time
from typing import Dict, Any, Optional
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
        
        logger.info(f"🔗 Calling ASR service: {self.asr_service_url}/api/v1/asr/inference")
        
        try:
            start_time = time.time()
            response = await self.client.post(
                f"{self.asr_service_url}/api/v1/asr/inference",
                json=request_data,
                headers=headers
            )
            elapsed_time = time.time() - start_time
            response.raise_for_status()
            result = response.json()
            logger.info(f"✅ ASR service completed successfully in {elapsed_time:.2f}s")
            return result
        except httpx.TimeoutException as e:
            timeout_val = self.client.timeout.timeout if hasattr(self.client.timeout, 'timeout') else 'unknown'
            error_detail = f"ASR service request timed out after {timeout_val}s. The service may be overloaded or unreachable."
            logger.error(f"❌ ASR service timeout: {error_detail}")
            raise ValueError(error_detail) from e
        except httpx.ConnectError as e:
            error_detail = f"ASR service connection failed. Unable to reach {self.asr_service_url}. Service may be down or unreachable."
            logger.error(f"❌ ASR service connection error: {error_detail}")
            raise ValueError(error_detail) from e
        except httpx.HTTPStatusError as e:
            error_detail = f"ASR service returned status {e.response.status_code}"
            try:
                error_body = e.response.json()
                error_detail += f": {error_body}"
            except Exception:
                error_detail += f": {e.response.text}"
            logger.error(f"❌ ASR service error: {error_detail}")
            raise ValueError(error_detail) from e
        except httpx.HTTPError as e:
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
        
        logger.info(f"🔗 Calling NMT service: {self.nmt_service_url}/api/v1/nmt/inference")
        
        try:
            start_time = time.time()
            response = await self.client.post(
                f"{self.nmt_service_url}/api/v1/nmt/inference",
                json=request_data,
                headers=headers
            )
            elapsed_time = time.time() - start_time
            response.raise_for_status()
            result = response.json()
            logger.info(f"✅ NMT service completed successfully in {elapsed_time:.2f}s")
            return result
        except httpx.TimeoutException as e:
            timeout_val = self.client.timeout.timeout if hasattr(self.client.timeout, 'timeout') else 'unknown'
            error_detail = f"NMT service request timed out after {timeout_val}s. The service may be overloaded or unreachable."
            logger.error(f"❌ NMT service timeout: {error_detail}")
            raise ValueError(error_detail) from e
        except httpx.ConnectError as e:
            error_detail = f"NMT service connection failed. Unable to reach {self.nmt_service_url}. Service may be down or unreachable."
            logger.error(f"❌ NMT service connection error: {error_detail}")
            raise ValueError(error_detail) from e
        except httpx.HTTPStatusError as e:
            error_detail = f"NMT service returned status {e.response.status_code}"
            try:
                error_body = e.response.json()
                error_detail += f": {error_body}"
            except Exception:
                error_detail += f": {e.response.text}"
            logger.error(f"❌ NMT service error: {error_detail}")
            raise ValueError(error_detail) from e
        except httpx.HTTPError as e:
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
        
        logger.info(f"🔗 Calling TTS service: {self.tts_service_url}/api/v1/tts/inference")
        
        try:
            start_time = time.time()
            response = await self.client.post(
                f"{self.tts_service_url}/api/v1/tts/inference",
                json=request_data,
                headers=headers
            )
            elapsed_time = time.time() - start_time
            response.raise_for_status()
            result = response.json()
            logger.info(f"✅ TTS service completed successfully in {elapsed_time:.2f}s")
            return result
        except httpx.TimeoutException as e:
            timeout_val = self.client.timeout.timeout if hasattr(self.client.timeout, 'timeout') else 'unknown'
            error_detail = f"TTS service request timed out after {timeout_val}s. The service may be overloaded or unreachable."
            logger.error(f"❌ TTS service timeout: {error_detail}")
            raise ValueError(error_detail) from e
        except httpx.ConnectError as e:
            error_detail = f"TTS service connection failed. Unable to reach {self.tts_service_url}. Service may be down or unreachable."
            logger.error(f"❌ TTS service connection error: {error_detail}")
            raise ValueError(error_detail) from e
        except httpx.HTTPStatusError as e:
            error_detail = f"TTS service returned status {e.response.status_code}"
            try:
                error_body = e.response.json()
                error_detail += f": {error_body}"
            except Exception:
                error_detail += f": {e.response.text}"
            logger.error(f"❌ TTS service error: {error_detail}")
            raise ValueError(error_detail) from e
        except httpx.HTTPError as e:
            logger.error(f"❌ TTS service HTTP error: {e}")
            raise ValueError(f"TTS service HTTP error: {str(e)}") from e
    
    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()
